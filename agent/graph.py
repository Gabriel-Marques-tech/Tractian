"""Braço B: grafo LangGraph com papéis especializados.

Primeira fatia (issue #7): executor, planejador e orquestrador de ferramentas.
Três porque é o mínimo que resolve um caso — algo que planeje, algo que chame
ferramenta, algo que roteie. Os outros três papéis entram um por ticket.

Usa o mesmo servidor MCP, o mesmo modelo e a mesma seed do braço A, e emite o
mesmo `Trace`. A comparação só isola a arquitetura se tudo o mais for idêntico.

Cada `ToolCall` carrega o papel que a originou, o que permite ao relatório
mostrar de onde veio cada passo da trajetória.

Os prompts de papel são curtos de propósito. Medido no braço A: acima de ~2000
tokens de prompt, `qwen2.5:1.5b` abandona a emissão estruturada de `tool_calls`
e volta a escrever a chamada em prosa. Um grafo de seis papéis com prompts
longos estouraria esse teto em todo nó.
"""

from __future__ import annotations

import json
import os
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agent.llm import LLMClient
from agent.mcp_client import connect
from agent.react import _observation
from agent.trace import Arm, RunConfig, StopReason, Trace

PLANNER_PROMPT = """Voce planeja investigacoes de suporte industrial na TRACTIAN.

Recebe um chamado e lista, em no maximo tres linhas, o que precisa ser
estabelecido para responder. Nao chame ferramentas. Nao responda ao cliente.

Lembre: o cadastro do ativo nao explica falha. O limiar de RMS vem do baseline.
Insight ausente pode ser modelo atrasado, sem cobertura, ou dado que nao chegou.
"""

ORCHESTRATOR_PROMPT = """Voce executa consultas na plataforma industrial da TRACTIAN.

Recebe um plano de investigacao e o que ja foi coletado.

1. Chame a ferramenta de verdade. Nunca escreva a chamada como texto.
2. Uma consulta so raramente basta. Siga o plano ate ter a evidencia.
3. Toda leitura traz `mode`: complete, partial, inconclusive, conflict,
   unavailable. Ausencia de dado NAO e ausencia de problema.
4. Acao de impacto exige justificativa de 20 caracteres ou mais.

Quando a evidencia do plano estiver coberta, responda ao cliente em portugues,
citando o dado que sustenta cada afirmacao.
"""


class GraphState(TypedDict, total=False):
    """Estado que atravessa o grafo."""

    case: dict[str, Any]
    plan: str
    messages: list[dict[str, Any]]
    trace: Trace
    finished: bool


def _case_brief(case: dict[str, Any]) -> str:
    partes = [f"CHAMADO: {case['message']}"]
    for chave, rotulo in (("asset_id", "ATIVO"), ("company_id", "EMPRESA"), ("id", "CASO")):
        if case.get(chave):
            partes.append(f"{rotulo}: {case[chave]}")
    return "\n".join(partes)


async def run_case_graph(case: dict[str, Any], config: RunConfig,
                         verbose: bool = False, client: Any | None = None) -> Trace:
    """Executa um caso pelo braço B. Nunca levanta: falha vira stop_reason."""
    trace = Trace(
        case_id=case["id"],
        ticket_id=case.get("ticket_id"),
        message=case["message"],
        config=config,
    )

    if client is None:
        client = LLMClient(base_url=config.model_base_url, model=config.model)

    async with connect(config.api_base_url, seed=config.seed,
                       include_impact=True, user_id=config.user_id) as tools:
        schema = await tools.openai_schema()

        async def planejador(state: GraphState) -> GraphState:
            """Interpreta o chamado e diz o que precisa ser estabelecido."""
            resposta = await client.chat(
                [
                    {"role": "system", "content": PLANNER_PROMPT},
                    {"role": "user", "content": _case_brief(state["case"])},
                ]
            )
            trace.model_calls += 1
            trace.prompt_tokens += resposta.prompt_tokens or 0
            trace.completion_tokens += resposta.completion_tokens or 0

            plano = (resposta.content or "").strip()
            if verbose:
                print(f"  [planejador] {plano[:120]}")

            return {
                "plan": plano,
                "messages": [
                    {"role": "system", "content": ORCHESTRATOR_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"{_case_brief(state['case'])}\n\n"
                            f"PLANO DE INVESTIGACAO:\n{plano}"
                        ),
                    },
                ],
            }

        async def orquestrador(state: GraphState) -> GraphState:
            """Monta argumentos, chama o servidor MCP e devolve as observações."""
            mensagens = state["messages"]
            resposta = await client.chat(mensagens, schema)

            trace.model_calls += 1
            trace.prompt_tokens += resposta.prompt_tokens or 0
            trace.completion_tokens += resposta.completion_tokens or 0

            if not resposta.tool_calls:
                trace.finish(StopReason.ANSWERED, resposta.content or "")
                if verbose:
                    print("  [orquestrador] resposta final")
                return {"finished": True}

            mensagens = mensagens + [
                {
                    "role": "assistant",
                    "content": resposta.content or "",
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments, ensure_ascii=False),
                            },
                        }
                        for c in resposta.tool_calls
                    ],
                }
            ]

            for pedido in resposta.tool_calls:
                if len(trace.steps) >= config.max_steps:
                    break
                chamada = await tools.call(
                    pedido.name, pedido.arguments, role="orquestrador_tools"
                )
                chamada.recovered_from_text = pedido.recovered
                registrada = trace.record(chamada)

                if verbose:
                    modo = registrada.mode.value if registrada.mode else "-"
                    print(f"  [orquestrador] {registrada.as_path_step()} mode={modo}")

                mensagens = mensagens + [
                    {
                        "role": "tool",
                        "tool_call_id": pedido.id,
                        "content": _observation(registrada),
                    }
                ]

            return {"messages": mensagens, "finished": False}

        def executor(state: GraphState) -> str:
            """Roteia. É o papel que decide continuar ou encerrar."""
            if state.get("finished"):
                return END
            if trace.model_calls >= config.max_model_calls:
                trace.finish(StopReason.MAX_MODEL_CALLS, "limite de chamadas atingido")
                return END
            if len(trace.steps) >= config.max_steps:
                trace.finish(StopReason.MAX_STEPS, "limite de passos atingido")
                return END
            return "orquestrador"

        grafo = StateGraph(GraphState)
        grafo.add_node("planejador", planejador)
        grafo.add_node("orquestrador", orquestrador)
        grafo.add_edge(START, "planejador")
        grafo.add_edge("planejador", "orquestrador")
        grafo.add_conditional_edges(
            "orquestrador", executor, {"orquestrador": "orquestrador", END: END}
        )

        try:
            await grafo.compile().ainvoke(
                {"case": case, "messages": [], "trace": trace, "finished": False},
                {"recursion_limit": config.max_steps * 3 + 10},
            )
        except Exception as exc:  # noqa: BLE001
            trace.error = str(exc)
            if trace.stop_reason is None:
                trace.finish(StopReason.ERROR)

    if trace.stop_reason is None:
        trace.finish(StopReason.ERROR)
    return trace


def multiagent_config(**overrides: Any) -> RunConfig:
    """Config padrão do braço B: idêntica à do A, exceto o braço."""
    from agent.react import baseline_config

    base = baseline_config().model_dump()
    base["arm"] = Arm.MULTI_AGENT
    base.update(overrides)
    return RunConfig(**base)
