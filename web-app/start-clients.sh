#!/bin/bash
# Script bash para iniciar múltiplos clientes em portas diferentes
# Uso: ./start-clients.sh

echo "Iniciando múltiplos clientes do Chat Seguro..."
echo ""

# Verificar se o node_modules existe
if [ ! -d "node_modules" ]; then
    echo "Instalando dependências..."
    npm install
fi

# Iniciar clientes em portas diferentes
echo "Cliente 1 na porta 3000..."
npm run dev:3000 &
CLIENT1_PID=$!

sleep 2

echo "Cliente 2 na porta 3001..."
PORT=3001 npm run dev:3001 &
CLIENT2_PID=$!

sleep 2

echo "Cliente 3 na porta 3002..."
PORT=3002 npm run dev:3002 &
CLIENT3_PID=$!

echo ""
echo "Clientes iniciados!"
echo "Acesse:"
echo "  - Cliente 1: http://localhost:3000"
echo "  - Cliente 2: http://localhost:3001"
echo "  - Cliente 3: http://localhost:3002"
echo ""
echo "PIDs dos processos: $CLIENT1_PID, $CLIENT2_PID, $CLIENT3_PID"
echo "Para parar, use: kill $CLIENT1_PID $CLIENT2_PID $CLIENT3_PID"

