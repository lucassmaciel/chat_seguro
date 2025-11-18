# Chat Seguro - Guia Completo

Sistema de chat seguro com criptografia end-to-end usando ECDH (X25519) + Salsa20+Poly1305.

## 📋 Pré-requisitos

- Python 3.12+
- Node.js 18+ e npm
- Certificado TLS (gerado automaticamente)

## 🚀 Instalação e Execução

### 1. Instalar Dependências Python

```bash
uv sync
```

### 2. Registrar Usuários com MFA

1. Inicie o servidor bridge (passo 5 abaixo)
2. Acesse `http://localhost:3000`
3. Escolha **Registrar** e informe e-mail, senha forte e ID público do chat
4. Faça login e valide o código MFA enviado diretamente ao e-mail cadastrado

### 3. Gerar Certificados TLS

```bash
python server/generate_cert.py
```

Isso criará `cert.pem` e `key.pem` na raiz do projeto.

### 4. Iniciar o Servidor TLS Principal

```bash
python server/server.py cert.pem key.pem
```

O servidor estará rodando na porta **4433**.

### 5. Iniciar o Servidor Bridge (HTTP/WebSocket)

Em um novo terminal:

```bash
python server/web_bridge.py
```

O servidor bridge estará rodando na porta **8000**.

### 6. Iniciar a Interface Web React

Em um novo terminal:

```bash
cd web-app
npm install
npm run dev
```

A interface web estará disponível em `http://localhost:3000`.

## 🎯 Como Usar

1. **Acesse a interface web** em `http://localhost:3000`
2. **Registre-se** com e-mail, senha forte e ID público do chat (ex: `alice`)
3. **Faça login** usando o e-mail/senha e valide o código MFA enviado
4. **Selecione uma conversa** da lista lateral ou crie um grupo
5. **Envie mensagens** criptografadas end-to-end

### Criar um Grupo

1. Clique no botão **➕** na lista de conversas
2. Digite o nome do grupo
3. Selecione os membros
4. Clique em "Criar Grupo"

### Iniciar Vários clientes
```bash
cd web-app
.\start-clients.ps1
```

## 🔐 Segurança

- **ECDH (X25519)**: Troca de chaves assimétrica
- **Salsa20+Poly1305**: Criptografia simétrica com autenticação
- **TLS**: Transporte seguro entre cliente e servidor
- **End-to-End**: O servidor nunca vê as mensagens descriptografadas

## 📁 Estrutura do Projeto

```
Chat-Seguran-a/
├── server/
│   ├── server.py          # Servidor TLS principal
│   ├── web_bridge.py      # Servidor HTTP/WebSocket bridge
│   └── generate_cert.py   # Gerador de certificados
├── client/
│   ├── chat_client_logic.py  # Lógica de criptografia e comunicação
│   └── chat_gui.py          # Interface Tkinter (legado)
├── web-app/                 # Interface React
│   ├── src/
│   │   ├── components/     # Componentes React
│   │   ├── App.jsx
│   │   └── main.jsx
│   └── package.json
└── README.md
```

## 🐛 Troubleshooting

### Erro de conexão no React

- Verifique se o servidor bridge está rodando na porta 8000
- Verifique se o servidor TLS está rodando na porta 4433
- Verifique os logs do servidor bridge para erros

### Mensagens não aparecem

- Verifique se o WebSocket está conectado (console do navegador)
- Verifique os logs do servidor
- Tente recarregar a página

### Código MFA não recebido

- Aguarde até 1 minuto e confira a caixa de entrada e o lixo eletrônico/spam do e-mail informado durante o login.
- Se o código expirar (após 5 minutos) ou não chegar, refaça o login para disparar um novo envio.
- Verifique se o serviço SMTP está sincronizado: confirme as variáveis `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USER`, `EMAIL_PASSWORD` e `EMAIL_FROM`, reinicie o processo `server/web_bridge.py` e examine os logs do servidor para erros relacionados a `EmailDeliveryError`.


### Erro de certificado

- Certifique-se de que `cert.pem` existe na raiz do projeto
- Execute `python server/generate_cert.py` novamente se necessário

## 📝 Notas

- As chaves privadas são armazenadas localmente em `{client_id}_key.pem`
- As chaves públicas são armazenadas no servidor em `pubkeys.json`
- O servidor nunca descriptografa as mensagens (apenas transporta)
- Cada cliente descriptografa suas próprias mensagens

## 🎨 Interface Web

A interface web React oferece:
- Design moderno com gradientes
- Animações suaves
- Responsividade
- Notificações em tempo real
- Suporte a grupos e mensagens privadas

## 📚 Desenvolvimento

### Modificar a Interface React

```bash
cd web-app
npm run dev
```

### Modificar o Servidor Bridge

Edite `server/web_bridge.py` e reinicie o servidor.
