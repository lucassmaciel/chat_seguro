from client.persistence import save_conversations, load_conversations
from pathlib import Path

TEST_CLIENT_ID = "teste_persistence"

def main():
    # 1) Montar um dicionário fake de conversas
    conversations = {
        "alice": {
            "type": "private",
            "key": None,
            "history": [
                ("10:00:00", "me", "Oi, Alice!"),
                ("10:00:05", "alice", "Fala!"),
            ],
        },
        "grupo_dev": {
            "type": "group",
            "key": b"\x01\x02\x03\x04",  # só pra testar BLOB
            "history": [
                ("11:00:00", "me", "Bom dia, grupo!"),
            ],
        },
    }

    # 2) Salvar no banco
    print("Salvando conversas...")
    save_conversations(TEST_CLIENT_ID, conversations)

    # 3) Confirmar que o arquivo .db foi criado
    db_path = Path(f"{TEST_CLIENT_ID}_state.db")
    print("DB existe?", db_path.exists(), "| caminho:", db_path)

    # 4) Carregar de volta
    print("Carregando conversas...")
    loaded = load_conversations(TEST_CLIENT_ID)

    # 5) Comparar estrutura básica
    print("Conversas carregadas:")
    for cid, cdata in loaded.items():
        print(" -", cid, "| type:", cdata["type"], "| msgs:", len(cdata["history"]))

    # 6) Checar se manteve o conteúdo esperado
    assert "alice" in loaded
    assert loaded["alice"]["history"][0][2] == "Oi, Alice!"
    assert loaded["grupo_dev"]["type"] == "group"
    assert isinstance(loaded["grupo_dev"]["key"], (bytes, type(None)))

    print("\n✅ Persistência SQLite OK!")

if __name__ == "__main__":
    main()
