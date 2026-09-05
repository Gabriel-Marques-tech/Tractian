"""Agregação dos resultados: pura, sem rede e sem modelo."""

from __future__ import annotations

from agent.report import (
    aggregate,
    category_of,
    category_table,
    comparison_table,
    mode_table,
)
from agent.scorer import Impact, Safety, Scores, ToolSelection, Trajectory
from agent.trace import Arm, RunConfig, ToolCall, Trace

CONFIG = RunConfig(
    arm=Arm.BASELINE, model="m", model_base_url="x", api_base_url="y", seed="s"
)


def score_of(ticket: str, similarity: float, arm: str = "A", recall: float = 1.0,
             modes: dict[str, int] | None = None, **impacto) -> Scores:
    return Scores(
        case_id=ticket.lower(), ticket_id=ticket, arm=arm,
        tool_selection=ToolSelection(recall=recall, precision=recall),
        trajectory=Trajectory(similarity=similarity),
        impact=Impact(**{k: v for k, v in impacto.items() if k.startswith(("missing", "unrequested", "executed"))}),
        safety=Safety(unjustified=impacto.get("unjustified", []),
                      refused_by_gate=impacto.get("refused", 0)),
        modes=modes or {},
        answered=True,
    )


# --- categoria ----------------------------------------------------------------


def test_categoria_sai_do_ticket_id():
    assert category_of("TKT-INV-05") == "investigar"
    assert category_of("TKT-CTX-01") == "contextualizar"
    assert category_of("TKT-EXE-16") == "executar"


def test_ticket_desconhecido_nao_quebra():
    assert category_of(None) == "desconhecida"
    assert category_of("SEM-PADRAO") == "desconhecida"
    assert category_of("TKT") == "desconhecida"


# --- agregação ----------------------------------------------------------------


def test_media_e_desvio_das_metricas():
    scores = [score_of("TKT-INV-01", s) for s in (0.2, 0.4, 0.6)]

    r = aggregate(scores)

    assert r.runs == 3
    assert abs(r.trajectory.mean - 0.4) < 1e-9
    assert r.trajectory.stdev > 0


def test_instabilidade_por_caso_e_o_objeto_de_analise_8():
    """Média sozinha esconde variância: dois braços com a mesma média e
    dispersões diferentes não são equivalentes."""
    estavel = [score_of("TKT-A", 0.5) for _ in range(3)]
    instavel = [score_of("TKT-B", v) for v in (0.0, 0.5, 1.0)]

    r = aggregate(estavel + instavel)

    assert r.stability["TKT-A"] == 0.0
    assert r.stability["TKT-B"] > 0.4
    assert r.mean_instability > 0


def test_quebra_por_categoria():
    scores = [
        score_of("TKT-INV-01", 0.8),
        score_of("TKT-INV-02", 0.6),
        score_of("TKT-CTX-01", 0.2),
    ]

    r = aggregate(scores)

    assert abs(r.by_category["investigar"].mean - 0.7) < 1e-9
    assert r.by_category["contextualizar"].mean == 0.2


def test_modes_da_api_sao_somados():
    scores = [
        score_of("TKT-A", 0.5, modes={"complete": 2, "partial": 1}),
        score_of("TKT-A", 0.5, modes={"complete": 1, "unavailable": 3}),
    ]

    r = aggregate(scores)

    assert r.by_mode == {"complete": 3, "partial": 1, "unavailable": 3}


def test_custo_e_resgate_vem_dos_traces():
    scores = [score_of("TKT-A", 0.5)]
    trace = Trace(case_id="a", ticket_id="TKT-A", config=CONFIG)
    trace.model_calls = 4
    trace.record(ToolCall(step=0, tool="t", recovered_from_text=True))
    trace.record(ToolCall(step=0, tool="t"))

    r = aggregate(scores, [trace])

    assert r.model_calls == 4
    assert r.calls_per_run == 4.0
    assert r.total_calls == 2
    assert r.recovery_rate == 0.5


def test_sem_execucao_nao_quebra():
    r = aggregate([])

    assert r.runs == 0
    assert r.seconds_per_run == 0.0
    assert r.calls_per_run == 0.0
    assert r.recovery_rate == 0.0
    assert r.mean_instability == 0.0


# --- tabelas ------------------------------------------------------------------


def test_tabela_de_comparacao_poe_os_bracos_lado_a_lado():
    a = aggregate([score_of("TKT-A", 0.3, arm="A")])
    b = aggregate([score_of("TKT-A", 0.7, arm="B")])

    tabela = comparison_table([a, b])

    assert "| Métrica | Braço A | Braço B |" in tabela
    assert "Trajetória" in tabela
    assert "Chamadas resgatadas de texto" in tabela
    assert tabela.count("\n") >= 14


def test_tabela_por_categoria_mostra_o_n_de_cada_celula():
    a = aggregate([score_of("TKT-INV-01", 0.5, arm="A"),
                   score_of("TKT-INV-02", 0.5, arm="A")])

    tabela = category_table([a])

    assert "investigar" in tabela
    assert "n=2" in tabela


def test_categoria_ausente_em_um_braco_vira_travessao():
    a = aggregate([score_of("TKT-INV-01", 0.5, arm="A")])
    b = aggregate([score_of("TKT-CTX-01", 0.5, arm="B")])

    tabela = category_table([a, b])

    assert "—" in tabela


def test_tabela_de_modes():
    a = aggregate([score_of("TKT-A", 0.5, arm="A", modes={"complete": 2})])
    b = aggregate([score_of("TKT-A", 0.5, arm="B", modes={"conflict": 1})])

    tabela = mode_table([a, b])

    assert "`complete`" in tabela
    assert "`conflict`" in tabela
