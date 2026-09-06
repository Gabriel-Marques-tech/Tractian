"""Smoke test de sinal: o portão antes de qualquer bateria grande.

O desenho do experimento empilha quatro fontes de variância — fluxo variável
decidido pelo orquestrador, fan-out, degradação da API e um modelo de 1,5B. Se a
variância dentro de um braço superar a diferença esperada entre braços, as 170
execuções da bateria oficial não concluem nada.

Este módulo custa alguns minutos e responde isso antes de comprometer horas. Se
não houver sinal, a resposta é **reduzir variância** — fixar o fluxo, desligar o
fan-out, aumentar repetições — e não rodar mais.

`summarize()` é puro: recebe pontuações, devolve o diagnóstico. Testável sem
modelo e sem rede.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Iterable

from agent.scorer import Scores

# Três casos, um de cada categoria do gabarito, para o smoke não medir só um
# tipo de investigação.
SMOKE_CASES = ["TKT-CTX-01", "TKT-INV-05", "TKT-EXE-16"]

FLOOR = 0.05
"""Abaixo disso o braço não acerta nada, e não há o que comparar.

Efeito de piso é diagnóstico diferente de variância alta: os dois impedem a
comparação, mas por motivos opostos e com correções opostas.
"""

NOISE = 0.15
"""Desvio-padrão dentro do caso acima do qual a variância domina.

Referência: uma diferença plausível entre arquiteturas está na casa de 0,1 a
0,2 de similaridade de trajetória. Ruído dessa ordem dentro do próprio braço
torna a comparação incapaz de distinguir as duas.
"""


MIN_DEPTH = 0.5
"""Fração dos passos do gabarito que um caso precisa ao menos tentar.

Avaliada **por caso**, e o veredito conta quantos ficam abaixo. A média das
frações não serve: um caso cujo gabarito tem um passo só marca profundidade
total com qualquer chamada única, inclusive a errada, e puxa a média para cima
escondendo os casos que o agente abandonou no primeiro passo.

Um agente que dá um passo quando o gabarito pede quatro não está investigando,
e medir arquitetura contra ele mede o prompt, não a arquitetura. É falha
diferente de variância e de piso, e passa despercebida pelas duas: as
repetições podem ser perfeitamente estáveis e a média pode estar acima do
piso, com o agente ainda assim desistindo no primeiro passo.
"""


@dataclass
class CaseSpread:
    """Como um caso se comportou entre as repetições."""

    ticket_id: str
    similarities: list[float] = field(default_factory=list)
    recalls: list[float] = field(default_factory=list)
    trajectories: list[tuple[str, ...]] = field(default_factory=list)
    expected_steps: int = 0

    @property
    def mean_steps(self) -> float:
        return (
            statistics.fmean(len(t) for t in self.trajectories)
            if self.trajectories else 0.0
        )

    @property
    def depth(self) -> float:
        """Passos dados sobre passos esperados."""
        return self.mean_steps / self.expected_steps if self.expected_steps else 1.0

    @property
    def mean_similarity(self) -> float:
        return statistics.fmean(self.similarities) if self.similarities else 0.0

    @property
    def stdev_similarity(self) -> float:
        return statistics.stdev(self.similarities) if len(self.similarities) > 1 else 0.0

    @property
    def distinct_paths(self) -> int:
        return len(set(self.trajectories))

    @property
    def deterministic(self) -> bool:
        return self.distinct_paths == 1


@dataclass
class SmokeVerdict:
    """O diagnóstico e a recomendação."""

    cases: list[CaseSpread] = field(default_factory=list)
    mean_similarity: float = 0.0
    mean_within_case_stdev: float = 0.0
    mean_depth: float = 0.0
    shallow_cases: int = 0
    deterministic_cases: int = 0
    proceed: bool = False
    reason: str = ""

    @property
    def total_cases(self) -> int:
        return len(self.cases)


def summarize(scores: Iterable[Scores]) -> SmokeVerdict:
    """Agrupa por caso e decide se a bateria vale a pena."""
    por_caso: dict[str, CaseSpread] = {}
    for s in scores:
        chave = s.ticket_id or s.case_id
        spread = por_caso.setdefault(chave, CaseSpread(ticket_id=chave))
        spread.similarities.append(s.trajectory.similarity)
        spread.recalls.append(s.tool_selection.recall)
        spread.trajectories.append(tuple(s.trajectory.executed))
        spread.expected_steps = max(spread.expected_steps, len(s.trajectory.expected))

    veredito = SmokeVerdict(cases=list(por_caso.values()))
    if not veredito.cases:
        veredito.reason = "nenhuma execucao pontuada"
        return veredito

    veredito.mean_similarity = statistics.fmean(
        c.mean_similarity for c in veredito.cases
    )
    veredito.mean_within_case_stdev = statistics.fmean(
        c.stdev_similarity for c in veredito.cases
    )
    veredito.mean_depth = statistics.fmean(c.depth for c in veredito.cases)
    veredito.shallow_cases = sum(1 for c in veredito.cases if c.depth < MIN_DEPTH)
    veredito.deterministic_cases = sum(1 for c in veredito.cases if c.deterministic)

    # Piso primeiro: um braço que não acerta nada não tem variância a discutir,
    # e a correção é outra — o problema está no agente, não no tamanho da amostra.
    if veredito.mean_similarity < FLOOR:
        veredito.proceed = False
        veredito.reason = (
            f"efeito de piso: similaridade media {veredito.mean_similarity:.2f}. "
            "O braço A quase nao acerta trajetoria, entao nao ha diferenca a medir "
            "contra o braço B. Corrigir o agente antes de rodar a bateria."
        )
    elif veredito.shallow_cases * 2 >= veredito.total_cases:
        veredito.proceed = False
        veredito.reason = (
            f"o braço nao investiga: {veredito.shallow_cases} de "
            f"{veredito.total_cases} casos ficam abaixo de {MIN_DEPTH:.0%} dos "
            "passos do gabarito antes de responder. Rodar a bateria assim "
            "mediria a politica de parada e o prompt, nao a arquitetura. "
            "Corrigir o agente antes."
        )
    elif veredito.mean_within_case_stdev > NOISE:
        veredito.proceed = False
        veredito.reason = (
            f"variancia domina: desvio medio dentro do caso "
            f"{veredito.mean_within_case_stdev:.2f}, acima de {NOISE:.2f}. "
            "Reduzir variancia (fixar fluxo, desligar fan-out, aumentar "
            "repeticoes) antes de comparar bracos."
        )
    else:
        veredito.proceed = True
        veredito.reason = (
            f"ha sinal: similaridade media {veredito.mean_similarity:.2f} com "
            f"desvio medio {veredito.mean_within_case_stdev:.2f} dentro do caso. "
            f"{veredito.deterministic_cases}/{veredito.total_cases} casos "
            "repetiram a mesma trajetoria."
        )
    return veredito


def extrapolate(seconds_per_run: float, calls_per_run: float, *,
                cases: int = 17, repetitions: int = 5, arms: int = 2) -> dict[str, float]:
    """Custo da bateria oficial, a partir do que o smoke mediu."""
    runs = cases * repetitions * arms
    return {
        "runs": runs,
        "hours": runs * seconds_per_run / 3600,
        "model_calls": runs * calls_per_run,
    }


# --- execução ------------------------------------------------------------------


async def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    from pathlib import Path

    from agent.runner import config_from, load_settings, run_batch

    parser = argparse.ArgumentParser(description="Portao de decisao do experimento.")
    parser.add_argument("--config", default="experiment.json")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--out-dir", dest="out_dir", default="runs/smoke")
    parser.add_argument("--cases", nargs="*", default=SMOKE_CASES)
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    settings = load_settings(
        args.config if Path(args.config).exists() else None,
        {"out_dir": args.out_dir, "repetitions": args.repetitions},
    )
    config = config_from(settings)

    todos = json.loads((root / "agent-input" / "cases.json").read_text())
    gabarito = json.loads((root / "eval" / "expected-paths.json").read_text())
    expected = {g["ticket_id"]: g["expected_path"] for g in gabarito}
    casos = [c for c in todos if c["ticket_id"] in args.cases]

    print("=" * 74)
    print("SMOKE TEST DE SINAL — portao antes da bateria oficial")
    print(f"modelo {config.model} · seed {config.seed} · braco {config.arm.value}")
    print(f"{len(casos)} casos × {args.repetitions} repeticoes = "
          f"{len(casos) * args.repetitions} execucoes")
    print("=" * 74)

    def progresso(trace, resultado) -> None:
        print(f"  {trace.ticket_id:<12} rep {trace.config.repetition}  "
              f"traj {resultado.trajectory.similarity:.2f}  "
              f"recall {resultado.tool_selection.recall:.2f}  "
              f"{trace.model_calls} chamadas  {trace.duration_s:.0f}s")

    resumo = await run_batch(
        config, casos, expected, args.out_dir,
        repetitions=args.repetitions, on_result=progresso,
    )

    if not resumo.scores:
        print("\nNada executado (tudo ja estava gravado). "
              f"Apague {args.out_dir} para rodar de novo.")
        return 1

    veredito = summarize(resumo.scores)

    print("\n" + "-" * 74)
    print("POR CASO")
    for caso in veredito.cases:
        marca = "deterministico" if caso.deterministic else f"{caso.distinct_paths} caminhos"
        print(f"  {caso.ticket_id:<12} similaridade media {caso.mean_similarity:.2f} "
              f"± {caso.stdev_similarity:.2f}   {marca}")

    print("\nCUSTO MEDIDO")
    print(f"  {resumo.seconds_per_run:.1f}s por execucao · "
          f"{resumo.model_calls / resumo.executed:.1f} chamadas ao modelo por execucao")

    custo = extrapolate(
        resumo.seconds_per_run, resumo.model_calls / resumo.executed
    )
    print(f"\nBATERIA OFICIAL EXTRAPOLADA (17 casos × 5 repeticoes × 2 bracos)")
    print(f"  {custo['runs']:.0f} execucoes · {custo['hours']:.1f} horas · "
          f"{custo['model_calls']:.0f} chamadas ao modelo")

    print("\n" + "=" * 74)
    print("SEGUIR PARA A BATERIA" if veredito.proceed else "NAO SEGUIR AINDA")
    print(veredito.reason)
    print("=" * 74)
    return 0 if veredito.proceed else 2


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
