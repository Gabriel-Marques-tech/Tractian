"""Costura do runner: o que falta rodar, e a execução em volta.

`pending()` é função pura sobre o que já está em disco — é onde mora a
resumibilidade, e não precisa de modelo nem de rede para ser exercitada.
`run_batch()` é testado com o mesmo modelo dublê da costura do laço ReAct.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent.llm import Completion, ToolRequest
from agent.runner import completed_runs, pending, run_batch
from agent.trace import Arm, RunConfig, StopReason, Trace

from conftest import API_BASE_URL, requires_api

pytestmark = [pytest.mark.anyio, requires_api]

CASES = [
    {"id": "case_a", "ticket_id": "TKT-A", "asset_id": "asset_C710", "message": "a"},
    {"id": "case_b", "ticket_id": "TKT-B", "asset_id": "asset_C710", "message": "b"},
]
GOLD = {
    "TKT-A": [{"step": "GET /assets/asset_C710/rms", "note": ""}],
    "TKT-B": [{"step": "GET /assets/asset_C710/baseline", "note": ""}],
}


class ScriptedModel:
    """Decide pelo histórico, não por contador.

    Um contador de chamadas vazaria estado entre as execuções do batch: a
    segunda execução começaria no meio do roteiro. Olhar o histórico faz o
    dublê se comportar igual em toda execução, que é o que um modelo de
    temperatura zero faria.
    """

    def __init__(self, primeiro: Completion | None = None,
                 depois: Completion | None = None) -> None:
        self.primeiro = primeiro or Completion(content="pronto")
        self.depois = depois or Completion(content="conclui")
        self.calls = 0

    async def chat(self, messages, tools=None) -> Completion:
        self.calls += 1
        ja_usou_ferramenta = any(m.get("role") == "tool" for m in messages)
        return self.depois if ja_usou_ferramenta else self.primeiro


def wants(tool: str, **arguments: Any) -> Completion:
    return Completion(
        content="", tool_calls=[ToolRequest(id="c", name=tool, arguments=arguments)]
    )


def config(**overrides: Any) -> RunConfig:
    defaults: dict[str, Any] = {
        "arm": Arm.BASELINE,
        "model": "dublê",
        "model_base_url": "http://modelo",
        "api_base_url": API_BASE_URL,
        "seed": "teste",
        "max_steps": 3,
        "max_model_calls": 4,
    }
    defaults.update(overrides)
    return RunConfig(**defaults)


# --- pending(): a parte pura ---------------------------------------------------


def test_nada_gravado_significa_tudo_pendente():
    assert pending(["case_a", "case_b"], repetitions=2, done=set()) == [
        ("case_a", 0), ("case_a", 1), ("case_b", 0), ("case_b", 1),
    ]


def test_execucao_ja_gravada_nao_repete():
    restante = pending(
        ["case_a", "case_b"], repetitions=2, done={("case_a", 0), ("case_b", 1)}
    )

    assert restante == [("case_a", 1), ("case_b", 0)]


def test_tudo_gravado_significa_nada_pendente():
    done = {("case_a", 0), ("case_a", 1)}
    assert pending(["case_a"], repetitions=2, done=done) == []


# --- completed_runs(): o que o disco já tem ------------------------------------


def test_arquivo_inexistente_nao_derruba_a_retomada(tmp_path: Path):
    assert completed_runs(tmp_path / "nao-existe.jsonl") == set()


def test_linha_corrompida_e_ignorada_em_vez_de_derrubar_o_batch(tmp_path: Path):
    """Sessão morta no meio da escrita deixa exatamente isso.

    Recusar-se a continuar por causa de uma linha truncada transformaria a
    perda de uma execução na perda do batch inteiro — que é o cenário que a
    resumibilidade existe para evitar.
    """
    arquivo = tmp_path / "traces.jsonl"
    arquivo.write_text(
        json.dumps({"case_id": "case_a", "config": {"repetition": 0}}) + "\n"
        + '{"case_id": "case_b", "conf\n'  # truncada
        + json.dumps({"case_id": "case_b", "config": {"repetition": 1}}) + "\n"
    )

    assert completed_runs(arquivo) == {("case_a", 0), ("case_b", 1)}


# --- run_batch(): a execução em volta ------------------------------------------


async def test_roda_todos_os_casos_por_todas_as_repeticoes(tmp_path: Path):
    modelo = ScriptedModel(Completion(content="resposta direta"))

    resumo = await run_batch(
        config(), CASES, GOLD, tmp_path, repetitions=2, client=modelo
    )

    assert resumo.total == 4
    assert resumo.executed == 4
    assert resumo.skipped == 0
    assert len(resumo.scores) == 4
    assert len(completed_runs(tmp_path / "traces.jsonl")) == 4


async def test_trace_e_score_sao_gravados_lado_a_lado(tmp_path: Path):
    await run_batch(config(), CASES, GOLD, tmp_path, repetitions=1,
                    client=ScriptedModel(Completion(content="ok")))

    traces = (tmp_path / "traces.jsonl").read_text().strip().splitlines()
    scores = (tmp_path / "scores.jsonl").read_text().strip().splitlines()

    assert len(traces) == len(scores) == 2
    assert json.loads(scores[0])["case_id"] == json.loads(traces[0])["case_id"]


async def test_rodar_de_novo_retoma_sem_duplicar(tmp_path: Path):
    """O cenário do Colab: sessão cai, tu reinicia, e nada é refeito."""
    primeiro = await run_batch(config(), CASES, GOLD, tmp_path, repetitions=2,
                               client=ScriptedModel(Completion(content="ok")))
    segundo = await run_batch(config(), CASES, GOLD, tmp_path, repetitions=2,
                              client=ScriptedModel(Completion(content="ok")))

    assert primeiro.executed == 4
    assert segundo.executed == 0
    assert segundo.skipped == 4
    assert len(completed_runs(tmp_path / "traces.jsonl")) == 4


async def test_retomada_parcial_completa_so_o_que_falta(tmp_path: Path):
    await run_batch(config(), CASES[:1], GOLD, tmp_path, repetitions=2,
                    client=ScriptedModel(Completion(content="ok")))

    resumo = await run_batch(config(), CASES, GOLD, tmp_path, repetitions=2,
                             client=ScriptedModel(Completion(content="ok")))

    assert resumo.executed == 2
    assert resumo.skipped == 2
    assert len(completed_runs(tmp_path / "traces.jsonl")) == 4


async def test_repeticao_e_gravada_na_config_de_cada_trace(tmp_path: Path):
    """É de onde a retomada lê. Sem isso, todas as repetições colidiriam."""
    await run_batch(config(), CASES[:1], GOLD, tmp_path, repetitions=3,
                    client=ScriptedModel(Completion(content="ok")))

    repeticoes = sorted(
        t.config.repetition for t in Trace.read_jsonl(tmp_path / "traces.jsonl")
    )
    assert repeticoes == [0, 1, 2]


async def test_custo_por_execucao_e_contabilizado(tmp_path: Path):
    modelo = ScriptedModel(wants("get_rms", asset_id="asset_C710"),
                           Completion(content="conclui"))

    resumo = await run_batch(config(), CASES[:1], GOLD, tmp_path, repetitions=2,
                             client=modelo)

    assert resumo.model_calls == 4          # 2 chamadas por execucao
    assert resumo.wall_seconds > 0
    assert resumo.seconds_per_run > 0


async def test_seed_da_config_chega_na_api(tmp_path: Path):
    """Mesma seed entre braços é o que torna a comparação justa."""
    modelo = ScriptedModel(wants("get_rms", asset_id="asset_C710"),
                           Completion(content="conclui"))

    await run_batch(config(seed="seed-fixa"), CASES[:1], GOLD, tmp_path,
                    repetitions=1, client=modelo)

    trace = next(iter(Trace.read_jsonl(tmp_path / "traces.jsonl")))
    assert trace.config.seed == "seed-fixa"
    assert trace.steps[0].mode is not None


# --- config externa ------------------------------------------------------------


def test_config_vem_de_arquivo_sobre_os_padroes(tmp_path: Path):
    arquivo = tmp_path / "exp.json"
    arquivo.write_text(json.dumps({"model": "qwen2.5:7b", "seed": "colab", "repetitions": 5}))

    from agent.runner import load_settings

    settings = load_settings(arquivo)

    assert settings["model"] == "qwen2.5:7b"
    assert settings["seed"] == "colab"
    assert settings["repetitions"] == 5
    assert settings["api_base_url"] == "http://localhost:8000"  # padrão preservado


def test_override_vence_o_arquivo_e_none_nao_apaga(tmp_path: Path):
    arquivo = tmp_path / "exp.json"
    arquivo.write_text(json.dumps({"model": "do-arquivo", "seed": "do-arquivo"}))

    from agent.runner import load_settings

    settings = load_settings(arquivo, {"model": "da-linha-de-comando", "seed": None})

    assert settings["model"] == "da-linha-de-comando"
    assert settings["seed"] == "do-arquivo"


def test_config_do_experimento_vira_runconfig_sem_campo_extra():
    from agent.runner import config_from, load_settings

    config = config_from(load_settings(None, {"repetitions": 5, "out_dir": "x"}))

    assert config.model_base_url == "http://localhost:11434"
    assert config.repetition == 0  # `repetitions` do batch não vira `repetition`


async def test_queda_entre_as_duas_escritas_nao_perde_o_score(tmp_path: Path, monkeypatch):
    """O trace é a chave de retomada, então tem que ser o último a ser escrito.

    Na ordem inversa, morrer entre as duas escritas deixaria o trace gravado —
    a execução conta como feita — e o score perdido para sempre, sem chance de
    retomada. Escrevendo o score primeiro, uma queda deixa score órfão, que a
    re-execução sobrescreve.
    """
    original = Trace.append_to
    chamadas = {"n": 0}

    def cai_na_primeira(self, path):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise OSError("disco cheio")
        return original(self, path)

    monkeypatch.setattr(Trace, "append_to", cai_na_primeira)

    with pytest.raises(OSError):
        await run_batch(config(), CASES[:1], GOLD, tmp_path, repetitions=1,
                        client=ScriptedModel())

    # Score sobreviveu; trace não. A execução segue pendente e será refeita.
    assert (tmp_path / "scores.jsonl").exists()
    assert completed_runs(tmp_path / "traces.jsonl") == set()


async def test_runner_despacha_para_o_braco_certo(tmp_path: Path):
    """Mesma bateria, mesma seed, mesmos casos: o braço é a unica variavel."""
    from agent.trace import Arm

    await run_batch(config(arm=Arm.MULTI_AGENT), CASES[:1], GOLD, tmp_path,
                    repetitions=1, client=ScriptedModel())

    trace = next(iter(Trace.read_jsonl(tmp_path / "traces.jsonl")))
    assert trace.config.arm is Arm.MULTI_AGENT


# --- retomada de execucoes que falharam ---------------------------------------


def _linha(case_id: str, repeticao: int, stop: str) -> str:
    return json.dumps({
        "case_id": case_id, "ticket_id": "TKT-A", "stop_reason": stop,
        "config": {"repetition": repeticao, "arm": "A", "model": "m",
                   "model_base_url": "x", "api_base_url": "y"},
        "steps": [],
    })


def test_execucao_com_erro_pode_ser_excluida_da_retomada(tmp_path: Path):
    """Falha de ambiente marcaria a execucao como feita para sempre."""
    arquivo = tmp_path / "traces.jsonl"
    arquivo.write_text("\n".join([
        _linha("case_a", 0, "answered"),
        _linha("case_a", 1, "error"),
    ]) + "\n")

    assert completed_runs(arquivo) == {("case_a", 0), ("case_a", 1)}
    assert completed_runs(arquivo, include_failed=False) == {("case_a", 0)}


def test_drop_failed_remove_do_disco_e_devolve_a_contagem(tmp_path: Path):
    from agent.runner import drop_failed

    (tmp_path / "traces.jsonl").write_text("\n".join([
        _linha("case_a", 0, "answered"),
        _linha("case_b", 0, "error"),
        _linha("case_b", 1, "error"),
    ]) + "\n")
    (tmp_path / "scores.jsonl").write_text("\n".join([
        json.dumps({"case_id": "case_a", "arm": "A"}),
        json.dumps({"case_id": "case_b", "arm": "A"}),
    ]) + "\n")

    assert drop_failed(tmp_path) == 2
    assert completed_runs(tmp_path / "traces.jsonl") == {("case_a", 0)}
    restantes = [json.loads(l) for l in
                 (tmp_path / "scores.jsonl").read_text().splitlines() if l.strip()]
    assert [r["case_id"] for r in restantes] == ["case_a"]


def test_drop_failed_sem_falha_nao_mexe_em_nada(tmp_path: Path):
    from agent.runner import drop_failed

    arquivo = tmp_path / "traces.jsonl"
    arquivo.write_text(_linha("case_a", 0, "answered") + "\n")
    antes = arquivo.read_text()

    assert drop_failed(tmp_path) == 0
    assert arquivo.read_text() == antes


def test_drop_failed_em_diretorio_vazio_nao_quebra(tmp_path: Path):
    from agent.runner import drop_failed

    assert drop_failed(tmp_path) == 0
