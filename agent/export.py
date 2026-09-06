"""Exporta traces e pontuações para o JSON estático que o inspetor consome.

O inspetor lê **um arquivo** e não fala com backend nenhum em runtime. Isso é
o que faz a mesma build servir em três destinos — `npm run dev`, o FastAPI em
`:8001`, e um deploy estático — sem CORS, sem websocket e sem o problema de o
backend morar em localhost.

Cabe: medido, 170 execuções com o `data` inteiro dão ~850 KB, e o maior payload
da API é 1,6 KB (`rms`). Não precisa de índice, lazy-load nem paginação.

A unidade do arquivo é o **caso**, não a execução: a tela compara os dois braços
no mesmo chamado, e agrupar por caso evita que o React tenha que reconstruir
esse agrupamento a cada render.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.scorer import Scores, parse_step
from agent.trace import Trace

ROOT = Path(__file__).resolve().parent.parent


def _load(run_dir: Path) -> tuple[list[Trace], dict[tuple[str, int], Scores]]:
    """Traces e pontuações de um diretório, indexadas por `(caso, repetição)`.

    `Scores` não carrega a repetição, então o par é reconstruído pela ordem de
    escrita: o runner grava score e trace na mesma iteração, um por linha.
    """
    traces = list(Trace.read_jsonl(run_dir / "traces.jsonl"))

    scores_path = run_dir / "scores.jsonl"
    linhas = (
        [l for l in scores_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if scores_path.exists()
        else []
    )
    pontuacoes = [Scores.model_validate_json(l) for l in linhas]

    indexado: dict[tuple[str, int], Scores] = {}
    for trace, pontuacao in zip(traces, pontuacoes):
        indexado[(trace.case_id, trace.config.repetition)] = pontuacao
    return traces, indexado


def _step_payload(call) -> dict[str, Any]:
    """Um passo, como a tela mostra: o que foi chamado e o que voltou."""
    return {
        "step": call.step,
        "tool": call.tool,
        "path": call.as_path_step(),
        "arguments": call.arguments,
        "role": call.role,
        "mode": call.mode.value if call.mode else None,
        "notes": call.notes,
        "data": call.data,
        "ok": call.ok,
        "error": call.error,
        "is_impact": call.is_impact,
        "justification": call.justification,
        "refused": call.refused,
        "refusal_reason": call.refusal_reason,
        "recovered_from_text": call.recovered_from_text,
        "duration_ms": call.duration_ms,
    }


def _run_payload(trace: Trace, pontuacao: Scores | None) -> dict[str, Any]:
    return {
        "repetition": trace.config.repetition,
        "steps": [_step_payload(c) for c in trace.steps],
        "path": trace.path(),
        "final_answer": trace.final_answer,
        "stop_reason": trace.stop_reason.value if trace.stop_reason else None,
        "error": trace.error,
        "model_calls": trace.model_calls,
        "duration_s": round(trace.duration_s, 1),
        "role_notes": trace.role_notes,
        "modes": trace.modes_seen(),
        "scores": json.loads(pontuacao.model_dump_json()) if pontuacao else None,
    }


def _arm_payload(traces: list[Trace], pontuacoes: dict[tuple[str, int], Scores]) -> dict[str, Any]:
    """Execuções de um braço num caso, com o indicador de estabilidade.

    `same_path_count` responde "quantas das N repetições seguiram este mesmo
    caminho". Sem ele o inspetor mostraria uma execução e esconderia a dimensão
    inteira de variância entre repetições, que é o objeto de análise 8.
    """
    ordenados = sorted(traces, key=lambda t: t.config.repetition)
    caminhos = Counter(tuple(t.path()) for t in ordenados)
    dominante, quantas = caminhos.most_common(1)[0] if caminhos else ((), 0)

    representativa = next(
        (i for i, t in enumerate(ordenados) if tuple(t.path()) == dominante), 0
    )

    return {
        "runs": [
            _run_payload(t, pontuacoes.get((t.case_id, t.config.repetition)))
            for t in ordenados
        ],
        "total_runs": len(ordenados),
        "same_path_count": quantas,
        "distinct_paths": len(caminhos),
        "representative": representativa,
    }


def build_payload(run_dirs: dict[str, Path]) -> dict[str, Any]:
    """Monta o JSON do inspetor a partir dos diretórios de execução por braço."""
    gabarito = {
        g["ticket_id"]: g
        for g in json.loads((ROOT / "eval" / "expected-paths.json").read_text())
    }
    chamados = {
        c["ticket_id"]: c
        for c in json.loads((ROOT / "agent-input" / "cases.json").read_text())
    }

    por_caso: dict[str, dict[str, list[Trace]]] = {}
    pontuacoes: dict[str, dict[tuple[str, int], Scores]] = {}
    configs: dict[str, Any] = {}

    for braco, diretorio in run_dirs.items():
        traces, indexado = _load(Path(diretorio))
        pontuacoes[braco] = indexado
        if traces:
            configs[braco] = json.loads(traces[0].config.model_dump_json())
        for t in traces:
            chave = t.ticket_id or t.case_id
            por_caso.setdefault(chave, {}).setdefault(braco, []).append(t)

    casos = []
    for ticket_id in sorted(por_caso):
        ouro = gabarito.get(ticket_id, {})
        chamado = chamados.get(ticket_id, {})
        casos.append(
            {
                "ticket_id": ticket_id,
                "case_id": chamado.get("id"),
                "message": chamado.get("message"),
                "asset_id": chamado.get("asset_id"),
                "root_question": ouro.get("root_question"),
                "scenario_mode": ouro.get("mode"),
                "expected_path": [
                    {"step": s["step"], "note": s.get("note", ""),
                     "endpoint": str(parse_step(s["step"])[0])}
                    for s in ouro.get("expected_path", [])
                ],
                "arms": {
                    braco: _arm_payload(traces, pontuacoes[braco])
                    for braco, traces in sorted(por_caso[ticket_id].items())
                },
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configs": configs,
        "arms": sorted(configs) or sorted({b for c in casos for b in c["arms"]}),
        "cases": casos,
    }


def export_types(destino: Path) -> None:
    """Gera o JSON Schema do `Trace` e do `Scores` para virar tipo TypeScript.

    Escrever os tipos à mão em TS criaria uma segunda fonte de verdade que
    divergiria em silêncio — mostrando campo vazio na tela em vez de erro. É o
    mesmo argumento que fez os schemas das ferramentas saírem do OpenAPI.

    Usa `models_json_schema`, e não dois `model_json_schema()` aninhados à mão:
    cada modelo carrega as próprias definições em `$defs` com `$ref` apontando
    para a raiz, então empilhá-los sob um `$defs` externo quebra as referências
    (`Missing $ref pointer "#/$defs/Arm"`). A API combinada emite um `$defs`
    único e compartilhado.
    """
    from pydantic.json_schema import models_json_schema

    _, schema = models_json_schema(
        [(Trace, "validation"), (Scores, "validation")],
        ref_template="#/$defs/{model}",
    )

    # O gerador de TypeScript nomeia interfaces a partir do tipo da raiz. Um
    # schema que só tem `$defs` não tem raiz, e ele emite uma interface vazia.
    # Apontar a raiz para os dois modelos faz cada `$def` virar uma interface
    # nomeada.
    schema.update(
        {
            "title": "AgentSchemas",
            "type": "object",
            "properties": {
                "trace": {"$ref": "#/$defs/Trace"},
                "scores": {"$ref": "#/$defs/Scores"},
            },
            "required": ["trace", "scores"],
        }
    )

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Exporta os dados do inspetor.")
    parser.add_argument("--arm", action="append", default=[], metavar="BRACO=DIR",
                        help="ex.: --arm A=runs/braco-A --arm B=runs/braco-B")
    parser.add_argument("--out", default="ui/public/data/runs.json")
    parser.add_argument("--schema-out", default="ui/src/schema.json")
    args = parser.parse_args(argv)

    if not args.arm:
        args.arm = ["A=runs/braco-A", "B=runs/braco-B"]

    diretorios = {}
    for entrada in args.arm:
        braco, _, caminho = entrada.partition("=")
        if Path(caminho).exists():
            diretorios[braco] = Path(caminho)
        else:
            print(f"(pulando {braco}: {caminho} nao existe)")

    if not diretorios:
        print("nenhum diretorio de execucao encontrado")
        return 1

    payload = build_payload(diretorios)
    destino = Path(args.out)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    export_types(Path(args.schema_out))

    tamanho = destino.stat().st_size
    execucoes = sum(a["total_runs"] for c in payload["cases"] for a in c["arms"].values())
    print(f"{len(payload['cases'])} casos · {execucoes} execucoes · "
          f"bracos {', '.join(payload['arms'])}")
    print(f"{destino} ({tamanho / 1024:.0f} KB)")
    print(f"{args.schema_out} (schemas de Trace e Scores)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
