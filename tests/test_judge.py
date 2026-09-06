"""Judge determinístico: objetos de análise 4 e 5, sem chamada de modelo.

O único juiz disponível seria o próprio modelo que produziu as respostas. Um
1,5B julgando a si mesmo produz número que não se defende. Regra sobre o trace
é auditável linha a linha, e mede exatamente o modo de falha observado: afirmar
sobre dado que não foi consultado.
"""

from __future__ import annotations

from agent.judge import RUBRIC_VERSION, judge, values_in
from agent.trace import Arm, Mode, RunConfig, StopReason, ToolCall, Trace

CONFIG = RunConfig(
    arm=Arm.BASELINE, model="m", model_base_url="x", api_base_url="y", seed="s"
)


def trace_com(resposta: str, evidencia: list[dict] | None = None,
              modes: list[Mode] | None = None, mensagem: str = "") -> Trace:
    t = Trace(case_id="c", ticket_id="TKT-INV-05", message=mensagem, config=CONFIG)
    for i, dado in enumerate(evidencia or []):
        t.record(
            ToolCall(step=0, tool="t", http_method="GET", http_path=f"/x{i}",
                     data=dado, mode=(modes or [Mode.COMPLETE])[i % len(modes or [1])]
                     if modes else Mode.COMPLETE)
        )
    t.finish(StopReason.ANSWERED, resposta)
    return t


# --- extração de valores -------------------------------------------------------


def test_extrai_numeros_e_identificadores():
    achados = values_in("O ativo asset_C710 gira a 2950 RPM com BPFO de 198.2 Hz")

    assert "asset_C710" in achados
    assert "2950" in achados
    assert "198.2" in achados


def test_ignora_palavra_comum():
    """Sem isso, qualquer palavra da resposta viraria 'valor citado'."""
    achados = values_in("O compressor esta com vibracao acima do normal")

    assert achados == set()


# --- objeto 4: ancoragem -------------------------------------------------------


def test_resposta_ancorada_na_evidencia_pontua_cheio():
    t = trace_com(
        "O ativo asset_C710 gira a 2950 RPM.",
        evidencia=[{"id": "asset_C710", "rotation_rpm": 2950}],
    )

    r = judge(t)

    assert r.grounding.cited == 2
    assert r.grounding.supported == 2
    assert r.grounding.hallucinated == []
    assert r.grounding.score == 5


def test_valor_que_nao_aparece_na_evidencia_e_alucinacao():
    """O modo de falha observado: afirmar sobre dado que nao foi consultado."""
    t = trace_com(
        "O RMS esta em 7.4 mm/s, acima do limiar.",
        evidencia=[{"id": "asset_C710", "rotation_rpm": 2950}],
    )

    r = judge(t)

    assert "7.4" in r.grounding.hallucinated
    assert r.grounding.score < 5


def test_valor_vindo_do_chamado_do_cliente_nao_e_alucinacao():
    """O cliente disse 'duas semanas'; repetir isso nao e inventar."""
    t = trace_com(
        "Voce relatou o problema no ativo asset_C710.",
        evidencia=[{"outra_coisa": 1}],
        mensagem="Problema no asset_C710 ha duas semanas",
    )

    r = judge(t)

    assert r.grounding.hallucinated == []


def test_resposta_sem_valor_nenhum_nao_pontua_ancoragem():
    """Nao citar dado nao e o mesmo que citar dado correto."""
    t = trace_com("Recomendo abrir um chamado.", evidencia=[{"rotation_rpm": 2950}])

    r = judge(t)

    assert r.grounding.cited == 0
    assert r.grounding.score == 0


# --- objeto 5: reconhecimento da degradação ------------------------------------


def test_reconhecer_a_degradacao_que_ocorreu_pontua():
    t = trace_com(
        "O dado veio parcial, entao a conclusao e limitada.",
        evidencia=[{"x": 1}], modes=[Mode.PARTIAL],
    )

    r = judge(t)

    assert r.degradation.occurred == ["partial"]
    assert r.degradation.acknowledged == ["partial"]
    assert r.degradation.score == 5


def test_ignorar_a_degradacao_zera_o_criterio():
    """Concluir com confianca sobre dado indisponivel e a falha central."""
    t = trace_com(
        "Esta tudo normal com a maquina.",
        evidencia=[{"x": 1}], modes=[Mode.UNAVAILABLE],
    )

    r = judge(t)

    assert r.degradation.occurred == ["unavailable"]
    assert r.degradation.acknowledged == []
    assert r.degradation.score == 0


def test_sem_degradacao_o_criterio_nao_penaliza():
    """Nada a reconhecer nao pode contar como falha de reconhecimento."""
    t = trace_com("Tudo certo.", evidencia=[{"x": 1}], modes=[Mode.COMPLETE])

    r = judge(t)

    assert r.degradation.occurred == []
    assert r.degradation.score == 5


# --- objeto 5: responde à pergunta raiz ----------------------------------------


def test_cobertura_da_pergunta_raiz():
    t = trace_com("Nao ha insight porque o modelo esta atrasado.")

    r = judge(t, root_question="Por que nao ha insight apesar da tendencia de RMS?")

    assert r.root_question.covered > 0
    assert r.root_question.score > 0


def test_resposta_que_nao_toca_a_pergunta_raiz_pontua_baixo():
    t = trace_com("O ativo e um compressor de gas fabricado em 2019.")

    r = judge(t, root_question="Por que nao ha insight apesar da tendencia de RMS?")

    assert r.root_question.score <= 2


# --- composição ----------------------------------------------------------------


def test_nota_final_combina_os_tres_criterios():
    t = trace_com(
        "O dado veio parcial. O ativo asset_C710 gira a 2950 RPM.",
        evidencia=[{"id": "asset_C710", "rotation_rpm": 2950}], modes=[Mode.PARTIAL],
    )

    r = judge(t, root_question="Qual a rotacao do ativo?")

    assert 0 <= r.answer_quality <= 5
    assert r.rubric_version == RUBRIC_VERSION


def test_resposta_vazia_zera_tudo():
    t = trace_com("", evidencia=[{"x": 1}])

    r = judge(t)

    assert r.answer_quality == 0
    assert r.grounding.score == 0


def test_versao_da_rubrica_viaja_junto():
    """Um numero precisa saber sob que regra foi produzido."""
    r = judge(trace_com("qualquer"))

    assert r.rubric_version == RUBRIC_VERSION
