import asyncio
import base64
import builtins
import contextlib
import hashlib
import hmac
import json
import logging
import os
import ssl
import tempfile
from argparse import ArgumentParser
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from nacl.secret import SecretBox
from nacl.signing import VerifyKey

from db_core import (
    DEFAULT_DB_PATH,
    get_conn,
    get_tls_credentials,
    init_db,
    store_tls_credentials,
)

# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("chatseguro.server")

DB_PATH = DEFAULT_DB_PATH
PUBLIC_KEYS = {}  # client_id -> base64 pubkey
SIGNING_PUBKEYS: dict[str, str] = {}  # client_id -> base64 signing pubkey
ACTIVE_CLIENTS = {}  # client_id -> {reader, writer}
GROUPS = {}  # group_id -> { "members": [client_id], "admin": client_id }
TLS_CERT = None
TLS_KEY = None
MESSAGE_BOX: SecretBox | None = None
MESSAGE_AUTH_KEY: bytes | None = None
MAX_PENDING_PER_CLIENT = int(os.getenv("MAX_PENDING_PER_CLIENT", "500"))


def _derive_message_keys(secret_material: bytes) -> tuple[SecretBox, bytes]:
    mac_key = hashlib.blake2b(
        secret_material, digest_size=SecretBox.KEY_SIZE, person=b"msg-mac"
    ).digest()
    box_key = hashlib.blake2b(
        secret_material, digest_size=SecretBox.KEY_SIZE, person=b"msg-box"
    ).digest()
    return SecretBox(box_key), mac_key


def ensure_message_protection() -> tuple[SecretBox, bytes]:
    global MESSAGE_BOX, MESSAGE_AUTH_KEY, TLS_KEY

    if MESSAGE_BOX and MESSAGE_AUTH_KEY:
        return MESSAGE_BOX, MESSAGE_AUTH_KEY

    env_key = os.getenv("MESSAGE_STORE_KEY_B64")
    if env_key:
        try:
            material = base64.b64decode(env_key)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("MESSAGE_STORE_KEY_B64 inválida") from exc
        if len(material) < SecretBox.KEY_SIZE:
            raise RuntimeError("MESSAGE_STORE_KEY_B64 deve ter pelo menos 32 bytes")
    else:
        if TLS_KEY is None:
            TLS_CERT, TLS_KEY = ensure_tls_credentials()
        material = TLS_KEY.encode()

    MESSAGE_BOX, MESSAGE_AUTH_KEY = _derive_message_keys(material)
    return MESSAGE_BOX, MESSAGE_AUTH_KEY


def load_groups_from_db() -> None:
    global GROUPS

    with get_conn(DB_PATH) as conn:
        cur = conn.cursor()
        group_rows = cur.execute("SELECT group_id, admin FROM groups").fetchall()
        member_rows = cur.execute(
            "SELECT group_id, client_id FROM group_members"
        ).fetchall()

    groups: dict[str, dict[str, list[str] | str]] = {}
    for row in group_rows:
        groups[row["group_id"]] = {"admin": row["admin"], "members": []}

    for member_row in member_rows:
        group = groups.setdefault(
            member_row["group_id"], {"admin": "", "members": []}
        )
        group["members"].append(member_row["client_id"])

    GROUPS = groups


def persist_group(group_id: str, members: list[str], admin: str) -> None:
    with get_conn(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO groups (group_id, admin) VALUES (?, ?)",
            (group_id, admin),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO group_members (group_id, client_id) VALUES (?, ?)",
            [(group_id, member) for member in members],
        )


def remove_group_member(group_id: str, member: str, requester: str) -> bool:
    group = GROUPS.get(group_id)
    if not group:
        raise ValueError("grupo não encontrado")
    if requester != group.get("admin"):
        raise PermissionError("apenas o administrador pode remover membros")
    if member == requester:
        raise PermissionError("o administrador não pode remover a si próprio")
    if member not in group["members"]:
        return False
    group["members"].remove(member)
    with get_conn(DB_PATH) as conn:
        conn.execute(
            "DELETE FROM group_members WHERE group_id = ? AND client_id = ?",
            (group_id, member),
        )
    return True


def _protect_blob(blob: str) -> tuple[str, str]:
    box, auth_key = ensure_message_protection()
    cipher = box.encrypt(blob.encode())
    auth_tag = hmac.new(auth_key, cipher, hashlib.sha256).hexdigest()
    return base64.b64encode(cipher).decode(), auth_tag


def _recover_blob(blob_b64: str, auth_tag: str | None) -> str | None:
    box, auth_key = ensure_message_protection()
    cipher = base64.b64decode(blob_b64)
    if not auth_tag:
        log.warning("Mensagem sem tag autenticada descartada")
        return None
    expected = hmac.new(auth_key, cipher, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, auth_tag):
        log.warning("Tag de integridade inválida; mensagem descartada")
        return None
    return box.decrypt(cipher).decode()


def _enforce_queue_limit(recipient_id: str) -> None:
    if MAX_PENDING_PER_CLIENT <= 0:
        return
    with get_conn(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM messages WHERE recipient_id = ?", (recipient_id,)
        )
        current = cur.fetchone()[0]
        if current < MAX_PENDING_PER_CLIENT:
            return
        overflow = current - MAX_PENDING_PER_CLIENT + 1
        cur.execute(
            """
            DELETE FROM messages
            WHERE id IN (
                SELECT id FROM messages
                WHERE recipient_id = ?
                ORDER BY id
                LIMIT ?
            )
            """,
            (recipient_id, overflow),
        )
        log.warning(
            "Fila de %s reduzia: %d mensagens descartadas por limite de %d",
            recipient_id,
            overflow,
            MAX_PENDING_PER_CLIENT,
        )


def persist_message(
    *,
    recipient_id: str,
    sender_id: str,
    blob: str,
    meta: dict | None = None,
    group_id: str | None = None,
    msg_type: str = "private",
) -> None:
    meta_json = json.dumps(meta or {})
    cipher_b64, auth_tag = _protect_blob(blob)
    _enforce_queue_limit(recipient_id)
    with get_conn(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO messages (recipient_id, sender_id, blob_b64, auth_tag, meta_json, group_id, msg_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (recipient_id, sender_id, cipher_b64, auth_tag, meta_json, group_id, msg_type),
        )


def fetch_pending_messages(client_id: str) -> list[dict]:
    with get_conn(DB_PATH) as conn:
        conn.execute("BEGIN IMMEDIATE;")
        rows = conn.execute(
            """
            SELECT id, sender_id, blob_b64, auth_tag, meta_json, group_id, msg_type
            FROM messages
            WHERE recipient_id = ?
            ORDER BY id
            """,
            (client_id,),
        ).fetchall()
        ids = [row["id"] for row in rows]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", ids)

    pending: list[dict] = []
    for row in rows:
        blob = _recover_blob(row["blob_b64"], row["auth_tag"])
        if blob is None:
            continue
        message = {"from": row["sender_id"], "blob": blob}
        if row["msg_type"] == "group":
            message["group_id"] = row["group_id"]
            message["type"] = "group"
        else:
            message["meta"] = json.loads(row["meta_json"] or "{}")
        pending.append(message)

    return pending


def init_pubkeys():
    global PUBLIC_KEYS, SIGNING_PUBKEYS
    log.info("=" * 70)
    log.info("[server.py][INIT] Inicializando servidor de chat seguro")
    log.info("  └─ Arquivo: server.py | Função: init_pubkeys()")

    # Garante que o schema existe
    init_db(DB_PATH)

    # Carrega chaves já existentes no banco
    with get_conn(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT client_id, pubkey_b64, signing_pubkey_b64 FROM public_keys"
        )
        rows = cur.fetchall()
        PUBLIC_KEYS = {row["client_id"]: row["pubkey_b64"] for row in rows}
        SIGNING_PUBKEYS = {
            row["client_id"]: row["signing_pubkey_b64"] or "" for row in rows
        }

    log.info(
        "  └─ ✅ Tabela public_keys carregada (%d chaves públicas)",
        len(PUBLIC_KEYS),
    )
    load_groups_from_db()
    log.info("  └─ ✅ Tabelas de grupos carregadas (%d grupos)", len(GROUPS))
    log.info("=" * 70)


def generate_tls_credentials() -> tuple[str, str]:
    log.info("[server.py][TLS] Gerando par RSA e certificado autoassinado")
    private_key: rsa.RSAPrivateKey = rsa.generate_private_key(
        public_exponent=65537, key_size=2048
    )
    key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Amazonas"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Manaus"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ChatSeguro"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC))
        .not_valid_after(datetime.now(UTC) + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    cert_bytes = cert.public_bytes(serialization.Encoding.PEM)
    return cert_bytes.decode(), key_bytes.decode()


def ensure_tls_credentials(regenerate: bool = False) -> tuple[str, str]:
    init_db(DB_PATH)
    if not regenerate:
        stored = get_tls_credentials(DB_PATH)
        if stored:
            log.info("[server.py][TLS] Certificado carregado do SQLite")
            return stored

    cert_pem, key_pem = generate_tls_credentials()
    store_tls_credentials(cert_pem, key_pem, DB_PATH)
    log.info("[server.py][TLS] Novo par TLS salvo em tls_credentials (SQLite)")
    return cert_pem, key_pem


def _require_proof_if_rotating(
    client_id: str, pubkey_b64: str, signing_pubkey_b64: str | None, proof: str | None
) -> None:
    stored_signing = SIGNING_PUBKEYS.get(client_id)
    if not stored_signing:
        return
    if not proof:
        raise ValueError("rotação de chave requer prova de posse")
    verify_key = VerifyKey(base64.b64decode(stored_signing))
    message = f"{client_id}:{pubkey_b64}:{signing_pubkey_b64 or stored_signing}".encode()
    verify_key.verify(message, base64.b64decode(proof))


# atualiza o json ao receber nova chave
def store_pubkey(
    client_id: str,
    pubkey_b64: str,
    *,
    signing_pubkey_b64: str | None = None,
    proof: str | None = None,
):
    global PUBLIC_KEYS, SIGNING_PUBKEYS

    _require_proof_if_rotating(client_id, pubkey_b64, signing_pubkey_b64, proof)
    if signing_pubkey_b64:
        SIGNING_PUBKEYS[client_id] = signing_pubkey_b64
    elif client_id not in SIGNING_PUBKEYS:
        SIGNING_PUBKEYS[client_id] = ""
    PUBLIC_KEYS[client_id] = pubkey_b64

    with get_conn(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO public_keys (client_id, pubkey_b64, signing_pubkey_b64)
            VALUES (?, ?, ?)
                ON CONFLICT(client_id) DO UPDATE SET
                pubkey_b64 = excluded.pubkey_b64,
                signing_pubkey_b64 = COALESCE(excluded.signing_pubkey_b64, public_keys.signing_pubkey_b64),
                updated_at = CURRENT_TIMESTAMP
            """,
            (client_id, pubkey_b64, signing_pubkey_b64),
        )

    log.info("")
    log.info("[server.py][PUBKEY_STORE] Chave pública recebida e armazenada")
    log.info("  └─ Arquivo: server.py | Função: store_pubkey()")
    log.info("  └─ Cliente: %s", client_id)
    log.info("  └─ Tamanho da chave (base64): %d caracteres", len(pubkey_b64))
    log.info("  └─ Algoritmo: X25519 (Curve25519 para ECDH)")
    log.info("  └─ Uso: Estabelecer canal criptografado via NaCl Box")
    log.info("  └─ Persistido em: tabela public_keys (SQLite)")


# --- Respostas ---
async def send_ok(writer, payload):
    obj = {"status": "ok", **payload}
    writer.write((json.dumps(obj) + "\n").encode())
    await writer.drain()


async def send_error(writer, reason):
    obj = {"status": "error", "reason": reason}
    writer.write((json.dumps(obj) + "\n").encode())
    await writer.drain()


async def handle_reader(reader, writer):
    addr = writer.get_extra_info("peername")
    client_id = None
    log.info("")
    log.info("[server.py][TLS] Nova conexão TLS estabelecida")
    log.info("  └─ Arquivo: server.py | Função: handle_reader()")
    log.info("  └─ Endereço remoto: %s", addr)
    log.info("  └─ Protocolo: TLS (Transport Layer Security)")

    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode())
            except Exception as e:
                await send_error(writer, f"invalid json: {e}")
                continue

            mtype = msg.get("type")

            if mtype == "publish_key":
                cid = msg.get("client_id")
                pub = msg.get("pubkey")
                signing_pubkey = msg.get("signing_pubkey")
                proof = msg.get("proof")
                if not cid or not pub:
                    await send_error(writer, "publish_key requer client_id e pubkey")
                    continue

                try:
                    store_pubkey(
                        cid,
                        pub,
                        signing_pubkey_b64=signing_pubkey,
                        proof=proof,
                    )
                except ValueError as exc:
                    await send_error(writer, str(exc))
                    continue

                if cid not in ACTIVE_CLIENTS:
                    log.info("[server.py][LOGIN] Cliente conectado: %s", cid)
                    ACTIVE_CLIENTS[cid] = {"reader": reader, "writer": writer}

                client_id = cid
                await send_ok(writer, {"message": "key stored", "client_id": cid})

            elif mtype == "get_key":
                cid = msg.get("client_id")
                if not cid:
                    await send_error(writer, "get_key requer client_id")
                    continue

                pub = PUBLIC_KEYS.get(cid)
                signing_pub = SIGNING_PUBKEYS.get(cid)
                if not pub:
                    await send_error(writer, "não encontrado")
                else:
                    log.info("")
                    log.info("[server.py][PUBKEY_FETCH] Chave pública solicitada")
                    log.info(
                        "  └─ Arquivo: server.py | Função: handle_reader() | Comando: get_key"
                    )
                    log.info("  └─ Cliente solicitado: %s", cid)
                    log.info("  └─ Tamanho (base64): %d caracteres", len(pub))
                    log.info("  └─ ✅ Chave enviada ao solicitante")
                    await send_ok(
                        writer,
                        {"client_id": cid, "pubkey": pub, "signing_pubkey": signing_pub},
                    )

            elif mtype == "send_blob":
                to = msg.get("to")
                frm = msg.get("from")
                blob = msg.get("blob")
                meta = msg.get("meta", {})
                if not to or not frm or not blob:
                    await send_error(writer, "send_blob requer to, from e blob")
                    continue
                persist_message(
                    recipient_id=to,
                    sender_id=frm,
                    blob=blob,
                    meta=meta,
                    msg_type="private",
                )

                log.info("")
                log.info(
                    "[server.py][TRANSPORTE][MSG_PRIVADA] Mensagem criptografada em trânsito"
                )
                log.info(
                    "  └─ Arquivo: server.py | Função: handle_reader() | Comando: send_blob"
                )
                log.info("  └─ Remetente: %s", frm)
                log.info("  └─ Destinatário: %s", to)
                log.info("  └─ Tamanho do blob (base64): %d caracteres", len(blob))
                log.info(
                    "  └─ ⚠️  IMPORTANTE: Servidor NÃO decripta. Apenas transporta!"
                )
                log.info(
                    "  └─ Criptografia aplicada: NaCl Box (X25519 + XSalsa20-Poly1305)"
                )
                log.info("  └─ Autenticação: Poly1305 MAC (16 bytes)")
                log.info("  └─ A descriptografia ocorre no cliente destino")

                await send_ok(writer, {"message": "stored"})

            elif mtype == "create_group":
                group_id = msg.get("group_id")
                members = msg.get("members")
                admin = msg.get("admin")
                if not group_id or not members or not admin:
                    await send_error(
                        writer, "create_group requer group_id, members e admin"
                    )
                    continue
                if group_id in GROUPS:
                    await send_error(writer, "grupo já existe")
                    continue

                GROUPS[group_id] = {"members": members, "admin": admin}
                persist_group(group_id, members, admin)

                log.info("")
                log.info("[server.py][GRUPO][CREATE] Novo grupo criado")
                log.info(
                    "  └─ Arquivo: server.py | Função: handle_reader() | Comando: create_group"
                )
                log.info("  └─ ID do grupo: %s", group_id)
                log.info("  └─ Administrador: %s", admin)
                log.info("  └─ Membros: %s", ", ".join(members))
                log.info("  └─ Total de membros: %d", len(members))

                await send_ok(writer, {"message": "group created"})

            elif mtype == "send_group_blob":
                group_id = msg.get("group_id")
                frm = msg.get("from")
                blob = msg.get("blob")
                if not group_id or not frm or not blob:
                    await send_error(
                        writer, "send_group_blob requer group_id, from e blob"
                    )
                    continue
                if group_id not in GROUPS:
                    await send_error(writer, "grupo não encontrado")
                    continue

                group = GROUPS[group_id]
                if frm not in group["members"]:
                    await send_error(writer, "você não é membro deste grupo")
                    continue

                log.info("")
                log.info(
                    "[server.py][TRANSPORTE][MSG_GRUPO] Mensagem de grupo em trânsito"
                )
                log.info(
                    "  └─ Arquivo: server.py | Função: handle_reader() | Comando: send_group_blob"
                )
                log.info("  └─ Remetente: %s", frm)
                log.info("  └─ Grupo: %s", group_id)
                log.info("  └─ Tamanho do blob (base64): %d caracteres", len(blob))
                log.info("  └─ Destinatários: %d membros", len(group["members"]) - 1)
                log.info("  └─ ⚠️  IMPORTANTE: Servidor NÃO decripta. Apenas distribui!")
                log.info(
                    "  └─ Criptografia aplicada: NaCl SecretBox (XSalsa20-Poly1305)"
                )
                log.info("  └─ Chave simétrica: Compartilhada entre membros do grupo")
                log.info("  └─ Autenticação: Poly1305 MAC (16 bytes)")

                # distribuir a mensagem para os outros membros
                for member in group["members"]:
                    if member != frm:
                        persist_message(
                            recipient_id=member,
                            sender_id=frm,
                            blob=blob,
                            group_id=group_id,
                            msg_type="group",
                        )
                await send_ok(writer, {"message": "stored for group"})

            elif mtype == "remove_group_member":
                group_id = msg.get("group_id")
                member = msg.get("member_id")
                requester = msg.get("requester")
                if not group_id or not member or not requester:
                    await send_error(
                        writer, "remove_group_member requer group_id, member_id e requester"
                    )
                    continue
                try:
                    removed = remove_group_member(group_id, member, requester)
                except PermissionError as exc:
                    await send_error(writer, str(exc))
                    continue
                except ValueError as exc:
                    await send_error(writer, str(exc))
                    continue
                await send_ok(
                    writer, {"message": "member processed", "removed": removed}
                )

            elif mtype == "fetch_blobs":
                cid = msg.get("client_id")
                if not cid:
                    await send_error(writer, "fetch_blobs requer client_id")
                    continue
                items = fetch_pending_messages(cid)

                if items:
                    log.info("")
                    log.info("[server.py][FETCH] Mensagens pendentes entregues")
                    log.info(
                        "  └─ Arquivo: server.py | Função: handle_reader() | Comando: fetch_blobs"
                    )
                    log.info("  └─ Cliente: %s", cid)
                    log.info("  └─ Quantidade de mensagens: %d", len(items))
                    log.info(
                        "  └─ Fila limpa de forma transacional para %s:%s",
                        *(addr or ("desconhecido", "-")),
                    )
                else:
                    log.info("")
                    log.info("[server.py][FETCH] Nenhuma mensagem pendente")
                    log.info("  └─ Cliente: %s", cid)
                    log.info(
                        "  └─ Requisição recebida de %s:%s",
                        *(addr or ("desconhecido", "-")),
                    )

                await send_ok(writer, {"messages": items})

            elif mtype == "list_all":
                requester = msg.get("client_id")
                clients = [c for c in PUBLIC_KEYS if c != requester]
                groups = list(GROUPS.keys())
                await send_ok(writer, {"clients": clients, "groups": groups})

            elif mtype == "disconnect":
                cid = msg.get("client_id")
                if cid and cid in ACTIVE_CLIENTS:
                    del ACTIVE_CLIENTS[cid]
                    log.info("[server.py][LOGOUT] Cliente desconectado: %s", cid)
                await send_ok(writer, {"message": "disconnected"})
                break

            else:
                await send_error(writer, "unknown_type")

    except Exception as e:
        log.error("[server.py][ERRO] Conexão encerrada com erro: %s", e)
    finally:
        writer.close()
        with contextlib.suppress(builtins.BaseException):
            await writer.wait_closed()


def configure_ssl_context(cert_pem: str, key_pem: str) -> ssl.SSLContext:
    sslctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    cert_fd, cert_path = tempfile.mkstemp()
    key_fd, key_path = tempfile.mkstemp()

    try:
        with os.fdopen(cert_fd, "w") as cert_tmp, os.fdopen(key_fd, "w") as key_tmp:
            cert_tmp.write(cert_pem)
            cert_tmp.flush()
            key_tmp.write(key_pem)
            key_tmp.flush()
        sslctx.load_cert_chain(cert_path, key_path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(cert_path)
            os.remove(key_path)
    return sslctx


async def main(cert_pem: str, key_pem: str, host="0.0.0.0", port=4433):
    log.info("")
    log.info("[server.py][SSL/TLS] Configurando contexto SSL/TLS")
    log.info("  └─ Arquivo: server.py | Função: main()")
    log.info("  └─ Origem do certificado: tabela tls_credentials (SQLite)")
    log.info("  └─ Protocolo: TLS (Transport Layer Security)")

    sslctx = configure_ssl_context(cert_pem, key_pem)

    server = await asyncio.start_server(handle_reader, host, port, ssl=sslctx)
    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)

    log.info("")
    log.info("=" * 70)
    log.info(" SERVIDOR RODANDO")
    log.info("=" * 70)
    log.info("   Endereço: %s", addrs)
    log.info("   TLS: ATIVO")
    log.info("   Aguardando conexões...")
    log.info("=" * 70)
    log.info("")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    p = ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", default=4433, type=int)
    p.add_argument(
        "--regen-tls",
        action="store_true",
        help="gera e substitui o certificado/chave armazenados no SQLite",
    )
    args = p.parse_args()
    try:
        TLS_CERT, TLS_KEY = ensure_tls_credentials(regenerate=args.regen_tls)
        init_pubkeys()
        asyncio.run(main(TLS_CERT, TLS_KEY, args.host, args.port))
    except KeyboardInterrupt:
        log.info("\n[server.py] Servidor encerrado pelo usuário")
