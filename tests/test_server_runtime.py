import asyncio
import importlib.util
import json
import sys
from pathlib import Path


class DummyWriter:
    def __init__(self):
        self.buffer = b""
        self.closed = False

    def write(self, data: bytes):
        self.buffer += data

    async def drain(self):
        return None

    def getvalue(self):
        return json.loads(self.buffer.decode())

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None

    def get_extra_info(self, name):
        if name == "peername":
            return ("127.0.0.1", 0)
        return None


def load_server_module(tmp_path):
    server_dir = Path(__file__).resolve().parent.parent / "server"
    sys.path.insert(0, str(server_dir))
    spec = importlib.util.spec_from_file_location(
        "server_runtime", server_dir / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.DB_PATH = tmp_path / "runtime.db"
    module.init_pubkeys()
    return module


def test_send_ok_and_error(tmp_path):
    module = load_server_module(tmp_path)
    writer = DummyWriter()

    asyncio.run(module.send_ok(writer, {"payload": True}))
    asyncio.run(module.send_error(writer, "bad"))

    messages = writer.buffer.decode().strip().split("\n")
    ok_msg = json.loads(messages[0])
    err_msg = json.loads(messages[1])

    assert ok_msg["status"] == "ok"
    assert ok_msg["payload"] is True
    assert err_msg == {"status": "error", "reason": "bad"}


def test_store_pubkey_writes_to_db(tmp_path):
    module = load_server_module(tmp_path)

    module.store_pubkey("alice", "base64pub")

    with module.get_conn(module.DB_PATH) as conn:
        row = conn.execute(
            "SELECT client_id, pubkey_b64 FROM public_keys WHERE client_id = ?",
            ("alice",),
        ).fetchone()

    assert row["pubkey_b64"] == "base64pub"
    assert module.PUBLIC_KEYS["alice"] == "base64pub"
