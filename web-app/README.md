# Chat Seguro - Interface Web (Design Apple-like)

Interface web moderna e sofisticada inspirada no design da Apple, com Tailwind CSS e animações suaves.

## 🚀 Instalação e Execução

### 1. Instalar Dependências

```bash
cd web-app
npm install
```

### 2. Iniciar o Servidor de Desenvolvimento

```bash
npm run dev
```

A aplicação estará disponível em `http://localhost:3000`

### 3. Certifique-se de que os Servidores estão Rodando

- **Servidor TLS**: `python server/server.py cert.pem key.pem` (porta 4433)
- **Servidor Bridge**: `python server/web_bridge.py` (porta 8000)

## 🎨 Características do Design

- ✅ **Design Apple-like**: Interface limpa e minimalista inspirada na Apple
- ✅ **Tailwind CSS**: Estilização moderna e responsiva
- ✅ **Animações Suaves**: Transições e animações fluidas
- ✅ **Backdrop Blur**: Efeitos de vidro fosco (glassmorphism)
- ✅ **Gradientes Modernos**: Cores suaves e profissionais
- ✅ **Tipografia SF Pro**: Fontes do sistema Apple
- ✅ **Responsivo**: Funciona em diferentes tamanhos de tela

## 📦 Build para Produção

```bash
npm run build
```

Os arquivos serão gerados na pasta `dist/`.

## 🛠️ Tecnologias

- **React 18** - Biblioteca UI
- **Vite** - Build tool e dev server
- **Tailwind CSS 3** - Framework CSS utility-first
- **FastAPI** - Backend bridge (Python)
- **WebSocket** - Comunicação em tempo real

## 🐛 Correções Implementadas

- ✅ **Mensagens aparecem imediatamente** após envio
- ✅ **Histórico atualizado em tempo real** via WebSocket
- ✅ **Sincronização correta** entre envio e recebimento
- ✅ **Feedback visual** para ações do usuário

## 📱 Funcionalidades

1. **Login/Registro**: Interface elegante para autenticação
2. **Lista de Conversas**: Sidebar com preview das mensagens
3. **Chat**: Área de mensagens com design tipo iMessage
4. **Grupos**: Criação e gerenciamento de grupos
5. **Tempo Real**: Notificações instantâneas via WebSocket

## 🎯 Design Inspiração

O design foi inspirado em:
- **iMessage** (iOS) - Bubbles de mensagens
- **macOS** - Sidebar e layout geral
- **Apple Human Interface Guidelines** - Princípios de design
