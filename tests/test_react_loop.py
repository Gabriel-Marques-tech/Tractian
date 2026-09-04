"""Seam 2 — `run_case(caso, config) -> Trace`, o laço do braço A.

O modelo é dublê e devolve sequências de tool call roteirizadas; o servidor MCP
e a API industrial são reais. É o que a spec pede: prova que o laço monta
argumentos, chama de verdade, registra o trace e para pelo motivo certo, sem
depender de um LLM real (que seria lento e não determinístico).
"""

from __future__ import annotations

from typing import Any

import pytest

from agent.llm import Completion, ToolRequest
from agent.react import run_case
from agent.trace import Arm, RunConfig, StopReason

from conftest import API_BASE_URL, requires_api

pytestmark = [pytest.mark.anyio, requires_api]


class ScriptedModel:
    """Modelo dublê: devolve as respostas roteirizadas, em ordem.

    Mesma interface de `LLMClient.chat`, então `run_case` não sabe a diferença.
    """

    def __init__(self, *script: Completion) -> None:
        self.script = list(script)
        self.calls: list[list[dict[str, Any]]] = []

    async def chat(self, messages, tools=None) -> Completion:
        self.calls.append(list(messages))
        if not self.script:
            return Completion(content="fim do roteiro")
        return self.script.pop(0)


def answer(text: str) -> Completion:
    return Completion(content=text, prompt_tokens=10, completion_tokens=5)


def wants(tool: str, **arguments: Any) -> Completion:
    return Completion(
        content="",
        tool_calls=[ToolRequest(id=f"c_{tool}", name=tool, arguments=arguments)],
        prompt_tokens=10,
        completion_tokens=5,
    )


CASE = {
    "id": "case_tkt_inv_05",
    "ticket_id": "TKT-INV-05",
    "asset_id": "asset_C710",
    "company_id": "comp_petro_delta",
    "message": "RMS subindo sem insight. Cade o diagnostico?",
}


def config(**overrides: Any) -> RunConfig:
    defaults: dict[str, Any] = {
        "arm": Arm.BASELINE,
        "model": "dublê",
        "model_base_url": "http://modelo-inexistente",
        "api_base_url": API_BASE_URL,
        "seed": "teste",
        "max_steps": 5,
        "max_model_calls": 6,
    }
    defaults.update(overrides)
    return RunConfig(**defaults)


async def test_responde_sem_ferramenta_encerra_como_answered():
    model = ScriptedModel(answer("Nao ha evidencia suficiente."))

    trace = await run_case(CASE, config(), client=model)

    assert trace.stop_reason is StopReason.ANSWERED
    assert trace.final_answer == "Nao ha evidencia suficiente."
    assert trace.steps == []
    assert trace.model_calls == 1


async def test_encadeia_ferramentas_e_registra_trajetoria_no_vocabulario_do_gabarito():
    model = ScriptedModel(
        wants("get_rms", asset_id="asset_C710"),
        wants("get_baseline", asset_id="asset_C710"),
        answer("Baseline estabelecido e RMS acima do limiar."),
    )

    trace = await run_case(CASE, config(), client=model)

    assert trace.path() == [
        "GET /assets/asset_C710/rms",
        "GET /assets/asset_C710/baseline",
    ]
    assert trace.stop_reason is StopReason.ANSWERED
    assert [c.step for c in trace.steps] == [1, 2]
    assert all(c.ok for c in trace.steps)


async def test_argumentos_do_modelo_chegam_na_chamada_registrada():
    model = ScriptedModel(wants("get_asset", asset_id="asset_G501"), answer("ok"))

    trace = await run_case(CASE, config(), client=model)

    assert trace.steps[0].tool == "get_asset"
    assert trace.steps[0].arguments == {"asset_id": "asset_G501"}


async def test_mode_degradado_da_api_sobrevive_ate_o_trace():
    # asset_G501/rms tem override de cenario fixo: sempre `unavailable`,
    # e o gabarito de TKT-INV-04 espera exatamente esse retorno.
    model = ScriptedModel(wants("get_rms", asset_id="asset_G501"), answer("Sem dado."))

    trace = await run_case(CASE, config(), client=model)

    assert trace.steps[0].mode is not None
    assert trace.steps[0].mode.value == "unavailable"
    assert trace.modes_seen() == {"unavailable": 1}


async def test_ferramenta_inexistente_nao_derruba_o_laco():
    model = ScriptedModel(wants("ferramenta_que_nao_existe"), answer("segui sem ela"))

    trace = await run_case(CASE, config(), client=model)

    assert trace.steps[0].ok is False
    assert trace.steps[0].error
    assert trace.stop_reason is StopReason.ANSWERED


async def test_modelo_que_nunca_conclui_para_no_limite_de_passos():
    insistente = ScriptedModel(*[wants("get_asset", asset_id="asset_C710") for _ in range(20)])

    trace = await run_case(CASE, config(max_steps=3, max_model_calls=50), client=insistente)

    assert trace.stop_reason is StopReason.MAX_STEPS
    assert len(trace.steps) <= 3


async def test_limite_de_passos_respeitado_com_varias_ferramentas_por_turno():
    """Um turno pode pedir várias ferramentas. O limite é de passos, não de turnos."""
    tres_de_uma_vez = Completion(
        content="",
        tool_calls=[
            ToolRequest(id="a", name="get_asset", arguments={"asset_id": "asset_C710"}),
            ToolRequest(id="b", name="get_rms", arguments={"asset_id": "asset_C710"}),
            ToolRequest(id="c", name="get_baseline", arguments={"asset_id": "asset_C710"}),
        ],
    )
    model = ScriptedModel(tres_de_uma_vez, tres_de_uma_vez, answer("pronto"))

    trace = await run_case(CASE, config(max_steps=4, max_model_calls=50), client=model)

    assert len(trace.steps) <= 4


async def test_falha_do_modelo_vira_stop_reason_e_nao_excecao():
    class ModeloQuebrado:
        async def chat(self, messages, tools=None):
            raise RuntimeError("ollama HTTP 500: llama-server terminated")

    trace = await run_case(CASE, config(), client=ModeloQuebrado())

    assert trace.stop_reason is StopReason.ERROR
    assert "ollama HTTP 500" in (trace.error or "")


async def test_parada_por_limite_ainda_entrega_algo_ao_cliente():
    """Quem abriu o chamado precisa receber resposta, mesmo em parada forçada.

    Encerrar por limite sem `final_answer` deixa a pessoa sem nada, o que
    contraria a regra de dizer o que falta em vez de silenciar.
    """
    insistente = ScriptedModel(
        *[
            Completion(
                content=f"ainda investigando, passo {i}",
                tool_calls=[ToolRequest(id=f"c{i}", name="get_asset",
                                        arguments={"asset_id": "asset_C710"})],
            )
            for i in range(20)
        ]
    )

    trace = await run_case(CASE, config(max_steps=2, max_model_calls=50), client=insistente)

    assert trace.stop_reason is StopReason.MAX_STEPS
    assert trace.final_answer, "parada por limite deixou o cliente sem resposta"
