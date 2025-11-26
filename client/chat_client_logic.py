import asyncio
import base64
import json
import os
import ssl
import time
from pathlib import Path

from nacl import bindings as nb  # acesso às primitivas de baixo nível (libsodium)
from nacl.public import PrivateKey, PublicKey
from nacl.secret import SecretBox
from nacl.signing import SigningKey

from client.persistence import load_conversations, save_conversations
from client.key_store import load_private_key_bytes, store_private_key_bytes

# =========================================
# Utils
# =========================================
DEBUG_CRYPTO = True  # coloque False em produção


def b64(x: bytes) -> str:
    return base64.b64encode(x).decode()


def ub64(s: str) -> bytes:
    return base64.b64decode(s.encode())


def hex_preview(b: bytes, n=32):
    h = b.hex()
    return h if len(h) <= 2 * n else h[: 2 * n] + "..."


def log(msg: str):
    if DEBUG_CRYPTO:
        print(msg)


# =========================================
# DebugBox: wrapper de Box com logs detalhados
# =========================================
class DebugBox:
    """
    Wrapper compatível com o uso existente, mas expondo logs detalhados:
      - shared key (32B) derivada por X25519 (crypto_box_beforenm)
      - nonce (24B), MAC (16B) e tamanhos na cifragem
      - verificações e split (nonce||ciphertext) na decifragem
    Retorna/consome sempre bytes no formato: nonce || ciphertext
    """

    NONCE_SIZE = nb.crypto_box_NONCEBYTES  # 24
    MAC_SIZE = 16
    KEY_SIZE = 32

    def __init__(self, private_key: PrivateKey, public_key: PublicKey, label: str = ""):
        if not isinstance(private_key, PrivateKey) or not isinstance(
            public_key, PublicKey
        ):
            raise TypeError("DebugBox requer PrivateKey e PublicKey")
        self._priv = private_key
        self._pub = public_key
        self._label = label or "Box"

        # Deriva a shared key (K) via X25519 (Curve25519) + preparação p/ XSalsa20-Poly1305
        self._shared_key = nb.crypto_box_beforenm(bytes(public_key), bytes(private_key))
        if len(self._shared_key) != self.KEY_SIZE:
            raise RuntimeError("shared key inesperada")

        # LOGS de inicialização
        log("\n" + "=" * 70)
        log(f"[DEBUG/Box:init] {self._label}")
        log(f"  • pub(peer): {hex_preview(bytes(public_key), 32)}")
        log(f"  • priv(self): {hex_preview(bytes(private_key), 32)}")
        log(f"  • shared_key(32B): {self._shared_key.hex()}")
        log("=" * 70)

    def shared_key(self) -> bytes:
        return self._shared_key

    def encrypt(self, plaintext: bytes, nonce: bytes | None = None) -> bytes:
        if nonce is None:
            nonce = os.urandom(self.NONCE_SIZE)
        if len(nonce) != self.NONCE_SIZE:
            raise ValueError("nonce inválido (esperado 24 bytes)")

        log("\n" + "-" * 70)
        log(f"[DEBUG/Box:encrypt] {self._label}")
        log(f"  • nonce(24B): {nonce.hex()}")
        log(f"  • plaintext({len(plaintext)}B): {repr(plaintext)[:120]}")

        # crypto_box_easy_afternm => ciphertext = MAC(16B) || CIPHERTEXT(mlen)
        ct = nb.crypto_box_easy_afternm(plaintext, nonce, self._shared_key)
        if len(ct) < self.MAC_SIZE:
            raise RuntimeError("ciphertext muito curto")

        mac = ct[: self.MAC_SIZE]
        body = ct[self.MAC_SIZE :]
        log(f"  • MAC(16B): {mac.hex()}")
        log(
            f"  • ctext({len(body)}B): {body.hex()[:96]}{'...' if len(body) > 48 else ''}"
        )
        log(f"  • total ciphertext({len(ct)}B) = 16 + {len(body)}")
        log("-" * 70)

        # Compatível com o restante do app: retornamos bytes = nonce || ct
        return nonce + ct

    def decrypt(self, combined: bytes, nonce: bytes | None = None) -> bytes:
        # Aceita tanto (nonce||ct) quanto (ct, nonce explícito)
        if nonce is None:
            if len(combined) < self.NONCE_SIZE + self.MAC_SIZE:
                raise ValueError("blob muito curto para (nonce||ciphertext)")
            nonce = combined[: self.NONCE_SIZE]
            ct = combined[self.NONCE_SIZE :]
        else:
            ct = combined

        if len(nonce) != self.NONCE_SIZE:
            raise ValueError("nonce inválido (esperado 24 bytes)")

        log("\n" + "-" * 70)
        log(f"[DEBUG/Box:decrypt] {self._label}")
        log(f"  • nonce(24B): {nonce.hex()}")
        if len(ct) < self.MAC_SIZE:
            raise ValueError("ciphertext sem MAC")
        mac = ct[: self.MAC_SIZE]
        body = ct[self.MAC_SIZE :]
        log(f"  • MAC(16B): {mac.hex()}")
        log(
            f"  • ctext({len(body)}B): {body.hex()[:96]}{'...' if len(body) > 48 else ''}"
        )

        # Verifica MAC e decifra
        pt = nb.crypto_box_open_easy_afternm(ct, nonce, self._shared_key)
        log(f"  • plaintext({len(pt)}B): {repr(pt)[:120]}")
        log(f"[DEBUG/Box:decrypt] OK")
        log("-" * 70)

        return pt


# =========================================
# TLS client
# =========================================
class TLSSocketClient:
    def __init__(
        self,
        host,
        port,
        cafile=None,
        *,
        server_name: str | None = None,
        insecure_skip_verify: bool = False,
    ):
        self.host = host
        self.port = port
        self.cafile = cafile
        self.server_name = server_name
        self.insecure_skip_verify = insecure_skip_verify

    async def send_recv(self, obj):
        try:
            sslctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            if self.insecure_skip_verify:
                sslctx.check_hostname = False
                sslctx.verify_mode = ssl.CERT_NONE
            elif self.cafile:
                sslctx.load_verify_locations(self.cafile)

            server_hostname = self.server_name or self.host
            reader, writer = await asyncio.open_connection(
                self.host,
                self.port,
                ssl=sslctx,
                server_hostname=server_hostname,
            )
            writer.write((json.dumps(obj) + "\n").encode())
            await writer.drain()
            line = await reader.readline()
            writer.close()
            await writer.wait_closed()
            if not line:
                return {"status": "error", "reason": "Nenhuma resposta recebida."}
            return json.loads(line.decode())
        except Exception as e:
            return {"status": "error", "reason": f"Erro de conexão: {e}"}


# =========================================
# Chat logic
# =========================================
class ChatLogic:
    def __init__(
        self,
        server_host,
        server_port,
        cacert,
        client_id,
        server_name: str | None = None,
        insecure_skip_verify: bool = False,
    ):
        self.client_id = client_id
        self.client = TLSSocketClient(
            server_host,
            server_port,
            cacert,
            server_name=server_name,
            insecure_skip_verify=insecure_skip_verify,
        )
        self.priv, self.pub, self.signing_key = self.load_or_create_keys(client_id)

        # Carregar conversas salvas
        self.conversations = load_conversations(client_id)
        self.on_new_message = None
        self.on_update_ui = None

    def save_state(self):
        """Salva o estado atual das conversas"""
        save_conversations(self.client_id, self.conversations)

    def load_or_create_keys(self, client_id):
        """
        Agora:
          1) tenta carregar do keystore (SQLite + SecretBox)
          2) se não existir, tenta do arquivo {client_id}_key.pem (migração)
          3) se nada existir, gera nova chave, salva no keystore
        """
        # 1) Tenta keystore
        try:
            loaded = load_private_key_bytes(client_id)
        except Exception as e:
            print(f"[WARN] Erro ao ler keystore local: {e}")
            loaded = None

        signing_priv_bytes = None
        if loaded is not None:
            priv_bytes, signing_priv_bytes = loaded
            print(f"Bem-vindo de volta, {client_id}! Carregando chave do keystore local.")
            priv = PrivateKey(priv_bytes)
        else:
            # 2) Fallback: arquivo antigo (se existir)
            key_file = Path(f"{client_id}_key.pem")
            if key_file.exists():
                print(f"Bem-vindo de volta, {client_id}! Migrando chave do arquivo para o keystore.")
                from base64 import b64decode

                priv_bytes = b64decode(key_file.read_text().encode())
                priv = PrivateKey(priv_bytes)
                # já que deu certo, persiste no keystore
                try:
                    store_private_key_bytes(client_id, bytes(priv), signing_priv_bytes)
                except Exception as e:
                    print(f"[WARN] Falha ao salvar chave no keystore: {e}")
            else:
                # 3) Nova chave
                print(f"Primeiro login de {client_id}. Gerando novo par de chaves.")
                priv = PrivateKey.generate()
                signing_priv_bytes = None
                try:
                    store_private_key_bytes(client_id, bytes(priv), signing_priv_bytes)
                except Exception as e:
                    print(f"[WARN] Falha ao salvar nova chave no keystore: {e}")

        signing_key = (
            SigningKey(signing_priv_bytes) if signing_priv_bytes else SigningKey.generate()
        )
        try:
            store_private_key_bytes(client_id, bytes(priv), signing_key.encode())
        except Exception as e:
            print(f"[WARN] Falha ao persistir chave de assinatura: {e}")

        pub = bytes(priv.public_key)
        return priv, pub, signing_key

    async def publish_key(self):
        signing_pub_b64 = b64(self.signing_key.verify_key.encode())
        proof_payload = f"{self.client_id}:{b64(self.pub)}:{signing_pub_b64}".encode()
        signature_b64 = b64(self.signing_key.sign(proof_payload).signature)
        return await self.client.send_recv(
            {
                "type": "publish_key",
                "client_id": self.client_id,
                "pubkey": b64(self.pub),
                "signing_pubkey": signing_pub_b64,
                "proof": signature_b64,
            }
        )

    async def list_all(self):
        resp = await self.client.send_recv(
            {"type": "list_all", "client_id": self.client_id}
        )
        if resp.get("status") == "ok":
            clients = resp.get("clients", [])
            groups = resp.get("groups", [])

            for client in clients:
                if client not in self.conversations:
                    self.conversations[client] = {"history": [], "type": "private"}
            for group in groups:
                if group not in self.conversations:
                    self.conversations[group] = {
                        "key": None,
                        "history": [],
                        "type": "group",
                    }
            return clients, groups
        return [], []

    async def create_group(self, group_id, members):
        if self.client_id not in members:
            members.append(self.client_id)
        group_key = os.urandom(SecretBox.KEY_SIZE)
        self.conversations[group_id] = {
            "key": group_key,
            "history": [],
            "type": "group",
        }

        await self.client.send_recv(
            {
                "type": "create_group",
                "group_id": group_id,
                "members": members,
                "admin": self.client_id,
            }
        )
        print(f"[GRUPO] Grupo '{group_id}' criado. Distribuindo chave...")

        for member in members:
            if member == self.client_id:
                continue
            resp = await self.client.send_recv({"type": "get_key", "client_id": member})
            if resp.get("status") != "ok":
                print(f"Erro ao obter chave de {member}: {resp.get('reason')}")
                continue

            peer_pub = PublicKey(ub64(resp["pubkey"]))
            # >>> Troca: Box -> DebugBox
            box = DebugBox(
                self.priv, peer_pub, label=f"{self.client_id} → {member} (grp-key)"
            )
            key_blob = box.encrypt(group_key)  # retorna bytes (nonce||ct)

            envelope = {
                "type": "group_key_distribution",
                "group_id": group_id,
                "sender_pub": b64(self.pub),
                "key_blob": b64(key_blob),  # já é bytes, ok
            }
            payload = {
                "type": "send_blob",
                "to": member,
                "from": self.client_id,
                "blob": b64(json.dumps(envelope).encode()),
            }
            await self.client.send_recv(payload)
            print(f"  - Chave enviada para {member}")

        ts = time.strftime("%H:%M:%S")
        self.conversations[group_id]["history"].append(
            (ts, "Sistema", f"Você criou o grupo '{group_id}'.")
        )
        self.save_state()  # Salvar após criar grupo
        if self.on_update_ui:
            self.on_update_ui()

    async def remove_group_member(self, group_id: str, member_id: str):
        return await self.client.send_recv(
            {
                "type": "remove_group_member",
                "group_id": group_id,
                "member_id": member_id,
                "requester": self.client_id,
            }
        )

    async def send_private_message(self, peer, text):
        resp = await self.client.send_recv({"type": "get_key", "client_id": peer})
        if resp.get("status") != "ok":
            return False, f"Não foi possível obter a chave de {peer}"
        peer_pub = PublicKey(ub64(resp["pubkey"]))
        # >>> Troca: Box -> DebugBox
        box = DebugBox(self.priv, peer_pub, label=f"{self.client_id} → {peer}")

        cipher = box.encrypt(text.encode())  # bytes = nonce||ct
        envelope = {"sender_pub": b64(self.pub), "blob": b64(cipher)}
        payload = {
            "type": "send_blob",
            "to": peer,
            "from": self.client_id,
            "blob": b64(json.dumps(envelope).encode()),
        }
        await self.client.send_recv(payload)
        return True, ""

    async def send_group_message(self, group_id, text):
        if (
            group_id not in self.conversations
            or self.conversations[group_id]["type"] != "group"
        ):
            return False, "Grupo não encontrado."

        group_data = self.conversations[group_id]
        if not group_data.get("key"):
            return False, "A chave deste grupo ainda não foi recebida."

        group_box = SecretBox(group_data["key"])
        cipher = group_box.encrypt(text.encode())

        payload = {
            "type": "send_group_blob",
            "group_id": group_id,
            "from": self.client_id,
            "blob": b64(cipher),  # SecretBox.EncryptedMessage já é bytes-like
        }
        await self.client.send_recv(payload)
        return True, ""

    async def poll_blobs(self):
        while True:
            await asyncio.sleep(0.5)  # Poll mais frequente para maior responsividade
            try:
                response = await self.client.send_recv(
                    {"type": "fetch_blobs", "client_id": self.client_id}
                )
                if response.get("status") == "ok":
                    for m in response.get("messages", []):
                        ts = time.strftime("%H:%M:%S")

                        # 1) Mensagens de grupo (blob binário SecretBox)
                        if m.get("type") == "group":
                            group_id = m["group_id"]
                            if group_id in self.conversations and self.conversations[
                                group_id
                            ].get("key"):
                                group_box = SecretBox(
                                    self.conversations[group_id]["key"]
                                )
                                try:
                                    pt = group_box.decrypt(ub64(m["blob"])).decode()
                                    self.conversations[group_id]["history"].append(
                                        (ts, m["from"], pt)
                                    )
                                    self.save_state()  # Salvar após nova mensagem
                                    if self.on_new_message:
                                        self.on_new_message(
                                            group_id, f"[{ts}] {m['from']}: {pt}"
                                        )
                                except Exception as e:
                                    print(f"Erro ao descriptografar msg de grupo: {e}")
                            continue  # próxima mensagem

                        # 2) Envelope JSON: ou distribuição de chave de grupo, ou msg privada
                        try:
                            env = json.loads(base64.b64decode(m["blob"]).decode())

                            # 2a) Distribuição de chave de grupo via Box
                            if env.get("type") == "group_key_distribution":
                                peer_pub = PublicKey(ub64(env["sender_pub"]))
                                # >>> Troca: Box -> DebugBox
                                box = DebugBox(
                                    self.priv,
                                    peer_pub,
                                    label=f"{peer_pub.encode().hex()[:16]} → {self.client_id} (grp-key)",
                                )
                                group_key = box.decrypt(
                                    ub64(env["key_blob"])
                                )  # bytes (nonce||ct) → pt

                                group_id = env["group_id"]
                                if group_id not in self.conversations:
                                    self.conversations[group_id] = {
                                        "history": [],
                                        "type": "group",
                                    }
                                self.conversations[group_id]["key"] = group_key

                                welcome_msg = (
                                    f"Você foi adicionado ao grupo '{group_id}'."
                                )
                                self.conversations[group_id]["history"].append(
                                    (ts, "Sistema", welcome_msg)
                                )
                                self.save_state()  # Salvar após receber chave de grupo
                                if self.on_new_message:
                                    self.on_new_message(
                                        group_id, f"[{ts}] Sistema: {welcome_msg}"
                                    )
                                if self.on_update_ui:
                                    self.on_update_ui()

                            # 2b) Mensagem privada
                            else:
                                peer = m["from"]
                                if peer not in self.conversations:
                                    self.conversations[peer] = {
                                        "history": [],
                                        "type": "private",
                                    }

                                cipher = ub64(env["blob"])  # bytes = nonce||ct
                                sender_pub = PublicKey(ub64(env["sender_pub"]))
                                # >>> Troca: Box -> DebugBox
                                msg_box = DebugBox(
                                    self.priv,
                                    sender_pub,
                                    label=f"{peer} → {self.client_id}",
                                )
                                pt = msg_box.decrypt(cipher).decode()

                                self.conversations[peer]["history"].append(
                                    (ts, peer, pt)
                                )
                                self.save_state()  # Salvar após nova mensagem
                                if self.on_new_message:
                                    self.on_new_message(peer, f"[{ts}] {peer}: {pt}")

                        except Exception as e:
                            print(
                                f"Erro ao processar blob JSON de {m.get('from')}: {e}"
                            )

            except Exception as e:
                print(f"Erro no polling: {e}")
