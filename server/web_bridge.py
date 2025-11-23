"""
Servidor HTTP/WebSocket bridge para interface React.
Faz proxy entre o React e o servidor TLS existente.
Suporta múltiplos clientes simultâneos.

Este bridge foi projetado exclusivamente para uso local em loopback, com
CORS totalmente liberado e validação TLS baseada apenas nos certificados
locais gerados na raiz do projeto.
"""

import asyncio
import json
import logging
import secrets
import sys
import time
from os import getenv
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from pydantic import BaseModel, EmailStr

sys.path.insert(0, str(Path(__file__).parent.parent))

from client.chat_client_logic import ChatLogic
from server.email_service import (
    EmailDeliveryError,
    EmailService,
    EmailServiceError,
    SMTPSettings,
)
from server.user_store import UserStore
from server.db_core import DEFAULT_DB_PATH

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("web_bridge")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

ENV_MODE = getenv("ENV", "development").lower()


def _parse_int_env(var_name: str, default: int) -> int:
    raw_value = getenv(var_name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:  # noqa: TRY003
        raise RuntimeError(f"{var_name} deve ser um inteiro válido") from exc


app = FastAPI(title="Chat Seguro Web Bridge")


# CORS para permitir conexões do React
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def healthcheck():
    return {"status": "ok", "mode": ENV_MODE, "sessions": len(active_sessions)}

# Armazenamento de sessões ativas (suporta múltiplos clientes)
active_sessions: dict[str, ChatLogic] = {}
websocket_connections: dict[str, set[WebSocket]] = {}
pending_mfa: dict[str, dict] = {}
session_tokens: dict[str, dict] = {}

# Configuração do servidor TLS (uso apenas local/loopback)
SERVER_HOST = "127.0.0.1"
SERVER_PORT = _parse_int_env("TLS_PORT", 4433)
CACERT = PROJECT_ROOT / "cert.pem"

user_store = UserStore(DEFAULT_DB_PATH)


def _build_email_service() -> EmailService:
    env_mode = getenv("ENV", "development")
    raw_port = getenv("EMAIL_PORT")
    port = None
    if raw_port:
        try:
            port = int(raw_port)
        except ValueError as exc:  # noqa: TRY003
            raise RuntimeError("EMAIL_PORT deve ser um inteiro válido") from exc
    settings = SMTPSettings(
        host=getenv("EMAIL_HOST"),
        port=port,
        username=getenv("EMAIL_USER"),
        password=getenv("EMAIL_PASSWORD"),
        sender=getenv("EMAIL_FROM"),
    )
    return EmailService(settings=settings, env_mode=env_mode)


email_service = _build_email_service()
MFA_TOKEN_TTL = 300  # 5 minutos
SESSION_TOKEN_BYTES = 48


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

    logic = ChatLogic(SERVER_HOST, SERVER_PORT, str(CACERT), client_id)

    def on_new_message(peer, message):
        notify_websockets(client_id, "new_message", {"peer": peer, "message": message})

    def on_update_ui():
        notify_websockets(client_id, "update_ui", {})

    logic.on_new_message = on_new_message
    logic.on_update_ui = on_update_ui

    try:
        publish_response = await logic.publish_key()
    except Exception as exc:  # noqa: BLE001
        log.error("Erro ao publicar chave para %s: %s", client_id, exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "Não foi possível se conectar ao servidor TLS. "
                "Verifique se ele está em execução."
            ),
        ) from exc

    if publish_response.get("status") != "ok":
        reason = publish_response.get("reason") or "Falha ao publicar chave"
        log.error("Publicação de chave falhou para %s: %s", client_id, reason)
        raise HTTPException(
            status_code=503,
            detail=f"Falha ao conectar ao servidor TLS: {reason}",
        )

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


def _issue_session_token(client_id: str) -> str:
    """Cria um token de sessão e remove anteriores para o mesmo cliente."""

    for token, session in list(session_tokens.items()):
        if session.get("client_id") == client_id:
            session_tokens.pop(token, None)

    token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    session_tokens[token] = {"client_id": client_id, "issued_at": time.time()}
    return token


def _require_session(request: Request) -> tuple[str, str]:
    """Obtém o token de sessão a partir de headers/cookies e valida."""

    token = request.headers.get("X-Session-Token")
    if not token:
        token = request.cookies.get("session_token")

    if not token:
        log.warning(
            "Tentativa de acesso ao endpoint %s sem token de sessão", request.url.path
        )
        raise HTTPException(status_code=401, detail="Token de sessão ausente")

    session = session_tokens.get(token)
    if not session:
        log.warning(
            "Tentativa de acesso ao endpoint %s com token inválido",
            request.url.path,
        )
        raise HTTPException(status_code=401, detail="Token de sessão inválido")

    return token, session["client_id"]


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
    try:
        email_service.send_mfa_code(user["email"], code)
    except (EmailDeliveryError, EmailServiceError) as exc:
        pending_mfa.pop(token, None)
        log.error("Falha ao enviar código MFA para %s: %s", user["email"], exc)
        raise HTTPException(
            status_code=500,
            detail="Falha ao enviar código MFA por e-mail",
        ) from exc
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
    session_token = _issue_session_token(info["client_id"])
    response_payload = {"status": "ok", **session_info, "session_token": session_token}
    return JSONResponse(response_payload)


@app.post("/api/logout")
async def logout(request: Request):
    """Logout e desconexão"""
    token, client_id = _require_session(request)

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

    session_tokens.pop(token, None)

    return JSONResponse({"status": "ok", "message": "Logout realizado"})


@app.get("/api/conversations")
async def get_conversations(request: Request):
    """Lista todas as conversas (clientes e grupos)"""
    _, client_id = _require_session(request)

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
async def send_message(payload: SendMessageRequest, request: Request):
    """Envia uma mensagem privada ou de grupo"""
    _, client_id = _require_session(request)

    if client_id not in active_sessions:
        raise HTTPException(status_code=401, detail="Não autenticado")

    logic = active_sessions[client_id]
    to = payload.to

    if to not in logic.conversations:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    conv_type = logic.conversations[to]["type"]
    success = False
    error = ""

    # Adicionar mensagem ao histórico local antes de enviar
    import time

    ts = time.strftime("%H:%M:%S")
    logic.conversations[to]["history"].append((ts, client_id, payload.message))
    # Salvar estado em background para não bloquear
    asyncio.create_task(asyncio.to_thread(logic.save_state))

    if conv_type == "private":
        success, error = await logic.send_private_message(to, payload.message)
    elif conv_type == "group":
        success, error = await logic.send_group_message(to, payload.message)
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
        {"to": to, "message": payload.message, "timestamp": ts},
    )

    return JSONResponse({"status": "ok", "message": "Mensagem enviada"})


class CreateGroupRequest(BaseModel):
    group_id: str
    members: list[str]


@app.post("/api/create-group")
async def create_group(payload: CreateGroupRequest, request: Request):
    """Cria um novo grupo"""
    _, client_id = _require_session(request)

    if client_id not in active_sessions:
        raise HTTPException(status_code=401, detail="Não autenticado")

    logic = active_sessions[client_id]
    await logic.create_group(payload.group_id, payload.members)
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
        "WebSocket conectado para %s. Total de conexões: %d",
        client_id,
        len(websocket_connections[client_id]),
    )

    try:
        while True:
            # Manter conexão viva e receber mensagens (se necessário)
            await websocket.receive_text()
            # Por enquanto, apenas ecoamos para manter conexão
            await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        log.info("WebSocket desconectado para %s", client_id)
    finally:
        if client_id in websocket_connections:
            websocket_connections[client_id].discard(websocket)
            if len(websocket_connections[client_id]) == 0:
                # Não remover o conjunto vazio, pode ser útil manter
                pass


async def poll_messages(client_id: str) -> None:
    """Polling de mensagens em background - uma task por cliente."""
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
