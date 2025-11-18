"""
Servidor HTTP/WebSocket bridge para interface React
Faz proxy entre o React e o servidor TLS existente
Suporta múltiplos clientes simultâneos
"""

import asyncio
import json
import logging
import secrets
import sys
import time
from pathlib import Path
from typing import Dict, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

sys.path.insert(0, str(Path(__file__).parent.parent))

from client.chat_client_logic import ChatLogic
from server.email_service import EmailService
from server.user_store import UserStore

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("web_bridge")

app = FastAPI(title="Chat Seguro Web Bridge")

# CORS para permitir conexões do React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especifique o domínio do React
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Armazenamento de sessões ativas (suporta múltiplos clientes)
active_sessions: Dict[str, ChatLogic] = {}
websocket_connections: Dict[str, Set[WebSocket]] = {}
pending_mfa: Dict[str, dict] = {}

# Configuração do servidor TLS
SERVER_HOST = "localhost"
SERVER_PORT = 4433
CACERT = "cert.pem"

user_store = UserStore("users.json")
email_service = EmailService()
MFA_TOKEN_TTL = 300  # 5 minutos


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    confirm_password: str
    client_id: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MFAVerifyRequest(BaseModel):
    token: str
    code: str


class SendMessageRequest(BaseModel):
    to: str
    message: str
    client_id: str = None


def notify_websockets(client_id: str, event_type: str, data: dict):
    """Notifica todos os WebSockets conectados de um cliente"""
    if client_id in websocket_connections:
        message = json.dumps({"type": event_type, **data})
        disconnected = set()
        for ws in websocket_connections[client_id]:
            try:
                asyncio.create_task(ws.send_text(message))
            except Exception as e:
                log.error(f"Erro ao enviar para WebSocket: {e}")
                disconnected.add(ws)
        websocket_connections[client_id] -= disconnected


@app.get("/api/status")
async def get_status():
    """Endpoint para verificar status do servidor e clientes conectados"""
    return JSONResponse(
        {
            "status": "ok",
            "active_sessions": len(active_sessions),
            "clients": list(active_sessions.keys()),
            "websocket_connections": {
                client_id: len(connections)
                for client_id, connections in websocket_connections.items()
            },
        }
    )


async def _establish_session(client_id: str) -> dict:
    """Cria uma sessão segura com o servidor TLS se necessário."""

    if client_id in active_sessions:
        return {"client_id": client_id, "session_active": True}

    logic = ChatLogic(SERVER_HOST, SERVER_PORT, CACERT, client_id)

    def on_new_message(peer, message):
        notify_websockets(client_id, "new_message", {"peer": peer, "message": message})

    def on_update_ui():
        notify_websockets(client_id, "update_ui", {})

    logic.on_new_message = on_new_message
    logic.on_update_ui = on_update_ui

    success = await logic.publish_key()
    if not success:
        raise HTTPException(status_code=500, detail="Falha ao publicar chave")

    active_sessions[client_id] = logic
    websocket_connections[client_id] = set()
    asyncio.create_task(poll_messages(client_id))
    await logic.list_all()
    log.info(
        "Cliente %s conectado. Sessões ativas: %d",
        client_id,
        len(active_sessions),
    )
    return {"client_id": client_id, "session_active": False}


@app.post("/api/register")
async def register_user(request: RegisterRequest):
    password = request.password.strip()
    if password != request.confirm_password.strip():
        raise HTTPException(status_code=400, detail="As senhas não conferem")
    if len(password) < 8:
        raise HTTPException(
            status_code=400, detail="A senha deve ter pelo menos 8 caracteres"
        )
    if not request.client_id.strip():
        raise HTTPException(status_code=400, detail="client_id é obrigatório")
    try:
        user_store.create_user(request.email, password, request.client_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log.info("Novo usuário registrado: %s", request.email)
    return JSONResponse({"status": "ok", "message": "Usuário registrado"})


@app.post("/api/login")
async def login(request: LoginRequest):
    user = user_store.verify_user(request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    token = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1_000_000):06d}"
    pending_mfa[token] = {
        "code": code,
        "client_id": user["client_id"],
        "email": user["email"],
        "expires_at": time.time() + MFA_TOKEN_TTL,
    }
    email_service.send_mfa_code(user["email"], code)
    log.info("Código MFA gerado para %s", user["email"])
    return JSONResponse(
        {
            "status": "mfa_required",
            "message": "Código MFA enviado por e-mail",
            "token": token,
            "expires_in": MFA_TOKEN_TTL,
        }
    )


@app.post("/api/verify-mfa")
async def verify_mfa(request: MFAVerifyRequest):
    info = pending_mfa.get(request.token)
    if not info:
        raise HTTPException(status_code=400, detail="Token inválido")

    if info["expires_at"] < time.time():
        pending_mfa.pop(request.token, None)
        raise HTTPException(status_code=400, detail="Token expirado")

    if info["code"] != request.code:
        raise HTTPException(status_code=400, detail="Código MFA inválido")

    pending_mfa.pop(request.token, None)
    session_info = await _establish_session(info["client_id"])
    return JSONResponse({"status": "ok", **session_info})


@app.post("/api/logout")
async def logout(client_id: str):
    """Logout e desconexão"""
    if client_id in active_sessions:
        logic = active_sessions[client_id]
        try:
            await logic.client.send_recv({"type": "disconnect", "client_id": client_id})
        except:
            pass
        del active_sessions[client_id]
        log.info(
            f"Cliente {client_id} desconectado. Sessões ativas: {len(active_sessions)}"
        )

    if client_id in websocket_connections:
        # Fechar todas as conexões WebSocket
        for ws in websocket_connections[client_id]:
            try:
                await ws.close()
            except:
                pass
        del websocket_connections[client_id]

    return JSONResponse({"status": "ok", "message": "Logout realizado"})


@app.get("/api/conversations")
async def get_conversations(client_id: str):
    """Lista todas as conversas (clientes e grupos)"""
    if client_id not in active_sessions:
        raise HTTPException(status_code=401, detail="Não autenticado")

    logic = active_sessions[client_id]

    # Cache: só chamar list_all se necessário (primeira vez ou a cada 10s)
    import time

    if not hasattr(logic, "_last_list_all") or time.time() - logic._last_list_all > 10:
        clients, groups = await logic.list_all()
        logic._last_list_all = time.time()
        logic._cached_clients = clients
        logic._cached_groups = groups
    else:
        clients = getattr(logic, "_cached_clients", [])
        groups = getattr(logic, "_cached_groups", [])

    conversations = []
    for conv_id, conv_data in logic.conversations.items():
        conversations.append(
            {
                "id": conv_id,
                "type": conv_data.get("type", "private"),
                "history": [
                    {"timestamp": ts, "sender": sender, "message": msg}
                    for ts, sender, msg in conv_data.get("history", [])
                ],
            }
        )

    return JSONResponse(
        {
            "status": "ok",
            "conversations": conversations,
            "available_clients": clients,
            "available_groups": groups,
        }
    )


@app.post("/api/send-message")
async def send_message(request: SendMessageRequest):
    """Envia uma mensagem privada ou de grupo"""
    client_id = request.client_id
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id é obrigatório")
    if client_id not in active_sessions:
        raise HTTPException(status_code=401, detail="Não autenticado")

    logic = active_sessions[client_id]
    to = request.to

    if to not in logic.conversations:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    conv_type = logic.conversations[to]["type"]
    success = False
    error = ""

    # Adicionar mensagem ao histórico local antes de enviar
    import time

    ts = time.strftime("%H:%M:%S")
    logic.conversations[to]["history"].append((ts, client_id, request.message))
    # Salvar estado em background para não bloquear
    asyncio.create_task(asyncio.to_thread(logic.save_state))

    if conv_type == "private":
        success, error = await logic.send_private_message(to, request.message)
    elif conv_type == "group":
        success, error = await logic.send_group_message(to, request.message)
    else:
        raise HTTPException(status_code=400, detail="Tipo de conversa inválido")

    if not success:
        # Remover mensagem do histórico se falhou
        if (
            logic.conversations[to]["history"]
            and logic.conversations[to]["history"][-1][1] == client_id
        ):
            logic.conversations[to]["history"].pop()
        raise HTTPException(status_code=500, detail=error)

    # Notificar via WebSocket
    notify_websockets(
        client_id,
        "message_sent",
        {"to": to, "message": request.message, "timestamp": ts},
    )

    return JSONResponse({"status": "ok", "message": "Mensagem enviada"})


class CreateGroupRequest(BaseModel):
    group_id: str
    members: list[str]
    client_id: str


@app.post("/api/create-group")
async def create_group(request: CreateGroupRequest):
    """Cria um novo grupo"""
    client_id = request.client_id
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id é obrigatório")
    if client_id not in active_sessions:
        raise HTTPException(status_code=401, detail="Não autenticado")

    logic = active_sessions[client_id]
    await logic.create_group(request.group_id, request.members)
    logic.save_state()  # Salvar após criar grupo

    return JSONResponse({"status": "ok", "message": "Grupo criado"})


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket para notificações em tempo real - suporta múltiplas conexões por cliente"""
    await websocket.accept()

    if client_id not in websocket_connections:
        websocket_connections[client_id] = set()

    websocket_connections[client_id].add(websocket)
    log.info(
        f"WebSocket conectado para {client_id}. Total de conexões: {len(websocket_connections[client_id])}"
    )

    try:
        while True:
            # Manter conexão viva e receber mensagens (se necessário)
            data = await websocket.receive_text()
            # Por enquanto, apenas ecoamos para manter conexão
            await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        log.info(f"WebSocket desconectado para {client_id}")
    finally:
        if client_id in websocket_connections:
            websocket_connections[client_id].discard(websocket)
            if len(websocket_connections[client_id]) == 0:
                # Não remover o conjunto vazio, pode ser útil manter
                pass


async def poll_messages(client_id: str):
    """Polling de mensagens em background - uma task por cliente"""
    while client_id in active_sessions:
        try:
            logic = active_sessions[client_id]
            await logic.poll_blobs()
            # O poll_blobs já tem sleep interno, não precisa aqui
        except Exception as e:
            log.error(f"Erro no polling para {client_id}: {e}")
            await asyncio.sleep(1)


if __name__ == "__main__":
    import uvicorn

    log.info("=" * 70)
    log.info("Servidor Web Bridge iniciando...")
    log.info("Suporta múltiplos clientes simultâneos")
    log.info("=" * 70)

    uvicorn.run(app, host="0.0.0.0", port=8000)
