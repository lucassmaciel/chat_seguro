import asyncio
import builtins
import contextlib
import json
import logging
import ssl
from argparse import ArgumentParser
from pathlib import Path
from db_core import get_conn, init_db, DEFAULT_DB_PATH

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
BLOBS = {}  # recipient_id -> [ {from, blob(base64), meta} ]
ACTIVE_CLIENTS = {}  # client_id -> {reader, writer}
GROUPS = {}  # group_id -> { "members": [client_id], "admin": client_id }


def init_pubkeys():
    global PUBLIC_KEYS
    log.info("=" * 70)
    log.info("[server.py][INIT] Inicializando servidor de chat seguro")
    log.info("  └─ Arquivo: server.py | Função: init_pubkeys()")

    # Garante que o schema existe
    init_db(DB_PATH)

    # Carrega chaves já existentes no banco
    with get_conn(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT client_id, pubkey_b64 FROM public_keys")
        rows = cur.fetchall()
        PUBLIC_KEYS = {row["client_id"]: row["pubkey_b64"] for row in rows}

    log.info(
        "  └─ ✅ Tabela public_keys carregada (%d chaves públicas)",
        len(PUBLIC_KEYS),
    )
    log.info("=" * 70)


# atualiza o json ao receber nova chave
def store_pubkey(client_id, pubkey_b64):
    global PUBLIC_KEYS
    PUBLIC_KEYS[client_id] = pubkey_b64

    with get_conn(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO public_keys (client_id, pubkey_b64)
            VALUES (?, ?)
                ON CONFLICT(client_id) DO UPDATE SET
                pubkey_b64 = excluded.pubkey_b64,
                                              updated_at = CURRENT_TIMESTAMP
            """,
            (client_id, pubkey_b64),
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
                if not cid or not pub:
                    await send_error(writer, "publish_key requer client_id e pubkey")
                    continue

                store_pubkey(cid, pub)

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
                    await send_ok(writer, {"client_id": cid, "pubkey": pub})

            elif mtype == "send_blob":
                to = msg.get("to")
                frm = msg.get("from")
                blob = msg.get("blob")
                meta = msg.get("meta", {})
                if not to or not frm or not blob:
                    await send_error(writer, "send_blob requer to, from e blob")
                    continue
                BLOBS.setdefault(to, []).append(
                    {"from": frm, "blob": blob, "meta": meta}
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
                        BLOBS.setdefault(member, []).append(
                            {
                                "from": frm,
                                "blob": blob,
                                "group_id": group_id,
                                "type": "group",
                            }
                        )
                await send_ok(writer, {"message": "stored for group"})

            elif mtype == "fetch_blobs":
                cid = msg.get("client_id")
                if not cid:
                    await send_error(writer, "fetch_blobs requer client_id")
                    continue
                items = BLOBS.pop(cid, [])

                if items:
                    log.info("")
                    log.info("[server.py][FETCH] Mensagens pendentes entregues")
                    log.info(
                        "  └─ Arquivo: server.py | Função: handle_reader() | Comando: fetch_blobs"
                    )
                    log.info("  └─ Cliente: %s", cid)
                    log.info("  └─ Quantidade de mensagens: %d", len(items))

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


async def main(certfile, keyfile, host="0.0.0.0", port=4433):
    log.info("")
    log.info("[server.py][SSL/TLS] Configurando contexto SSL/TLS")
    log.info("  └─ Arquivo: server.py | Função: main()")
    log.info("  └─ Certificado: %s", certfile)
    log.info("  └─ Chave privada: %s", keyfile)
    log.info("  └─ Protocolo: TLS (Transport Layer Security)")

    sslctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    sslctx.load_cert_chain(certfile, keyfile)

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
    init_pubkeys()
    p = ArgumentParser()
    p.add_argument("certfile")
    p.add_argument("keyfile")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", default=4433, type=int)
    args = p.parse_args()
    try:
        asyncio.run(main(args.certfile, args.keyfile, args.host, args.port))
    except KeyboardInterrupt:
        log.info("\n[server.py] Servidor encerrado pelo usuário")
