"""Runner: executa um braço sobre os casos, grava trace e pontua.

Ponto de entrada headless. Não depende de `make`, de shell nem de terminal
interativo, porque a bateria oficial roda dentro do notebook do Colab, cujo
teto é 12 horas com queda por ociosidade.

Daí a resumibilidade: um batch que só grava no fim é um batch que se perde
inteiro quando a sessão cai. O trace vai para disco assim que cada execução
termina, e reiniciar recomeça de onde parou em vez de refazer tudo.

`pending()` é a peça pura dessa lógica — dado o que já está gravado, o que falta
rodar — e por isso é testável sem modelo, sem rede e sem relógio.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from agent.react import run_case
from agent.scorer import Scores, score
from agent.trace import RunConfig, Trace

Run = tuple[str, int]
"""Uma execução: `(case_id, repeticao)`. A unidade de retomada."""


def pending(cases: Iterable[str], repetitions: int, done: set[Run]) -> list[Run]:
    """O que falta rodar, em ordem determinística.

    Ordenado por caso e depois por repetição para que uma retomada produza a
    mesma sequência que teria produzido sem a interrupção.
    """
    return [
        (case_id, repetition)
        for case_id in cases
        for repetition in range(repetitions)
        if (case_id, repetition) not in done
    ]


def completed_runs(traces_path: str | Path) -> set[Run]:
    """Lê o JSONL e devolve as execuções já gravadas.

    Linha corrompida é ignorada em vez de derrubar a retomada: uma sessão morta
    no meio da escrita deixa exatamente isso, e recusar-se a continuar por causa
    dela transformaria uma perda de uma execução na perda do batch inteiro.
    """
    path = Path(traces_path)
    if not path.exists():
        return set()

    done: set[Run] = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                registro = json.loads(line)
                done.add((registro["case_id"], registro["config"]["repetition"]))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    return done


@dataclass
class BatchSummary:
    """O que a bateria custou e produziu."""

    total: int = 0
    executed: int = 0
    skipped: int = 0
    failed: int = 0
    model_calls: int = 0
    wall_seconds: float = 0.0
    scores: list[Scores] = field(default_factory=list)

    @property
    def seconds_per_run(self) -> float:
        return self.wall_seconds / self.executed if self.executed else 0.0


async def run_batch(
    config: RunConfig,
    cases: list[dict[str, Any]],
    expected_paths: dict[str, list[dict[str, str]]],
    out_dir: str | Path,
    *,
    repetitions: int = 1,
    client: Any | None = None,
    on_result: Callable[[Trace, Scores], None] | None = None,
) -> BatchSummary:
    """Roda o braço sobre os casos e devolve o resumo.

    Grava incrementalmente em `out_dir`: `traces.jsonl` e `scores.jsonl`.
    Chamar de novo com o mesmo `out_dir` retoma de onde parou.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    traces_path = out / "traces.jsonl"
    scores_path = out / "scores.jsonl"

    by_id = {c["id"]: c for c in cases}
    done = completed_runs(traces_path)
    todo = pending(list(by_id), repetitions, done)

    summary = BatchSummary(
        total=len(by_id) * repetitions,
        skipped=len(by_id) * repetitions - len(todo),
    )

    for case_id, repetition in todo:
        case = by_id[case_id]
        # Cada execução carrega a própria repetição na config, porque é a config
        # que vai para o trace e é dela que a retomada lê o que já rodou.
        run_config = config.model_copy(update={"repetition": repetition})

        trace = await run_case(case, run_config, client=client)
        resultado = score(trace, expected_paths.get(case.get("ticket_id", ""), []))

        # O score vai primeiro, o trace por último. O trace é a chave de
        # retomada: na ordem inversa, morrer entre as duas escritas deixaria a
        # execução marcada como feita com o score perdido para sempre. Assim,
        # uma queda deixa no máximo um score órfão, que a re-execução repõe.
        with scores_path.open("a", encoding="utf-8") as fh:
            fh.write(resultado.model_dump_json() + "\n")
        trace.append_to(traces_path)

        summary.executed += 1
        summary.model_calls += trace.model_calls
        summary.wall_seconds += trace.duration_s
        summary.scores.append(resultado)
        if trace.error:
            summary.failed += 1

        if on_result:
            on_result(trace, resultado)

    return summary


# --- ponto de entrada headless ------------------------------------------------

DEFAULTS: dict[str, Any] = {
    "arm": "A",
    "model": "qwen2.5:1.5b",
    "model_base_url": "http://localhost:11434",
    "api_base_url": "http://localhost:8000",
    "seed": "exp",
    "user_id": "usr_ana",
    "max_steps": 10,
    "max_model_calls": 12,
    "repetitions": 1,
    "cases": None,
    "out_dir": "runs/baseline",
}


def load_settings(path: str | Path | None = None,
                  overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Config a partir de arquivo JSON, sobre os padrões, com overrides por cima.

    Externa de propósito: trocar o laptop pelo Colab tem que ser trocar um
    arquivo, não editar código. E o que muda o comportamento do modelo precisa
    estar aqui para chegar ao `RunConfig` e, por ele, ao trace — knob lido do
    ambiente produziria execuções diferentes com traces de config idêntica.
    """
    settings = dict(DEFAULTS)
    if path:
        settings.update(json.loads(Path(path).read_text(encoding="utf-8")))
    settings.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return settings


def config_from(settings: dict[str, Any]) -> RunConfig:
    campos = set(RunConfig.model_fields)
    return RunConfig(**{k: v for k, v in settings.items() if k in campos})


async def main(argv: list[str] | None = None) -> int:
    import argparse

    from agent.trace import Arm

    parser = argparse.ArgumentParser(description="Roda um braço do experimento.")
    parser.add_argument("--config", help="arquivo JSON de configuração")
    parser.add_argument("--arm", choices=[a.value for a in Arm])
    parser.add_argument("--model")
    parser.add_argument("--seed")
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--out-dir", dest="out_dir")
    parser.add_argument("--cases", nargs="*", help="ticket_ids; vazio = todos")
    args = parser.parse_args(argv)

    settings = load_settings(args.config, vars(args))
    root = Path(__file__).resolve().parent.parent

    todos = json.loads((root / "agent-input" / "cases.json").read_text())
    gabarito = json.loads((root / "eval" / "expected-paths.json").read_text())
    expected = {g["ticket_id"]: g["expected_path"] for g in gabarito}

    escolhidos = settings.get("cases")
    casos = [c for c in todos if not escolhidos or c["ticket_id"] in escolhidos]

    config = config_from(settings)
    print(f"braço {config.arm.value} · modelo {config.model} · seed {config.seed}")
    print(f"{len(casos)} casos × {settings['repetitions']} repetições\n")

    def progresso(trace: Trace, resultado: Scores) -> None:
        print(
            f"  {trace.ticket_id:<12} rep {trace.config.repetition}  "
            f"recall {resultado.tool_selection.recall:.2f}  "
            f"traj {resultado.trajectory.similarity:.2f}  "
            f"{trace.duration_s:.1f}s"
        )

    resumo = await run_batch(
        config, casos, expected, settings["out_dir"],
        repetitions=int(settings["repetitions"]), on_result=progresso,
    )

    print(
        f"\nexecutadas {resumo.executed} · retomadas {resumo.skipped} · "
        f"falhas {resumo.failed}"
    )
    print(
        f"chamadas ao modelo {resumo.model_calls} · "
        f"{resumo.wall_seconds:.0f}s totais · "
        f"{resumo.seconds_per_run:.1f}s por execução"
    )
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
