import base64
import importlib.util
import os
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from nacl.signing import SigningKey

pytest.importorskip("cryptography", reason="Os testes de segurança exigem cryptography")


def load_server_module(tmp_path):
    secret = base64.b64encode(b"integration-test-key-material-32bytes!!").decode()
    os.environ["MESSAGE_STORE_KEY_B64"] = secret
    server_dir = Path(__file__).resolve().parent.parent / "server"
    server_dir_str = str(server_dir)
    if server_dir_str not in sys.path:
        sys.path.insert(0, server_dir_str)
    spec = importlib.util.spec_from_file_location(
        "server_runtime_security", server_dir / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.DB_PATH = tmp_path / "security.db"
    module.PUBLIC_KEYS.clear()
    module.GROUPS.clear()
    module.ACTIVE_CLIENTS.clear()
    module.MAX_PENDING_PER_CLIENT = 5
    module.init_pubkeys()
    return module


def test_confidentiality_tls_credentials_are_reused(tmp_path):
    module = load_server_module(tmp_path)

    cert_1, key_1 = module.ensure_tls_credentials()
    cert_2, key_2 = module.ensure_tls_credentials()

    assert cert_1.startswith("-----BEGIN CERTIFICATE-----")
    assert key_1.startswith("-----BEGIN RSA PRIVATE KEY-----")
    assert cert_1 == cert_2
    assert key_1 == key_2
    sslctx = module.configure_ssl_context(cert_1, key_1)
    assert isinstance(sslctx, ssl.SSLContext)


def test_authenticity_pubkey_overwrite_persists_latest(tmp_path):
    module = load_server_module(tmp_path)

    signing = SigningKey.generate()
    signing_b64 = base64.b64encode(signing.verify_key.encode()).decode()

    module.store_pubkey("alice", "pub_old", signing_pubkey_b64=signing_b64)

    with pytest.raises(ValueError):
        module.store_pubkey("alice", "pub_new", signing_pubkey_b64=signing_b64)

    proof = base64.b64encode(
        signing.sign(f"alice:pub_new:{signing_b64}".encode()).signature
    ).decode()
    module.store_pubkey(
        "alice", "pub_new", signing_pubkey_b64=signing_b64, proof=proof
    )

    assert module.PUBLIC_KEYS["alice"] == "pub_new"
    assert module.SIGNING_PUBKEYS["alice"] == signing_b64


def test_availability_group_messages_reach_members(tmp_path):
    module = load_server_module(tmp_path)

    group_id = "sala-segura"
    members = ["alice", "bob", "carol"]
    module.persist_group(group_id, members, "alice")
    module.GROUPS[group_id] = {"members": members, "admin": "alice"}

    for member in members:
        if member != "alice":
            module.persist_message(
                recipient_id=member,
                sender_id="alice",
                blob="ciphertext",
                group_id=group_id,
                msg_type="group",
            )

    pending_bob = module.fetch_pending_messages("bob")
    pending_carol = module.fetch_pending_messages("carol")

    expected_payload = {
        "from": "alice",
        "blob": "ciphertext",
        "group_id": group_id,
        "type": "group",
    }

    assert pending_bob == [expected_payload]
    assert pending_carol == [expected_payload]
    assert module.fetch_pending_messages("bob") == []
    assert module.fetch_pending_messages("carol") == []


def test_integrity_tampering_in_transit_goes_undetected(tmp_path):
    module = load_server_module(tmp_path)

    original_blob = "ciphertext-original"
    module.persist_message(
        recipient_id="bob",
        sender_id="alice",
        blob=original_blob,
        meta={"id": 9},
    )

    with module.get_conn(module.DB_PATH) as conn:
        conn.execute(
            "UPDATE messages SET blob_b64 = ?, auth_tag = 'x' WHERE recipient_id = ?",
            ("tampered", "bob"),
        )

    pending = module.fetch_pending_messages("bob")

    assert pending == []


def test_queue_limit_eviction_and_concurrency(tmp_path):
    module = load_server_module(tmp_path)
    module.MAX_PENDING_PER_CLIENT = 3

    def enqueue(idx: int):
        module.persist_message(
            recipient_id="bob", sender_id="alice", blob=f"msg-{idx}", meta={"i": idx}
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        for i in range(6):
            executor.submit(enqueue, i)

    pending = module.fetch_pending_messages("bob")
    payloads = [p["blob"] for p in pending]
    assert len(payloads) == 3
    assert payloads == ["msg-3", "msg-4", "msg-5"]


def test_tampered_auth_tag_is_rejected(tmp_path):
    module = load_server_module(tmp_path)
    module.persist_message(recipient_id="bob", sender_id="alice", blob="ok", meta=None)

    with module.get_conn(module.DB_PATH) as conn:
        conn.execute(
            "UPDATE messages SET auth_tag = 'wrong' WHERE recipient_id = ?", ("bob",)
        )

    assert module.fetch_pending_messages("bob") == []
