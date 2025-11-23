# Guia de Deploy Seguro

Este guia resume como preparar o projeto para produção, com foco em confidencialidade, integridade, disponibilidade e autenticidade.

## 1. Pré-requisitos
- Python 3.12+
- Dependências instaladas (`pip install -r requirements.txt` ou `uv pip install .`)
- Certificado TLS válido (`cert.pem` e `key.pem`); para testes locais use `python server/generate_cert.py`.
- Variáveis de ambiente configuradas:
  - `ENV=production`
  - `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USER`, `EMAIL_PASSWORD`, `EMAIL_FROM`
  - Opcional: `ALLOWED_ORIGINS` ou arquivo `allowed_origins.json` caso deseje restringir domínios

## 2. Testes antes do deploy
Execute a suíte completa de testes para validar funcionalidade e pilares de segurança:

```bash
python -m pytest
```

Os testes verificam persistência, armazenamento seguro de usuários, políticas de CORS, emissão de tokens de sessão e logs de MFA sem envio real de e-mails.

## 3. Deploy no Railway (Nixpacks)

- O arquivo `railway.toml` já define o builder Nixpacks, health check em `/api/health` e comando de start `python railway_start.py`.
- Crie um projeto no Railway, conecte o repositório e defina as variáveis de ambiente abaixo na aba **Variables**:
  - `ENV=production`
  - `PORT=8000` (ou deixe o padrão do Railway)
  - `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USER`, `EMAIL_PASSWORD`, `EMAIL_FROM`
  - Opcional: `ALLOWED_ORIGINS` (domínios front-end separados por vírgula)
  - Opcional: `TLS_HOST=127.0.0.1`, `TLS_PORT=4433`, `TLS_CERT_FILE`/`TLS_KEY_FILE` se você enviar certificados próprios
- O Railway expõe apenas a porta `$PORT`; o servidor TLS fica interno no container, consumido pelo bridge via loopback.
- Logs e health check ficam disponíveis diretamente no painel do Railway (`/api/health`).
- Para secrets como certs, use **Variables** com valor em PEM (montados em volume temporário) ou um `Secret File`.

## 4. Execução em produção

### Opção recomendada: containers
1. **Build**
   ```bash
   docker build -t chat-seguro .
   ```
2. **Run** com variáveis seguras e volume para o banco SQLite:
   ```bash
   docker run -d --name chat-seguro \
     -e ENV=production \
     -e EMAIL_HOST=smtp.seudominio.com \
     -e EMAIL_PORT=587 \
     -e EMAIL_USER=usuario \
     -e EMAIL_PASSWORD=senha \
     -e EMAIL_FROM=no-reply@seudominio.com \
    -e ALLOWED_ORIGINS="https://seudominio.com" \
     -v /var/lib/chat-seguro:/data \
     -p 4433:4433 -p 8000:8000 \
     chat-seguro
   ```
   - Monte `/data` para persistir `chatseguro.db` e estados locais.
   - Coloque `cert.pem` e `key.pem` no container ou monte como segredo.

### Execução direta (sem container)
1. Inicie o servidor TLS:
   ```bash
   python server/server.py cert.pem key.pem --host 0.0.0.0 --port 4433
   ```
2. Inicie o Web Bridge FastAPI (HTTP + WebSocket):
   ```bash
   ENV=production uvicorn server.web_bridge:app --host 0.0.0.0 --port 8000
   ```

## 5. Checklist de segurança
- **Confidencialidade**: TLS ativo (certificados válidos), CORS restrito quando `ALLOWED_ORIGINS` estiver definido, chaves privadas protegidas por permissões de arquivo/segredos.
- **Integridade**: Banco SQLite em modo WAL, PBKDF2 para senhas, MACs fornecidos pelas caixas criptográficas NaCl.
- **Disponibilidade**: Use restart policies (`--restart unless-stopped` no Docker), monitore `/api/status`, e configure backups do banco.
- **Autenticidade**: MFA por e-mail, tokens de sessão de alta entropia e certificados TLS assinados por autoridade confiável.

## 6. Observabilidade
- Centralize logs (stdout/servidor) e ative monitoração de falhas de e-mail.
- Exponha métricas básicas via `/api/status` e `/api/health` para health checks.

Seguindo estes passos, o projeto fica pronto para produção com validações automatizadas e controles de segurança alinhados aos pilares fundamentais.
