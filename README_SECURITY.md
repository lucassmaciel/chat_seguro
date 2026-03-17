# Avaliação dos Pilares de Segurança

Esta avaliação cobre confidencialidade, integridade, disponibilidade e autenticidade do projeto Chat Seguro. Os testes automatizados foram adicionados em `tests/test_security_pillars.py` e podem ser executados via `pytest` (dependem do pacote `cryptography`).

## Resultados por Pilar

### Confidencialidade
- O servidor gera e reutiliza o par de certificado/chave TLS armazenado no SQLite, permitindo configurar o contexto SSL sem arquivos temporários expostos além da carga momentânea feita pelo servidor.
- O conteúdo das mensagens é criptografado novamente pelo servidor antes de ser gravado no banco (SecretBox com chave derivada de `MESSAGE_STORE_KEY_B64` ou do material TLS), blindando confidencialidade mesmo se a tabela `messages` for acessada diretamente.
- Melhoria: formalizar a instalação de dependências críticas (`cryptography`, `nacl`, etc.) no ambiente de CI para garantir que o transporte TLS esteja sempre habilitado e os testes não sejam ignorados.

### Integridade
- Cada mensagem persiste um `auth_tag` (HMAC-SHA256 derivado de chave MAC separada) e é decriptada/validada antes da entrega. Alterações no banco (como troca de `blob_b64` ou tag) fazem a mensagem ser descartada e registrada como tentativa inválida.
- Testes de fila em concorrência (`test_queue_limit_eviction_and_concurrency`) garantem que operações simultâneas não quebram a integridade das filas nem permitem overflow silencioso.

### Disponibilidade
- A persistência de mensagens de grupo foi verificada para múltiplos membros, e o consumo limpa a fila individualmente, garantindo que mensagens não sejam perdidas nem entregues em duplicidade para clientes offline.
- Limites configuráveis de fila (`MAX_PENDING_PER_CLIENT`) evitam crescimento indefinido; mensagens mais antigas são descartadas quando necessário para preservar capacidade de entrega.
- Testes de concorrência simulam múltiplos enfileiramentos simultâneos e confirmam que apenas as mensagens mais recentes permanecem na fila quando o limite é atingido.

### Autenticidade
- O servidor exige prova de posse para rotação de chave: a chave pública só é atualizada se o cliente assinar o payload `client_id:pubkey:signing_pubkey` com a chave de assinatura já registrada. Isso previne troca maliciosa sem o segredo anterior.
- O endpoint de remoção de membro de grupo valida que somente o administrador consegue expulsar participantes, reforçando autenticação/autorização no controle de grupos.

## Como Executar os Testes

```bash
pytest tests/test_security_pillars.py
```

> Obs.: os testes são ignorados automaticamente se o pacote `cryptography` não estiver instalado; inclua-o nas dependências do ambiente para obter cobertura completa.
