"""Fixtures de teste.

O seam sob teste é o **servidor MCP**, exercitado por uma sessão de cliente MCP
real ligada por streams em memória. Nada aqui alcança função interna do servidor:
se um teste passa, um cliente MCP de verdade também consegue.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

API_BASE_URL = os.environ.get("TRACTIAN_API_URL", "http://localhost:8000")


def api_is_up() -> bool:
    try:
        return httpx.get(f"{API_BASE_URL}/openapi.json", timeout=2.0).status_code == 200
    except Exception:
        return False


requires_api = pytest.mark.skipif(
    not api_is_up(),
    reason=f"API industrial não está no ar em {API_BASE_URL} (rode `make up`)",
)


@asynccontextmanager
async def mcp_session(server) -> AsyncIterator[ClientSession]:
    """Liga um ClientSession ao servidor por streams em memória."""
    import anyio

    async with create_client_server_memory_streams() as (client_streams, server_streams):
        client_read, client_write = client_streams
        server_read, server_write = server_streams

        low = server._lowlevel_server

        async with anyio.create_task_group() as tg:
            tg.start_soon(
                lambda: low.run(
                    server_read,
                    server_write,
                    low.create_initialization_options(),
                    raise_exceptions=True,
                )
            )
            async with ClientSession(client_read, client_write) as session:
                await session.initialize()
                yield session
            tg.cancel_scope.cancel()


@pytest.fixture
def anyio_backend() -> str:
    """Roda os testes async só em asyncio; trio não é dependência do projeto."""
    return "asyncio"
