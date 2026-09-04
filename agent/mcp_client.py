"""Cliente MCP: conecta ao servidor por stdio e expõe as ferramentas.

É aqui que o trace é capturado. Cada `call` devolve um ToolCall pronto, o que
mantém o servidor sem estado de experimento e garante que os dois braços
registrem exatamente da mesma forma.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent.trace import Mode, ToolCall


def _split_step(step: str | None) -> tuple[str | None, str | None]:
    """`"GET /assets/asset_G501"` -> `("GET", "/assets/asset_G501")`."""
    if not step or " " not in step:
        return None, None
    method, _, path = step.partition(" ")
    return method, path


@asynccontextmanager
async def connect(api_base: str, seed: str | None = None, include_impact: bool = False):
    env = dict(os.environ)
    env["TRACTIAN_API"] = api_base
    if seed:
        env["TRACTIAN_SEED"] = seed
    if include_impact:
        env["INCLUDE_IMPACT"] = "1"

    params = StdioServerParameters(
        command=sys.executable, args=["-m", "agent.mcp_server"], env=env
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield MCPTools(session)


class MCPTools:
    def __init__(self, session: ClientSession) -> None:
        self.session = session
        self._tools: list[Any] = []

    async def list_tools(self) -> list[Any]:
        """Nome nao pode ser `list`: dentro da classe ele sombreia o builtin e
        quebra as anotacoes `list[...]` dos outros metodos."""
        if not self._tools:
            self._tools = (await self.session.list_tools()).tools
        return self._tools

    async def openai_schema(self) -> list[dict[str, Any]]:
        """Converte para o formato de tool da API compatível com OpenAI."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in await self.list_tools()
        ]

    async def call(self, name: str, arguments: dict[str, Any],
                   role: str = "react", role_instance: int = 0) -> ToolCall:
        """Executa a ferramenta e devolve um ToolCall pronto para o trace.

        Nunca levanta: falha de transporte ou de protocolo vira `ok=False`, para
        que uma execução degradada continue produzindo trace analisável.
        """
        started = time.perf_counter()
        try:
            result = await self.session.call_tool(name, arguments or {})
            # `content` pode trazer imagem, audio ou recurso, que nao tem
            # `.text`. Este servidor so devolve texto, mas assumir isso faria
            # uma resposta inesperada virar AttributeError em vez de erro legivel.
            first = result.content[0] if result.content else None
            raw = getattr(first, "text", None) or "{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                # O SDK devolve texto puro quando a própria camada MCP recusa
                # (ferramenta inexistente, argumento inválido). Vira erro
                # estruturado em vez de estourar como falha de parsing.
                payload = {"_ok": False, "error": raw.strip()}
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira trace, não crash
            return ToolCall(
                step=0, tool=name, arguments=arguments or {},
                ok=False, error=str(exc), role=role, role_instance=role_instance,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

        method, path = _split_step(payload.get("_http_step"))
        raw_mode = payload.get("mode")

        return ToolCall(
            step=0,  # numerado por Trace.record()
            tool=name,
            arguments=arguments or {},
            role=role,
            role_instance=role_instance,
            http_method=method,
            http_path=path,
            mode=Mode(raw_mode) if raw_mode in Mode._value2member_map_ else None,
            notes=payload.get("notes"),
            data=payload.get("data"),
            ok=bool(payload.get("_ok")),
            error=None if payload.get("_ok") else str(payload.get("error")),
            is_impact=bool(payload.get("_is_impact")),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
