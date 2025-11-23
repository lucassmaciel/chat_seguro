"""Ponto de entrada para execução no Railway.

- Sobe o servidor TLS interno (porta configurável via TLS_PORT)
- Gera cert.pem/key.pem automaticamente se não existirem
- Inicia o FastAPI (server.web_bridge) na porta `$PORT`
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import uvicorn

from server import server as tls_server
from server.server import init_pubkeys


def _ensure_certificates(cert_path: Path, key_path: Path) -> None:
    if cert_path.exists() and key_path.exists():
        return

    print("[railway] Gerando certificados TLS autoassinados...")
    subprocess.run(
        [sys.executable, "server/generate_cert.py"],
        check=True,
    )


async def _run_tls_server(cert_path: Path, key_path: Path) -> None:
    init_pubkeys()
    tls_host = os.getenv("TLS_HOST", "0.0.0.0")
    tls_port = int(os.getenv("TLS_PORT", "4433"))
    await tls_server.main(str(cert_path), str(key_path), host=tls_host, port=tls_port)


async def _run_web_bridge() -> None:
    port = int(os.getenv("PORT", "8000"))
    config = uvicorn.Config(
        "server.web_bridge:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    cert_path = Path(os.getenv("TLS_CERT_FILE", "cert.pem"))
    key_path = Path(os.getenv("TLS_KEY_FILE", "key.pem"))
    _ensure_certificates(cert_path, key_path)

    tls_task = asyncio.create_task(_run_tls_server(cert_path, key_path))
    web_task = asyncio.create_task(_run_web_bridge())

    done, pending = await asyncio.wait({tls_task, web_task}, return_when=asyncio.FIRST_EXCEPTION)
    for task in pending:
        task.cancel()
    for task in done:
        task.result()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[railway] Encerrado pelo usuário")
