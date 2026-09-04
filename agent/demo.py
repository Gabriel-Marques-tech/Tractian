"""Demo: roda um caso oficial no braço A e compara a trajetória com o gabarito.

    python -m agent.demo                 # caso padrao
    python -m agent.demo TKT-INV-05
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from agent.react import baseline_config, run_case

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / "agent-input" / "cases.json").read_text())
GOLD = {
    g["ticket_id"]: g
    for g in json.loads((ROOT / "eval" / "expected-paths.json").read_text())
}


async def main() -> None:
    ticket = sys.argv[1] if len(sys.argv) > 1 else "TKT-INV-05"
    case = next(c for c in CASES if c["ticket_id"] == ticket)
    gold = GOLD[ticket]
    config = baseline_config()

    print("=" * 78)
    print(f"CASO {ticket}  ({case['id']})")
    print(f"Chamado do cliente: {case['message']}")
    print(f"Pergunta raiz (gabarito): {gold['root_question']}")
    print(f"Modelo: {config.model}   seed: {config.seed}   braco: {config.arm.value}")
    print("=" * 78)

    print("\nEXECUCAO")
    trace = await run_case(case, config, verbose=True)

    print("\nRESPOSTA AO CLIENTE")
    print("-" * 78)
    print((trace.final_answer or "(sem resposta)").strip()[:1500])

    executed = trace.path()
    expected = [s["step"] for s in gold["expected_path"]]

    print("\nTRAJETORIA")
    print("-" * 78)
    width = max([len(s) for s in executed + expected] + [20]) + 2
    print(f"{'EXECUTADA':<{width}}{'GABARITO'}")
    for i in range(max(len(executed), len(expected))):
        left = executed[i] if i < len(executed) else ""
        right = expected[i] if i < len(expected) else ""
        mark = "=" if left == right else " "
        print(f"{left:<{width}}{mark} {right}")

    hits = len(set(executed) & set(expected))
    print(f"\nferramentas certas       : {hits}/{len(set(expected))}")
    print(f"chamadas ao modelo       : {trace.model_calls}")
    print(f"chamadas de ferramenta   : {len(trace.steps)}")
    print(f"tokens (prompt/resposta) : {trace.prompt_tokens}/{trace.completion_tokens}")
    print(f"motivo de parada         : {trace.stop_reason.value if trace.stop_reason else '-'}")
    print(f"tempo de parede          : {trace.duration_s:.1f}s")
    print(f"modes retornados pela API: {trace.modes_seen()}")
    if trace.refusals():
        print(f"acoes recusadas pelo gate: {len(trace.refusals())}")
    if trace.error:
        print(f"erro                     : {trace.error}")

    out = ROOT / "runs" / f"demo-{ticket}.jsonl"
    trace.append_to(out)
    print(f"\ntrace anexado em {out.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
