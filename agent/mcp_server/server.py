"""Servidor MCP que expõe a API industrial da TRACTIAN como ferramentas.

Transporte stdio: sobe como subprocesso, funciona igual no laptop e dentro do
notebook do Colab, sem porta exposta — o que importa porque os termos do Colab
proíbem usar o runtime como servidor para fora.

Escopo desta versão (issue #1): as 13 operações de leitura. As 5 ações de
impacto entram na #3, junto com o gate de justificativa.

O servidor não guarda estado de experimento. A captura do trace acontece no
cliente, envolvendo cada chamada.

O SDK (mcp 2.x) deriva o schema de cada ferramenta da assinatura da função,
então as funções são geradas em tempo de execução a partir do contrato OpenAPI.
É por isso que existe `_build_tool_function`: o contrato continua sendo a fonte
única de verdade, e nenhum schema é escrito à mão.

Uso:
    python -m agent.mcp_server              # 13 ferramentas de leitura
    INCLUDE_IMPACT=1 python -m agent.mcp_server
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Callable

from mcp.server.mcpserver import MCPServer

from agent.toolgen import DEFAULT_API, ToolSpec, describe, execute, load_specs

API_BASE = os.environ.get("TRACTIAN_API", DEFAULT_API)
INCLUDE_IMPACT = os.environ.get("INCLUDE_IMPACT") == "1"
SEED = os.environ.get("TRACTIAN_SEED") or None

server = MCPServer("tractian-industrial")


async def _dispatch(spec: ToolSpec, arguments: dict[str, Any]) -> str:
    """Executa a operação e devolve o envelope serializado.

    `_http_step` viaja junto para o cliente montar o trace sem reconstruir a
    URL, e é a string que o scorer compara com `expected_path[].step`.
    """
    supplied = {k: v for k, v in arguments.items() if v is not None}
    ok, payload = await asyncio.to_thread(execute, spec, supplied, API_BASE, SEED)

    envelope = {
        "_http_step": spec.http_step(supplied),
        "_ok": ok,
        "_is_impact": spec.is_impact,
        **(payload if isinstance(payload, dict) else {"data": payload}),
    }
    return json.dumps(envelope, ensure_ascii=False, default=str)


def _build_tool_function(spec: ToolSpec) -> Callable[..., Any]:
    """Cria uma função async com a assinatura que o schema da ferramenta exige."""
    required = list(dict.fromkeys(spec.path_params + spec.body_required))
    optional = [
        p
        for p in spec.query_params + spec.header_params + list(spec.body_props)
        if p not in required
    ]

    parts = [f"{p}: str" for p in required]
    parts += [f"{p}: str | None = None" for p in optional]
    all_params = required + optional

    source = (
        f"async def {spec.name}({', '.join(parts)}) -> str:\n"
        f"    return await _dispatch(_spec, {{{', '.join(f'{p!r}: {p}' for p in all_params)}}})\n"
    )

    namespace: dict[str, Any] = {"_dispatch": _dispatch, "_spec": spec}
    exec(compile(source, f"<tool:{spec.name}>", "exec"), namespace)  # noqa: S102

    fn = namespace[spec.name]
    fn.__doc__ = describe(spec)
    return fn


def register_tools(mcp: MCPServer) -> list[ToolSpec]:
    specs = [s for s in load_specs(API_BASE) if INCLUDE_IMPACT or not s.is_impact]
    for spec in specs:
        mcp.add_tool(
            _build_tool_function(spec),
            name=spec.name,
            description=describe(spec),
        )
    return specs
