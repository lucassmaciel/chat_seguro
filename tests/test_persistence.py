from pathlib import Path

from client.persistence import load_conversations, save_conversations


sample_conversations = {
    "alice": {
        "type": "private",
        "key": None,
        "history": [("10:00", "me", "Oi")],
    },
    "team": {
        "type": "group",
        "key": b"abc123",  # bytes devem ser persistidos como BLOB
        "history": [("11:00", "ana", "Olá time")],
    },
}


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    save_conversations("tester", sample_conversations)

    db_path = Path("tester_state.db")
    assert db_path.exists()

    loaded = load_conversations("tester")

    assert set(loaded) == {"alice", "team"}
    assert loaded["alice"]["history"][0][2] == "Oi"
    assert loaded["team"]["type"] == "group"
    assert loaded["team"]["key"] == b"abc123"


def test_load_unknown_client_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_conversations("missing") == {}
