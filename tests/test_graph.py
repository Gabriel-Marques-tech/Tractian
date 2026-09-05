"""Braço B — o grafo dos papéis, na mesma costura do braço A.

Mesmo dublê de modelo, mesmo servidor MCP e mesma API real. O que muda é a
arquitetura, que é justamente a variável do experimento.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent.graph import run_case_graph
from agent.llm import Completion, ToolRequest
from agent.trace import Arm, RunConfig, StopReason, Trace

from conftest import API_BASE_URL, requires_api

pytestmark = [pytest.mark.anyio, requires_api]

CASE = {
    "id": "case_tkt_inv_05",
    "ticket_id": "TKT-INV-05",
    "asset_id": "asset_C710",
    "company_id": "comp_petro_delta",
    "message": "RMS subindo sem insight.",
}


class RoleAwareModel:
    """Responde conforme o papel que chamou, não por contador.

    O planejador chama sem ferramentas; o orquestrador chama com. Distinguir
    por isso mantém o dublê estável entre execuções, como um modelo de
    temperatura zero.
    """

    def __init__(self, *tools_to_call: str) -> None:
        self.plan_calls = 0
        self.tool_turns = 0
        self.tools_to_call = list(tools_to_call)

    async def chat(self, messages, tools=None) -> Completion:
        if tools is None and not self.plan_calls:
            self.plan_calls += 1
            return Completion(content="1. checar RMS\n2. checar baseline",
                              prompt_tokens=10, completion_tokens=5)

        if tools is None and self.plan_calls:
            # Sem ferramentas e ja houve plano: e o organizador concluindo.
            return Completion(
                content="DESCARTADO: espectro veio inconclusive.\n"
                        "RESPOSTA: RMS acima do limiar, baseline estabelecido.",
                prompt_tokens=10, completion_tokens=5,
            )

        if self.tool_turns < len(self.tools_to_call):
            nome = self.tools_to_call[self.tool_turns]
            self.tool_turns += 1
            return Completion(
                content="",
                tool_calls=[ToolRequest(id=f"c{self.tool_turns}", name=nome,
                                        arguments={"asset_id": "asset_C710"})],
                prompt_tokens=10, completion_tokens=5,
            )
        return Completion(content="RMS acima do limiar, baseline estabelecido.",
                          prompt_tokens=10, completion_tokens=5)


def config(**overrides: Any) -> RunConfig:
    defaults: dict[str, Any] = {
        "arm": Arm.MULTI_AGENT,
        "model": "dublê",
        "model_base_url": "http://modelo",
        "api_base_url": API_BASE_URL,
        "seed": "teste",
        "user_id": "usr_ana",
        "max_steps": 5,
        "max_model_calls": 8,
    }
    defaults.update(overrides)
    return RunConfig(**defaults)


async def test_resolve_um_caso_ponta_a_ponta():
    modelo = RoleAwareModel("get_rms", "get_baseline")

    trace = await run_case_graph(CASE, config(), client=modelo)

    assert trace.stop_reason is StopReason.ANSWERED
    assert trace.final_answer
    assert trace.path() == [
        "GET /assets/asset_C710/rms",
        "GET /assets/asset_C710/baseline",
    ]


async def test_o_planejador_roda_uma_vez_antes_das_ferramentas():
    modelo = RoleAwareModel("get_rms")

    trace = await run_case_graph(CASE, config(), client=modelo)

    assert modelo.plan_calls == 1
    # planejador + turnos de ferramenta + turno que encerra a coleta + organizador
    assert trace.model_calls == modelo.plan_calls + modelo.tool_turns + 2


async def test_trace_registra_o_papel_que_originou_cada_chamada():
    """Sem isso o relatório não consegue mostrar de onde veio cada passo."""
    trace = await run_case_graph(CASE, config(), client=RoleAwareModel("get_rms"))

    assert [c.role for c in trace.steps] == ["orquestrador_tools"]


async def test_trace_do_braco_B_e_distinguivel_do_braco_A():
    trace = await run_case_graph(CASE, config(), client=RoleAwareModel("get_rms"))

    assert trace.config.arm is Arm.MULTI_AGENT
    assert trace.config.arm.value == "B"


async def test_e_pontuavel_pelo_scorer_sem_alteracao():
    from agent.scorer import score

    trace = await run_case_graph(
        CASE, config(), client=RoleAwareModel("get_rms", "get_baseline")
    )
    gabarito = [
        {"step": "GET /assets/asset_C710/rms", "note": ""},
        {"step": "GET /assets/asset_C710/baseline", "note": ""},
    ]

    resultado = score(trace, gabarito)

    assert resultado.arm == "B"
    assert resultado.trajectory.similarity == 1.0
    assert resultado.tool_selection.recall == 1.0


async def test_limite_de_passos_encerra_o_grafo():
    """Grafo com ciclo precisa de parada própria, senão roda até o teto do
    LangGraph e estoura em vez de encerrar limpo."""
    modelo = RoleAwareModel(*["get_rms"] * 50)

    trace = await run_case_graph(CASE, config(max_steps=3), client=modelo)

    assert trace.stop_reason is StopReason.MAX_STEPS
    assert len(trace.steps) <= 3


async def test_limite_de_chamadas_ao_modelo_encerra_o_grafo():
    modelo = RoleAwareModel(*["get_rms"] * 50)

    trace = await run_case_graph(
        CASE, config(max_steps=99, max_model_calls=4), client=modelo
    )

    assert trace.stop_reason is StopReason.MAX_MODEL_CALLS
    assert trace.model_calls <= 5


async def test_falha_do_modelo_vira_stop_reason_e_nao_excecao():
    class ModeloQuebrado:
        async def chat(self, messages, tools=None):
            raise RuntimeError("ollama HTTP 500")

    trace = await run_case_graph(CASE, config(), client=ModeloQuebrado())

    assert trace.stop_reason is StopReason.ERROR
    assert "ollama HTTP 500" in (trace.error or "")


# --- issue #8: organizador de evidencias --------------------------------------


async def test_organizador_escreve_a_resposta_final():
    """Quem conclui nao e quem coleta. Separar as duas coisas e a razao de o
    braco B existir."""
    trace = await run_case_graph(
        CASE, config(), client=RoleAwareModel("get_rms", "get_baseline")
    )

    assert trace.stop_reason is StopReason.ANSWERED
    assert "RMS acima do limiar" in (trace.final_answer or "")
    assert "DESCARTADO" not in (trace.final_answer or "")


async def test_o_que_foi_descartado_fica_registrado_no_trace():
    trace = await run_case_graph(CASE, config(), client=RoleAwareModel("get_rms"))

    assert "espectro veio inconclusive" in trace.role_notes["organizador"]


async def test_braco_A_nao_tem_deliberacao_a_inspecionar():
    """`role_notes` vazio no braco A e a diferenca que o relatorio mostra."""
    from agent.react import run_case
    from agent.llm import Completion as C

    class Simples:
        async def chat(self, messages, tools=None):
            return C(content="resposta direta")

    trace = await run_case(CASE, config(arm=Arm.BASELINE), client=Simples())

    assert trace.role_notes == {}


async def test_digest_de_evidencia_marca_o_mode_de_cada_consulta():
    """O organizador precisa ver `mode` por consulta: e o que distingue
    evidencia que sustenta de evidencia que nao sustenta."""
    from agent.graph import _evidence_digest
    from agent.trace import Mode, ToolCall

    trace = Trace(case_id="c", config=config())
    for modo, passo in ((Mode.COMPLETE, "/a/rms"), (Mode.CONFLICT, "/a/analyses")):
        trace.record(ToolCall(step=0, tool="t", http_method="GET",
                              http_path=passo, mode=modo))

    digest = _evidence_digest(trace)

    assert "[complete]" in digest
    assert "[conflict]" in digest


async def test_digest_sem_consulta_nao_quebra():
    from agent.graph import _evidence_digest

    assert "nenhuma consulta" in _evidence_digest(Trace(case_id="c", config=config()))
