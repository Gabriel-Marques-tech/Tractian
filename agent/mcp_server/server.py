"""Servidor MCP que expõe a API industrial da TRACTIAN como ferramentas.

Transporte stdio: sobe como subprocesso, funciona igual no laptop e dentro do
notebook do Colab, sem porta exposta — o que importa porque os termos do Colab
proíbem usar o runtime como servidor para fora.

O servidor não guarda estado de experimento. A captura do trace acontece no
cliente, envolvendo cada chamada.

O SDK (mcp 2.x) deriva o schema de cada ferramenta da assinatura da função,
então as funções são geradas em tempo de execução a partir do contrato OpenAPI.
É por isso que existe `_build_tool_function`: o contrato continua sendo a fonte
única de verdade, e nenhum schema é escrito à mão.

## O gate das ações de impacto

Vive aqui, e não no agente. Segurança imposta por prompt não é segurança: um
modelo pequeno ignorando instrução é o caso esperado. Além disso os dois braços
do experimento precisam da mesma superfície de ferramentas para a comparação
isolar a arquitetura, e a recusa só vira métrica se acontecer num lugar que a
registra.

Duas verificações, com autoridades diferentes:

- **Justificativa**: validada aqui antes de sair para a rede. O contrato OpenAPI
  declara `body: dict[str, Any]` e portanto não expõe propriedade nenhuma — sem
  injetar `justification` no schema da ferramenta, o modelo não teria como saber
  que precisa justificar, e toda ação falharia por 400. A API revalida; esta
  checagem é guarda antecipada, não a autoridade.
- **Permissão**: decidida pela API, que devolve 403. O servidor apenas traduz
  esse 403 em recusa estruturada. Replicar a matriz de permissões aqui criaria
  uma segunda fonte de verdade que divergiria em silêncio.

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

from agent.toolgen import (
    DEFAULT_API,
    JUSTIFICATION_ARG,
    MIN_JUSTIFICATION,
    ToolSpec,
    describe,
    execute,
    load_specs,
)

API_BASE = os.environ.get("TRACTIAN_API", DEFAULT_API)
INCLUDE_IMPACT = os.environ.get("INCLUDE_IMPACT") == "1"
SEED = os.environ.get("TRACTIAN_SEED") or None
USER_ID = os.environ.get("TRACTIAN_USER") or None


def _refusal(spec: ToolSpec, arguments: dict[str, Any], reason: str) -> str:
    """Recusa do gate: evento de segurança, não falha de execução.

    `_refused` é distinto de `_ok: false` de propósito. Erro de execução e
    recusa deliberada têm causas diferentes, e o scorer as conta em métricas
    diferentes (objeto de análise 6 contra 7).
    """
    return json.dumps(
        {
            "_http_step": spec.http_step(arguments),
            "_ok": False,
            "_is_impact": spec.is_impact,
            "_refused": True,
            "_refusal_reason": reason,
            "error": reason,
        },
        ensure_ascii=False,
        default=str,
    )


async def _dispatch(spec: ToolSpec, arguments: dict[str, Any], *,
                    api_base: str, seed: str | None, user_id: str | None) -> str:
    """Aplica o gate e executa. Devolve o envelope serializado.

    `_http_step` viaja junto para o cliente montar o trace sem reconstruir a
    URL, e é a string que o scorer compara com `expected_path[].step`.
    """
    supplied = {k: v for k, v in arguments.items() if v is not None}
    justification = str(supplied.pop(JUSTIFICATION_ARG, "") or "").strip()

    if spec.is_impact:
        if not justification:
            return _refusal(spec, supplied, "acao de impacto exige justificativa")
        if len(justification) < MIN_JUSTIFICATION:
            return _refusal(
                spec,
                supplied,
                f"justificativa curta demais: {len(justification)} caracteres, "
                f"minimo {MIN_JUSTIFICATION}",
            )
        supplied[JUSTIFICATION_ARG] = justification

    # A identidade vem da configuração da execução, nunca do modelo: deixar o
    # agente escolher o próprio usuário anularia a checagem de permissão.
    if user_id and any(
        spec.alias.get(p, p) == "x-user-id" for p in spec.header_params
    ):
        for p in spec.header_params:
            if spec.alias.get(p, p) == "x-user-id":
                supplied[p] = user_id

    ok, payload = await asyncio.to_thread(execute, spec, supplied, api_base, seed)

    # 403 é decisão de permissão da API, não falha de execução. Traduzido para o
    # mesmo formato de recusa do gate, para que o scorer conte os dois juntos.
    if not ok and isinstance(payload, dict) and payload.get("status") == 403:
        detalhe = payload.get("error")
        if isinstance(detalhe, dict):
            detalhe = detalhe.get("message") or detalhe
        return _refusal(spec, supplied, f"permissao negada: {detalhe}")

    envelope = {
        "_http_step": spec.http_step(supplied),
        "_ok": ok,
        "_is_impact": spec.is_impact,
        "_refused": False,
        **(payload if isinstance(payload, dict) else {"data": payload}),
    }
    return json.dumps(envelope, ensure_ascii=False, default=str)


def _build_tool_function(spec: ToolSpec, *, api_base: str, seed: str | None,
                         user_id: str | None) -> Callable[..., Any]:
    """Cria uma função async com a assinatura que o schema da ferramenta exige."""
    required = list(dict.fromkeys(spec.path_params + spec.body_required))
    optional = [
        p
        for p in spec.query_params + spec.header_params + list(spec.body_props)
        if p not in required
    ]

    # `justification` já vem de `spec.body_required`: o `toolgen` a declara para
    # as ações de impacto, porque o contrato OpenAPI a omite.

    # A identidade é injetada pelo servidor a partir da configuração; expô-la ao
    # modelo abriria caminho para o agente escolher um usuário mais permissivo.
    optional = [p for p in optional if spec.alias.get(p, p) != "x-user-id"]

    parts = [f"{p}: str" for p in required]
    parts += [f"{p}: str | None = None" for p in optional]
    all_params = required + optional

    source = (
        f"async def {spec.name}({', '.join(parts)}) -> str:\n"
        f"    return await _dispatch(\n"
        f"        _spec, {{{', '.join(f'{p!r}: {p}' for p in all_params)}}},\n"
        f"        api_base=_api_base, seed=_seed, user_id=_user_id,\n"
        f"    )\n"
    )

    namespace: dict[str, Any] = {
        "_dispatch": _dispatch, "_spec": spec,
        "_api_base": api_base, "_seed": seed, "_user_id": user_id,
    }
    exec(compile(source, f"<tool:{spec.name}>", "exec"), namespace)  # noqa: S102

    fn = namespace[spec.name]
    fn.__doc__ = describe(spec)
    return fn


def build(*, include_impact: bool = False, user_id: str | None = None,
          seed: str | None = None, api_base: str | None = None) -> MCPServer:
    """Monta um servidor configurado. Fábrica, para o teste não depender de env."""
    base = api_base or API_BASE
    mcp = MCPServer("tractian-industrial")

    for spec in load_specs(base):
        if spec.is_impact and not include_impact:
            continue
        mcp.add_tool(
            _build_tool_function(spec, api_base=base, seed=seed, user_id=user_id),
            name=spec.name,
            description=describe(spec),
        )
    return mcp


def from_environment() -> MCPServer:
    """Servidor configurado pelo ambiente, para o `__main__`."""
    return build(
        include_impact=INCLUDE_IMPACT,
        user_id=USER_ID,
        seed=SEED,
        api_base=API_BASE,
    )
