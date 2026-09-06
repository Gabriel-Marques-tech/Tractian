"""Exportador do inspetor: puro sobre o que o runner gravou."""

from __future__ import annotations

import json
from pathlib import Path

from agent.export import build_payload, export_types
from agent.scorer import Scores, ToolSelection, Trajectory
from agent.trace import Arm, Mode, RunConfig, StopReason, ToolCall, Trace


def config(arm: Arm = Arm.BASELINE, repetition: int = 0) -> RunConfig:
    return RunConfig(
        arm=arm, model="m", model_base_url="x", api_base_url="y", seed="s",
        repetition=repetition,
    )


def gravar(dir_: Path, traces: list[Trace]) -> None:
    """Escreve trace e score na mesma ordem que o runner escreve."""
    dir_.mkdir(parents=True, exist_ok=True)
    for t in traces:
        pontuacao = Scores(
            case_id=t.case_id, ticket_id=t.ticket_id, arm=t.config.arm.value,
            tool_selection=ToolSelection(recall=0.5),
            trajectory=Trajectory(similarity=0.5, executed=t.path()),
        )
        with (dir_ / "scores.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(pontuacao.model_dump_json() + "\n")
        t.append_to(dir_ / "traces.jsonl")


def trace_de(ticket: str, passos: list[str], arm: Arm = Arm.BASELINE,
             repetition: int = 0) -> Trace:
    t = Trace(case_id="case_tkt_inv_05", ticket_id=ticket, message="m",
              config=config(arm, repetition))
    for p in passos:
        metodo, _, caminho = p.partition(" ")
        t.record(ToolCall(step=0, tool="t", http_method=metodo, http_path=caminho,
                          mode=Mode.COMPLETE, arguments={"asset_id": "a"}))
    t.finish(StopReason.ANSWERED, "resposta ao cliente")
    return t


def test_agrupa_por_caso_e_nao_por_execucao(tmp_path: Path):
    """A tela compara os braços no mesmo chamado; agrupar por caso evita que o
    React reconstrua isso a cada render."""
    gravar(tmp_path / "A", [
        trace_de("TKT-INV-05", ["GET /assets/a/rms"], repetition=r) for r in range(3)
    ])

    payload = build_payload({"A": tmp_path / "A"})

    assert len(payload["cases"]) == 1
    assert payload["cases"][0]["ticket_id"] == "TKT-INV-05"
    assert payload["cases"][0]["arms"]["A"]["total_runs"] == 3


def test_indicador_de_estabilidade_conta_quantas_seguiram_o_mesmo_caminho():
    """Sem ele o inspetor mostraria uma execução e esconderia a variância."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        gravar(base / "A", [
            trace_de("TKT-INV-05", ["GET /assets/a/rms"], repetition=0),
            trace_de("TKT-INV-05", ["GET /assets/a/rms"], repetition=1),
            trace_de("TKT-INV-05", ["GET /companies/x"], repetition=2),
        ])

        arm = build_payload({"A": base / "A"})["cases"][0]["arms"]["A"]

    assert arm["total_runs"] == 3
    assert arm["same_path_count"] == 2
    assert arm["distinct_paths"] == 2


def test_execucao_representativa_e_a_do_caminho_dominante(tmp_path: Path):
    gravar(tmp_path / "A", [
        trace_de("TKT-INV-05", ["GET /companies/x"], repetition=0),
        trace_de("TKT-INV-05", ["GET /assets/a/rms"], repetition=1),
        trace_de("TKT-INV-05", ["GET /assets/a/rms"], repetition=2),
    ])

    arm = build_payload({"A": tmp_path / "A"})["cases"][0]["arms"]["A"]

    assert arm["runs"][arm["representative"]]["path"] == ["GET /assets/a/rms"]


def test_os_dois_bracos_ficam_no_mesmo_caso(tmp_path: Path):
    gravar(tmp_path / "A", [trace_de("TKT-INV-05", ["GET /assets/a/rms"])])
    gravar(tmp_path / "B", [
        trace_de("TKT-INV-05", ["GET /assets/a/rms", "GET /assets/a/baseline"],
                 arm=Arm.MULTI_AGENT)
    ])

    payload = build_payload({"A": tmp_path / "A", "B": tmp_path / "B"})

    caso = payload["cases"][0]
    assert set(caso["arms"]) == {"A", "B"}
    assert len(caso["arms"]["B"]["runs"][0]["steps"]) == 2
    assert payload["arms"] == ["A", "B"]


def test_gabarito_entra_com_endpoint_normalizado(tmp_path: Path):
    """A tela compara trajetória contra o gabarito; a query é argumento."""
    gravar(tmp_path / "A", [trace_de("TKT-CTX-01", ["GET /assets/asset_M101"])])

    caso = build_payload({"A": tmp_path / "A"})["cases"][0]

    assert caso["expected_path"]
    com_query = [e for e in caso["expected_path"] if "?" in e["step"]]
    if com_query:
        assert "?" not in com_query[0]["endpoint"]


def test_passo_carrega_o_que_a_tela_precisa(tmp_path: Path):
    gravar(tmp_path / "A", [trace_de("TKT-INV-05", ["GET /assets/a/rms"])])

    passo = build_payload({"A": tmp_path / "A"})["cases"][0]["arms"]["A"]["runs"][0]["steps"][0]

    for campo in ("path", "arguments", "mode", "data", "role", "is_impact",
                  "refused", "recovered_from_text"):
        assert campo in passo
    assert passo["mode"] == "complete"


def test_config_de_cada_braco_vai_junto(tmp_path: Path):
    """Modelo, seed e limites precisam aparecer na tela: sem eles o leitor não
    sabe sob que condição os números foram produzidos."""
    gravar(tmp_path / "A", [trace_de("TKT-INV-05", ["GET /assets/a/rms"])])

    configs = build_payload({"A": tmp_path / "A"})["configs"]

    assert configs["A"]["model"] == "m"
    assert configs["A"]["seed"] == "s"


def test_diretorio_vazio_nao_quebra(tmp_path: Path):
    (tmp_path / "A").mkdir()

    payload = build_payload({"A": tmp_path / "A"})

    assert payload["cases"] == []


def test_schema_dos_tipos_e_gerado_do_pydantic(tmp_path: Path):
    """Tipo escrito à mão em TS divergiria em silêncio, mostrando campo vazio
    na tela em vez de erro."""
    destino = tmp_path / "schema.json"

    export_types(destino)

    schema = json.loads(destino.read_text())
    assert "Trace" in schema["$defs"]
    assert "Scores" in schema["$defs"]
    assert "steps" in schema["$defs"]["Trace"]["properties"]
