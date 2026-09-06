"""Braço A: agente ReAct de nó único sobre o servidor MCP.

Este é o **baseline honesto** do experimento, não um espantalho. Recebe as
mesmas ferramentas, o mesmo servidor MCP e a mesma seed que o braço B. Se o
baseline fosse fraco de propósito, a comparação entre arquiteturas não valeria
nada.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from agent.llm import LLMClient
from agent.mcp_client import connect
from agent.trace import Arm, RunConfig, StopReason, Trace

SYSTEM_PROMPT = """Voce e um agente de suporte tecnico industrial da TRACTIAN.

Investiga chamados usando as ferramentas, que consultam a plataforma real.

1. Chame a ferramenta de verdade. Nunca escreva a chamada como texto.
2. Uma consulta so raramente basta. O cadastro do ativo nao explica falha.
3. Toda leitura traz `mode`: complete, partial, inconclusive, conflict,
   unavailable. Ausencia de dado NAO e ausencia de problema.
4. Fundamente cada afirmacao no dado que voltou. Nao invente.
5. Decida entre orientar, agir ou escalar.
6. Responda em portugues, direto.

Pare de chamar ferramentas so quando puder citar o dado que sustenta cada
afirmacao.

O baseline e o estado normal aprendido do ativo: `learning`, `established` ou
`invalidated`. O limiar de RMS vem dele. Insight ausente pode ser modelo
atrasado, sem cobertura, ou dado que nao chegou.
"""
"""Tamanho do prompt e escolha de ferramenta foram medidos, nao adivinhados.

Contra o caso TKT-INV-05, cujo gabarito comeca em `GET /assets/{id}/rms`:

    596 chars  -> tool call estruturada, ferramenta errada (`get_asset`)
    797 chars  -> tool call estruturada, ferramenta certa  (`get_rms`)
    2367 chars -> ferramenta certa, mas emitida como TEXTO

O conteudo de dominio (baseline, limiar, insight ausente) e o que corrige a
escolha. O excesso de texto e o que quebra a emissao estruturada: acima de
~2000 tokens de prompt, `qwen2.5:1.5b` volta a escrever a chamada em prosa.

Os conceitos vem de `STUDENT-GUIDE.md` secao 6, que documenta o dominio para
quem constroi o agente. Nao sao o gabarito: nenhuma sequencia de endpoints e
mencionada, so o que precisa ser estabelecido para concluir.
"""


def _observation(call) -> str:
    """O que o modelo enxerga de volta. `mode` e `notes` nunca são omitidos."""
    if not call.ok:
        return json.dumps({"erro": call.error}, ensure_ascii=False)
    return json.dumps(
        {
            "mode": call.mode.value if call.mode else None,
            "notes": call.notes,
            "data": call.data,
        },
        ensure_ascii=False,
        default=str,
    )[:4000]


def _framing(case: dict[str, Any]) -> str:
    """Enquadra o chamado como tarefa.

    Medido nesta maquina: `qwen2.5:1.5b` responde pergunta com prosa e
    instrucao com ferramenta. Os chamados chegam como pergunta ("Cade o
    diagnostico?"), entao o enquadramento e parte do agente, nao maquiagem do
    benchmark.

    A versao anterior terminava com "Comece consultando os dados do ativo".
    O smoke test da issue #6 mostrou que o modelo tratava essa frase como a
    tarefa inteira: consultava o cadastro, relatava, encerrava. Nove execucoes,
    uma unica chamada de ferramenta cada, contra gabaritos de quatro passos.

    A instrucao agora nomeia o que precisa ser estabelecido, nao um primeiro
    passo que possa ser confundido com o unico.
    """
    context = ""
    if case.get("asset_id"):
        context += f"\nATIVO: {case['asset_id']}"
    if case.get("company_id"):
        context += f"\nEMPRESA: {case['company_id']}"
    if case.get("id"):
        context += f"\nCASO: {case['id']}"

    return (
        "Investigue o chamado abaixo usando as ferramentas disponiveis.\n\n"
        f"CHAMADO: {case['message']}{context}\n\n"
        "Levante a evidencia necessaria antes de responder. Uma consulta so "
        "raramente basta: cruze as fontes que a pergunta exige e so entao "
        "conclua, citando o dado que sustenta cada afirmacao."
    )


# Fixa em 0: o experimento mede arquitetura, e amostragem aleatoria adicionaria
# uma fonte de variancia que nao e a variavel sob estudo.
TEMPERATURE = 0.0

TRUNCATED_NOTICE = (
    "Investigacao encerrada antes de concluir: o limite de passos do agente foi "
    "atingido. O que foi levantado ate aqui esta acima; o caso precisa de "
    "analise humana para fechar."
)


def _halt(trace: Trace, reason: StopReason, last_content: str) -> None:
    """Encerra por limite, entregando o que houver em vez de silêncio."""
    partial = (last_content or "").strip()
    if partial:
        trace.finish(reason, f"{partial}\n\n{TRUNCATED_NOTICE}")
    else:
        trace.finish(reason, TRUNCATED_NOTICE)


def baseline_config(**overrides: Any) -> RunConfig:
    """Config padrão do braço A, sobrescrevível por ambiente ou argumento."""
    defaults: dict[str, Any] = {
        "arm": Arm.BASELINE,
        "model": os.environ.get("AGENT_MODEL", "qwen2.5:1.5b"),
        "model_base_url": os.environ.get("AGENT_BASE_URL", "http://localhost:11434"),
        "api_base_url": os.environ.get("TRACTIAN_API", "http://localhost:8000"),
        "seed": os.environ.get("AGENT_SEED", "demo"),
        "max_steps": int(os.environ.get("AGENT_MAX_STEPS", "10")),
        "max_model_calls": int(os.environ.get("AGENT_MAX_MODEL_CALLS", "12")),
    }
    defaults.update(overrides)
    return RunConfig(**defaults)


async def run_case(case: dict[str, Any], config: RunConfig,
                   verbose: bool = False, client: Any | None = None) -> Trace:
    """Executa um caso e devolve o Trace. Nunca levanta: falha vira stop_reason.

    `client` é qualquer objeto com `chat(messages, tools) -> Completion`. Existe
    para o teste injetar um modelo roteirizado: o laço fica exercitável contra o
    servidor MCP e a API reais sem depender de um LLM, que seria lento e não
    determinístico. Em produção fica `None` e o cliente sai da config.
    """
    trace = Trace(
        case_id=case["id"],
        ticket_id=case.get("ticket_id"),
        message=case["message"],
        config=config,
    )

    if client is None:
        # Nada de ambiente aqui. Tudo que muda o comportamento do modelo precisa
        # estar no RunConfig, porque e o RunConfig que vai para o trace: um knob
        # lido do ambiente produziria duas execucoes diferentes com traces de
        # config identica, e a comparacao entre bracos deixaria de ser honesta.
        # O backend e inferido de `model_base_url`, que esta na config.
        client = LLMClient(
            base_url=config.model_base_url,
            model=config.model,
            temperature=TEMPERATURE,
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _framing(case)},
    ]

    # Ultimo texto que o modelo produziu. Numa parada forcada ele vira a
    # resposta ao cliente: encerrar em silencio deixa quem abriu o chamado sem
    # nada, o oposto da regra de dizer o que falta.
    last_content: str = ""

    # As cinco ações de impacto entram junto: sem elas o agente não consegue
    # escalar nem executar, e sete dos dezessete casos exigem isso. A identidade
    # sai da config, e o gate do servidor decide o que ela pode fazer.
    async with connect(
        config.api_base_url,
        seed=config.seed,
        include_impact=True,
        user_id=config.user_id,
    ) as tools:
        schema = await tools.openai_schema()

        while True:
            if trace.model_calls >= config.max_model_calls:
                _halt(trace, StopReason.MAX_MODEL_CALLS, last_content)
                break
            if len(trace.steps) >= config.max_steps:
                _halt(trace, StopReason.MAX_STEPS, last_content)
                break

            t0 = time.perf_counter()
            try:
                completion = await client.chat(messages, schema)
            except Exception as exc:  # noqa: BLE001
                trace.error = str(exc)
                trace.finish(StopReason.ERROR)
                break

            trace.model_calls += 1
            trace.prompt_tokens += completion.prompt_tokens or 0
            trace.completion_tokens += completion.completion_tokens or 0
            last_content = completion.content or last_content

            if verbose:
                elapsed = int((time.perf_counter() - t0) * 1000)
                asked = [c.name for c in completion.tool_calls] or ["<resposta final>"]
                print(f"  modelo ({elapsed} ms) -> {', '.join(asked)}")

            if not completion.tool_calls:
                trace.finish(StopReason.ANSWERED, completion.content or "")
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": completion.content or "",
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments, ensure_ascii=False),
                            },
                        }
                        for c in completion.tool_calls
                    ],
                }
            )

            for tool_call in completion.tool_calls:
                # Um turno pode pedir varias ferramentas. O teto e de passos,
                # nao de turnos, entao ele tambem vale dentro do turno. Quem
                # encerra e a checagem no topo do while, para haver um unico
                # caminho de parada.
                if len(trace.steps) >= config.max_steps:
                    break

                result = trace.record(
                    await tools.call(tool_call.name, tool_call.arguments)
                )

                if verbose:
                    flag = "ok" if result.ok else "ERRO"
                    mode = result.mode.value if result.mode else "-"
                    print(f"  [{result.step}] {result.as_path_step()}  {flag}  mode={mode}")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": _observation(result),
                    }
                )

    if trace.stop_reason is None:
        trace.finish(StopReason.ERROR)
    return trace
