"""`summarize()` e `extrapolate()`: as partes puras do portão de decisão."""

from __future__ import annotations

import pytest

from agent.scorer import Scores, ToolSelection, Trajectory
from agent.smoke import extrapolate, summarize


def score_of(ticket: str, similarity: float, path: list[str], recall: float = 1.0) -> Scores:
    return Scores(
        case_id=ticket.lower(), ticket_id=ticket, arm="A",
        tool_selection=ToolSelection(recall=recall),
        trajectory=Trajectory(similarity=similarity, executed=path),
    )


def test_repeticoes_identicas_sao_deterministicas_e_liberam_a_bateria():
    scores = [score_of("TKT-A", 0.9, ["GET /x"]) for _ in range(3)]

    veredito = summarize(scores)

    assert veredito.proceed is True
    assert veredito.deterministic_cases == 1
    assert veredito.mean_within_case_stdev == 0.0
    assert "ha sinal" in veredito.reason


def test_variancia_alta_dentro_do_caso_barra_a_bateria():
    scores = [
        score_of("TKT-A", 0.9, ["GET /x"]),
        score_of("TKT-A", 0.2, ["GET /y"]),
        score_of("TKT-A", 0.6, ["GET /z"]),
    ]

    veredito = summarize(scores)

    assert veredito.proceed is False
    assert "variancia domina" in veredito.reason
    assert veredito.deterministic_cases == 0


def test_efeito_de_piso_e_diagnosticado_separado_da_variancia():
    """Braço que não acerta nada e braço que oscila impedem a comparação por
    motivos opostos, e as correções são opostas."""
    scores = [score_of("TKT-A", 0.0, ["GET /errado"]) for _ in range(3)]

    veredito = summarize(scores)

    assert veredito.proceed is False
    assert "piso" in veredito.reason
    assert "variancia" not in veredito.reason


def test_sem_execucao_nao_libera_nada():
    veredito = summarize([])

    assert veredito.proceed is False
    assert veredito.total_cases == 0


def test_extrapolacao_da_bateria_oficial():
    custo = extrapolate(seconds_per_run=30.0, calls_per_run=4.0)

    assert custo["runs"] == 170
    assert custo["hours"] == 170 * 30 / 3600
    assert custo["model_calls"] == 680


def score_deep(ticket: str, executed: list[str], expected: list[str]) -> Scores:
    from agent.scorer import Trajectory as T
    return Scores(
        case_id=ticket.lower(), ticket_id=ticket, arm="A",
        tool_selection=ToolSelection(recall=0.5),
        trajectory=T(similarity=0.5, executed=executed, expected=expected),
    )


def test_agente_que_desiste_no_primeiro_passo_barra_a_bateria():
    """Estável e acima do piso, mas dá 1 passo onde o gabarito pede 4.

    Nem variância nem piso pegam esse caso: as repetições são idênticas e a
    média está acima do chão. Medir arquitetura contra um agente assim mede a
    política de parada e o prompt.
    """
    scores = [
        score_deep("TKT-A", ["GET /x"], ["GET /x", "GET /y", "GET /z", "GET /w"])
        for _ in range(3)
    ]

    veredito = summarize(scores)

    assert veredito.proceed is False
    assert "nao investiga" in veredito.reason
    assert veredito.shallow_cases == 1


def test_profundidade_suficiente_nao_barra():
    scores = [
        score_deep("TKT-A", ["GET /x", "GET /y", "GET /z"], ["GET /x", "GET /y", "GET /z"])
        for _ in range(3)
    ]

    veredito = summarize(scores)

    assert veredito.mean_depth == 1.0
    assert veredito.proceed is True


def test_caso_de_um_passo_nao_mascara_os_casos_abandonados():
    """Gabarito de 1 passo dá profundidade 100% com qualquer chamada única.

    Mediando as frações, esse caso puxa a média e esconde os abandonados.
    Contando casos, ele não tem esse poder.
    """
    fundo = ["GET /x", "GET /y", "GET /z", "GET /w"]
    scores = (
        [score_deep("TKT-RASO-1", ["GET /x"], fundo)]
        + [score_deep("TKT-RASO-2", ["GET /x"], fundo)]
        + [score_deep("TKT-CURTO", ["GET /errado"], ["GET /x"])]
    )

    veredito = summarize(scores)

    assert veredito.mean_depth == pytest.approx(0.5)   # média diria "passa"
    assert veredito.shallow_cases == 2
    assert veredito.proceed is False
