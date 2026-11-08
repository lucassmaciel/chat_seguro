import base64
import importlib.util
import os
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from nacl.signing import SigningKey

# Se a lib "cryptography" não estiver disponível, todos esses testes são pulados.
# Isso garante que os testes de segurança só rodem em ambientes com dependências corretas.
pytest.importorskip("cryptography", reason="Os testes de segurança exigem cryptography")


def load_server_module(tmp_path):
    """
    Função auxiliar para carregar dinamicamente o módulo do servidor (server.py)
    em um ambiente de testes isolado.

    - Define uma chave de criptografia de teste em MESSAGE_STORE_KEY_B64.
    - Adiciona o diretório do servidor ao sys.path para permitir import dinâmico.
    - Carrega o módulo server.py como "server_runtime_security".
    - Redefine o caminho do banco de dados para usar um arquivo temporário.
    - Limpa os estados globais (PUBLIC_KEYS, GROUPS, ACTIVE_CLIENTS).
    - Configura o limite de mensagens pendentes por cliente.
    - Inicializa chaves públicas persistidas (init_pubkeys).
    """
    # Define uma chave fixa (apenas para testes) em base64 para o armazenamento de mensagens
    secret = base64.b64encode(b"integration-test-key-material-32bytes!!").decode()
    os.environ["MESSAGE_STORE_KEY_B64"] = secret

    # Descobre o diretório do servidor (../server a partir deste arquivo de teste)
    server_dir = Path(__file__).resolve().parent.parent / "server"
    server_dir_str = str(server_dir)

    # Garante que o diretório do servidor está no sys.path para o import funcionar
    if server_dir_str not in sys.path:
        sys.path.insert(0, server_dir_str)

    # Carrega o módulo server.py dinamicamente com um nome específico
    spec = importlib.util.spec_from_file_location(
        "server_runtime_security", server_dir / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    # Redireciona o caminho do banco de dados do servidor para um arquivo temporário
    module.DB_PATH = tmp_path / "security.db"

    # Limpa estados globais para não vazar informações entre testes
    module.PUBLIC_KEYS.clear()
    module.GROUPS.clear()
    module.ACTIVE_CLIENTS.clear()

    # Força um limite menor de mensagens pendentes por cliente para exercitar as proteções
    module.MAX_PENDING_PER_CLIENT = 5

    # Inicializa as chaves públicas persistidas (se houver)
    module.init_pubkeys()

    return module


def test_confidentiality_tls_credentials_are_reused(tmp_path):
    """
    Teste de CONFIDENCIALIDADE (via TLS):

    Verifica se:
    - As credenciais TLS (certificado e chave privada) são geradas apenas uma vez e reutilizadas.
    - O certificado e a chave têm o formato esperado.
    - A função configure_ssl_context consegue criar um SSLContext válido a partir dessas credenciais.
    """
    module = load_server_module(tmp_path)

    # Gera (ou carrega) as credenciais TLS pela primeira vez
    cert_1, key_1 = module.ensure_tls_credentials()
    # Chama novamente para garantir que as mesmas credenciais são reutilizadas
    cert_2, key_2 = module.ensure_tls_credentials()

    # Verifica se o certificado e a chave estão em formato PEM esperado
    assert cert_1.startswith("-----BEGIN CERTIFICATE-----")
    assert key_1.startswith("-----BEGIN RSA PRIVATE KEY-----")

    # Garante que a chamada subsequente não gerou novas credenciais (reutilização)
    assert cert_1 == cert_2
    assert key_1 == key_2

    # Tenta configurar um contexto SSL com essas credenciais
    sslctx = module.configure_ssl_context(cert_1, key_1)
    assert isinstance(sslctx, ssl.SSLContext)


def test_authenticity_pubkey_overwrite_persists_latest(tmp_path):
    """
    Teste de AUTENTICIDADE (gestão de chaves públicas de clientes):

    Objetivos:
    - Garantir que sobrescrever a chave pública de um usuário sem prova criptográfica falhe.
    - Permitir a atualização da chave pública apenas quando acompanhada de uma prova (assinatura)
      do novo binding (username, label, pubkey).
    - Confirmar que, após a atualização válida, o servidor guarda a nova chave e o novo rótulo.
    """
    module = load_server_module(tmp_path)

    # Gera uma nova chave de assinatura (SigningKey) para simular o cliente "alice"
    signing = SigningKey.generate()
    # Extrai a chave de verificação (pública) e codifica em base64 para armazenamento
    signing_b64 = base64.b64encode(signing.verify_key.encode()).decode()

    # Registra uma chave pública inicial para "alice" com o rótulo "pub_old"
    module.store_pubkey("alice", "pub_old", signing_pubkey_b64=signing_b64)

    # Tenta sobrescrever a chave pública sem fornecer prova de assinatura -> deve falhar
    with pytest.raises(ValueError):
        module.store_pubkey("alice", "pub_new", signing_pubkey_b64=signing_b64)

    # Gera uma prova criptográfica assinando o binding "alice:pub_new:<pubkey_b64>"
    proof = base64.b64encode(
        signing.sign(f"alice:pub_new:{signing_b64}".encode()).signature
    ).decode()

    # Agora tenta sobrescrever a chave pública, desta vez com a prova correta
    module.store_pubkey(
        "alice", "pub_new", signing_pubkey_b64=signing_b64, proof=proof
    )

    # Verifica se o rótulo da chave pública foi atualizado para "pub_new"
    assert module.PUBLIC_KEYS["alice"] == "pub_new"
    # Verifica se a chave pública associada a "alice" é a mesma que cadastramos
    assert module.SIGNING_PUBKEYS["alice"] == signing_b64


def test_availability_group_messages_reach_members(tmp_path):
    """
    Teste de DISPONIBILIDADE (entrega de mensagens em grupos):

    Objetivos:
    - Garantir que mensagens enviadas para um grupo sejam entregues a todos os membros
      (exceto o remetente, quando essa for a regra implementada).
    - Confirmar que, após buscar as pendências, a fila de mensagens do usuário seja esvaziada.
    """
    module = load_server_module(tmp_path)

    group_id = "sala-segura"
    members = ["alice", "bob", "carol"]

    # Persiste o grupo no armazenamento (ex.: banco de dados)
    module.persist_group(group_id, members, "alice")
    # Atualiza a estrutura em memória representando o grupo
    module.GROUPS[group_id] = {"members": members, "admin": "alice"}

    # Simula "alice" enviando uma mensagem de grupo para cada membro (exceto ela mesma)
    for member in members:
        if member != "alice":
            module.persist_message(
                recipient_id=member,
                sender_id="alice",
                blob="ciphertext",
                group_id=group_id,
                msg_type="group",
            )

    # Busca mensagens pendentes para "bob" e "carol"
    pending_bob = module.fetch_pending_messages("bob")
    pending_carol = module.fetch_pending_messages("carol")

    # Estrutura esperada de cada mensagem de grupo entregue
    expected_payload = {
        "from": "alice",
        "blob": "ciphertext",
        "group_id": group_id,
        "type": "group",
    }

    # Verifica se ambos receberam exatamente a mensagem esperada
    assert pending_bob == [expected_payload]
    assert pending_carol == [expected_payload]

    # Depois da primeira leitura, as filas de pendências devem estar vazias
    assert module.fetch_pending_messages("bob") == []
    assert module.fetch_pending_messages("carol") == []


def test_integrity_tampering_in_transit_goes_undetected(tmp_path):
    """
    Teste de INTEGRIDADE (detecção de adulteração):

    Cenário:
    - Uma mensagem é persistida corretamente.
    - Depois, alguém (simulando um atacante) altera diretamente o campo 'blob_b64'
      e o 'auth_tag' no banco de dados para esse destinatário.

    Objetivo:
    - Garantir que, ao tentar buscar as mensagens pendentes, o servidor perceba
      que a integridade está comprometida e NÃO retorne a mensagem adulterada.
    """
    module = load_server_module(tmp_path)

    original_blob = "ciphertext-original"

    # Persiste uma mensagem "correta" para o destinatário "bob"
    module.persist_message(
        recipient_id="lucas",
        sender_id="lucasmaciel",
        blob=original_blob,
        meta={"id": 9},
    )

    # Simula adulteração direta na tabela de mensagens:
    # - Altera o conteúdo criptografado (blob_b64)
    # - Altera também o auth_tag (para simular quebra do MAC/autenticação)
    with module.get_conn(module.DB_PATH) as conn:
        conn.execute(
            "UPDATE messages SET blob_b64 = ?, auth_tag = 'x' WHERE recipient_id = ?",
            ("tampered", "lucas"),
        )

    # Ao buscar mensagens pendentes, a integridade deve falhar e nada deve ser retornado
    pending = module.fetch_pending_messages("bob")
    assert pending == []


def test_tampered_auth_tag_is_rejected(tmp_path):
    """
    Teste específico de INTEGRIDADE (auth_tag adulterado):

    Cenário:
    - Persiste uma mensagem simples com blob "ok".
    - Em seguida, alguém altera apenas o campo 'auth_tag' no banco para esse destinatário.

    Objetivo:
    - Garantir que, mesmo que somente o auth_tag seja adulterado,
      a mensagem também seja descartada na leitura de pendências.
    """
    module = load_server_module(tmp_path)

    # Persiste uma mensagem "ok" para o destinatário "bob"
    module.persist_message(recipient_id="lucas", sender_id="lucasmaciel", blob="ok", meta=None)

    # Simula adulteração SOMENTE do auth_tag no banco de dados
    with module.get_conn(module.DB_PATH) as conn:
        conn.execute(
            "UPDATE messages SET auth_tag = 'wrong' WHERE recipient_id = ?", ("lucas",)
        )

    # Ao buscar mensagens pendentes, a verificação de integridade deve falhar e retornar lista vazia
    assert module.fetch_pending_messages("bob") == []
