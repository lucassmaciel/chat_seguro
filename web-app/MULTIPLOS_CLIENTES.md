# Como Iniciar Múltiplos Clientes em Portas Diferentes

Este guia explica como iniciar múltiplas instâncias da interface web em portas diferentes para testar com vários usuários simultaneamente.

## Método 1: Scripts Automáticos (Recomendado)

### Windows (PowerShell)

```powershell
cd web-app
.\start-clients.ps1
```

Isso iniciará 3 clientes automaticamente nas portas 3000, 3001 e 3002.

### Linux/Mac (Bash)

```bash
cd web-app
chmod +x start-clients.sh
./start-clients.sh
```

## Método 2: Manual com Scripts NPM

Você pode iniciar cada cliente manualmente em terminais diferentes:

### Terminal 1 - Cliente na porta 3000
```bash
cd web-app
npm run dev:3000
```
Acesse: http://localhost:3000

### Terminal 2 - Cliente na porta 3001
```bash
cd web-app
npm run dev:3001
```
Acesse: http://localhost:3001

### Terminal 3 - Cliente na porta 3002
```bash
cd web-app
npm run dev:3002
```
Acesse: http://localhost:3002

## Método 3: Usando Variáveis de Ambiente

Você também pode especificar a porta manualmente:

```bash
# Cliente na porta 3000 (padrão)
npm run dev

# Cliente na porta 3001
PORT=3001 npm run dev

# Cliente na porta 3002
PORT=3002 npm run dev

# Cliente na porta 3003
PORT=3003 npm run dev
```

## Configuração da API Backend

Todos os clientes se conectam ao mesmo servidor backend na porta 8000 (padrão).

Se você quiser mudar a porta do backend, use variáveis de ambiente:

```bash
# Cliente conectando a um backend na porta 8001
VITE_API_PORT=8001 npm run dev:3000
```

## Testando com Múltiplos Clientes

1. **Inicie o servidor TLS** (se ainda não estiver rodando):
   ```bash
   python server/server.py cert.pem key.pem
   ```

2. **Inicie o servidor bridge** (se ainda não estiver rodando):
   ```bash
   python server/web_bridge.py
   ```

3. **Inicie múltiplos clientes** usando um dos métodos acima

4. **Acesse cada cliente** em seu navegador:
   - http://localhost:3000
   - http://localhost:3001
   - http://localhost:3002

5. **Faça login** com IDs diferentes em cada cliente:
   - Cliente 1: "lucas"
   - Cliente 2: "caio"
   - Cliente 3: "maria"

6. **Teste mensagens** entre os clientes!

## Notas Importantes

- Todos os clientes compartilham o mesmo backend (porta 8000)
- Cada cliente mantém seu próprio estado local
- As mensagens são sincronizadas via WebSocket
- Você pode ter quantos clientes quiser, apenas use portas diferentes

## Solução de Problemas

### Porta já em uso
Se uma porta estiver ocupada, o Vite tentará usar a próxima porta disponível automaticamente.

### Erro de conexão
Certifique-se de que o servidor bridge está rodando na porta 8000:
```bash
python server/web_bridge.py
```

### Clientes não se comunicam
Verifique se todos os clientes estão usando a mesma porta de API (padrão 8000).

