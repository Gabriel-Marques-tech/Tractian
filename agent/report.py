"""Agregação dos resultados e tabelas para a documentação.

Função pura sobre o que o runner gravou: recebe `Scores` e `Trace`, devolve
números e markdown. Sem rede, sem modelo — reanalisar não custa re-executar,
que é a razão de o trace ser persistido em vez de resumido em memória.

A agregação sempre reporta **desvio entre repetições** junto da média. Média
sozinha esconde o objeto de análise 8: dois braços com a mesma média e
variâncias diferentes não são equivalentes, e o que decide se uma diferença
entre braços significa alguma coisa é o tamanho dela contra o ruído de cada um.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from agent.scorer import Scores
from agent.trace import Trace

CATEGORIES = {"CTX": "contextualizar", "INV": "investigar", "EXE": "executar"}


def category_of(ticket_id: str | None) -> str:
    """`"TKT-INV-05"` -> `"investigar"`.

    As três categorias exigem comportamentos diferentes do agente, então a
    média global pode esconder que um braço só é melhor numa delas.
    """
    if not ticket_id:
        return "desconhecida"
    partes = ticket_id.split("-")
    return CATEGORIES.get(partes[1], "desconhecida") if len(partes) > 1 else "desconhecida"


@dataclass
class Metric:
    """Média e dispersão de uma métrica."""

    name: str
    values: list[float] = field(default_factory=list)

    @property
    def mean(self) -> float:
        return statistics.fmean(self.values) if self.values else 0.0

    @property
    def stdev(self) -> float:
        return statistics.stdev(self.values) if len(self.values) > 1 else 0.0

    def __str__(self) -> str:
        return f"{self.mean:.2f} ± {self.stdev:.2f}"


@dataclass
class ArmReport:
    """Tudo que se sabe sobre um braço."""

    arm: str
    runs: int = 0

    trajectory: Metric = field(default_factory=lambda: Metric("trajetória"))
    recall: Metric = field(default_factory=lambda: Metric("recall"))
    precision: Metric = field(default_factory=lambda: Metric("precisão"))

    answered: int = 0
    grounding: Metric = field(default_factory=lambda: Metric("ancoragem"))
    answer_quality: Metric = field(default_factory=lambda: Metric("qualidade"))
    degradation: Metric = field(default_factory=lambda: Metric("degradação"))
    root_question: Metric = field(default_factory=lambda: Metric("pergunta raiz"))
    cited_values: int = 0
    hallucinated_values: int = 0
    impact_missing: int = 0
    impact_unrequested: int = 0
    config_changes: int = 0
    unjustified: int = 0
    refused: int = 0
    recovered_calls: int = 0
    total_calls: int = 0

    model_calls: int = 0
    wall_seconds: float = 0.0

    by_mode: dict[str, int] = field(default_factory=dict)
    by_category: dict[str, Metric] = field(default_factory=dict)
    stability: dict[str, float] = field(default_factory=dict)
    """Desvio da similaridade entre repetições, por caso."""

    @property
    def seconds_per_run(self) -> float:
        return self.wall_seconds / self.runs if self.runs else 0.0

    @property
    def calls_per_run(self) -> float:
        return self.model_calls / self.runs if self.runs else 0.0

    @property
    def mean_instability(self) -> float:
        vals = list(self.stability.values())
        return statistics.fmean(vals) if vals else 0.0

    @property
    def hallucination_rate(self) -> float:
        """Por valor citado, não em absoluto.

        Contagem absoluta pune quem cita mais dado: o braço A cita 346 valores
        e o B apenas 74, então 154 contra 40 alucinações inverteria a leitura.
        """
        return self.hallucinated_values / self.cited_values if self.cited_values else 0.0

    @property
    def recovery_rate(self) -> float:
        return self.recovered_calls / self.total_calls if self.total_calls else 0.0


def aggregate(scores: Iterable[Scores], traces: Iterable[Trace] | None = None) -> ArmReport:
    """Agrega as pontuações de um braço. `traces` acrescenta custo e resgates."""
    lista = list(scores)
    relatorio = ArmReport(arm=lista[0].arm if lista else "?", runs=len(lista))

    por_caso: dict[str, list[float]] = {}
    por_categoria: dict[str, Metric] = {}

    for s in lista:
        relatorio.trajectory.values.append(s.trajectory.similarity)
        relatorio.recall.values.append(s.tool_selection.recall)
        relatorio.precision.values.append(s.tool_selection.precision)
        relatorio.answered += int(s.answered)

        j = s.judgement
        # `None` significa "sem valor citado, nada a medir" — entrar como 0
        # misturaria silêncio com fabricação e puxaria a média para baixo.
        if j.grounding.score is not None:
            relatorio.grounding.values.append(float(j.grounding.score))
        relatorio.answer_quality.values.append(float(j.answer_quality))
        relatorio.degradation.values.append(float(j.degradation.score))
        relatorio.root_question.values.append(float(j.root_question.score))
        relatorio.cited_values += j.grounding.cited
        relatorio.hallucinated_values += len(j.grounding.hallucinated)

        relatorio.impact_missing += len(s.impact.missing)
        relatorio.impact_unrequested += len(s.impact.unrequested)
        relatorio.config_changes += len(s.impact.unrequested_config_changes)
        relatorio.unjustified += len(s.safety.unjustified)
        relatorio.refused += s.safety.refused_by_gate

        for modo, quantas in s.modes.items():
            relatorio.by_mode[modo] = relatorio.by_mode.get(modo, 0) + quantas

        chave = s.ticket_id or s.case_id
        por_caso.setdefault(chave, []).append(s.trajectory.similarity)

        categoria = category_of(s.ticket_id)
        por_categoria.setdefault(categoria, Metric(categoria)).values.append(
            s.trajectory.similarity
        )

    relatorio.by_category = por_categoria
    relatorio.stability = {
        caso: statistics.stdev(vals) if len(vals) > 1 else 0.0
        for caso, vals in por_caso.items()
    }

    for t in traces or []:
        relatorio.model_calls += t.model_calls
        relatorio.wall_seconds += t.duration_s
        for c in t.steps:
            relatorio.total_calls += 1
            relatorio.recovered_calls += int(c.recovered_from_text)

    return relatorio


# --- tabelas ------------------------------------------------------------------


def _row(*células: str) -> str:
    return "| " + " | ".join(células) + " |"


def comparison_table(relatorios: list[ArmReport]) -> str:
    """Tabela principal: os braços lado a lado."""
    cabecalho = ["Métrica"] + [f"Braço {r.arm}" for r in relatorios]
    linhas = [_row(*cabecalho), _row(*["---"] * len(cabecalho))]

    def linha(rotulo, fn):
        linhas.append(_row(rotulo, *[fn(r) for r in relatorios]))

    linha("Execuções", lambda r: str(r.runs))
    linha("Trajetória", lambda r: str(r.trajectory))
    linha("Recall de ferramentas", lambda r: str(r.recall))
    linha("Precisão de ferramentas", lambda r: str(r.precision))
    linha("Respondeu", lambda r: f"{r.answered}/{r.runs}")
    linha("Instabilidade média", lambda r: f"{r.mean_instability:.3f}")
    linha("Chamadas ao modelo por execução", lambda r: f"{r.calls_per_run:.1f}")
    linha("Segundos por execução", lambda r: f"{r.seconds_per_run:.0f}")
    linha("Ações exigidas não executadas", lambda r: str(r.impact_missing))
    linha("Ações executadas sem o caso pedir", lambda r: str(r.impact_unrequested))
    linha("Alterações de config indevidas", lambda r: str(r.config_changes))
    linha("Ações sem justificativa", lambda r: str(r.unjustified))
    linha("Recusas do gate", lambda r: str(r.refused))
    linha("Chamadas resgatadas de texto", lambda r: f"{r.recovery_rate:.0%}")
    linha("Ancoragem (objeto 4)",
          lambda r: f"{r.grounding} (n={len(r.grounding.values)})")
    linha("Respostas que citam dado", lambda r: f"{len(r.grounding.values)}/{r.runs}")
    linha("Qualidade da resposta (objeto 5)", lambda r: str(r.answer_quality))
    linha("— reconhece a degradação", lambda r: str(r.degradation))
    linha("— cobre a pergunta raiz", lambda r: str(r.root_question))
    linha("Valores citados", lambda r: str(r.cited_values))
    linha("Alucinação por valor citado", lambda r: f"{r.hallucination_rate:.0%}")
    return "\n".join(linhas)


def category_table(relatorios: list[ArmReport]) -> str:
    """Por categoria de caso: a média global pode esconder onde o ganho está."""
    categorias = sorted({c for r in relatorios for c in r.by_category})
    cabecalho = ["Categoria"] + [f"Braço {r.arm}" for r in relatorios]
    linhas = [_row(*cabecalho), _row(*["---"] * len(cabecalho))]

    for categoria in categorias:
        células = []
        for r in relatorios:
            m = r.by_category.get(categoria)
            células.append(f"{m} (n={len(m.values)})" if m else "—")
        linhas.append(_row(categoria, *células))
    return "\n".join(linhas)


def mode_table(relatorios: list[ArmReport]) -> str:
    """Quanta degradação cada braço enfrentou.

    Sob a mesma seed os braços deveriam ver quase a mesma distribuição; uma
    diferença grande aqui indica que trajetórias diferentes tocaram recursos
    diferentes, e não que a API tratou os braços de forma distinta.
    """
    modos = sorted({m for r in relatorios for m in r.by_mode})
    cabecalho = ["`mode` da API"] + [f"Braço {r.arm}" for r in relatorios]
    linhas = [_row(*cabecalho), _row(*["---"] * len(cabecalho))]

    for modo in modos:
        linhas.append(_row(f"`{modo}`", *[str(r.by_mode.get(modo, 0)) for r in relatorios]))
    return "\n".join(linhas)


# --- ponto de entrada ---------------------------------------------------------


def load_arm(run_dir: str | Path) -> tuple[list[Scores], list[Trace]]:
    """Lê `scores.jsonl` e `traces.jsonl` de um diretório de execução."""
    d = Path(run_dir)
    scores_path, traces_path = d / "scores.jsonl", d / "traces.jsonl"

    scores = [
        Scores.model_validate_json(l)
        for l in (scores_path.read_text(encoding="utf-8").splitlines()
                  if scores_path.exists() else [])
        if l.strip()
    ]
    return scores, list(Trace.read_jsonl(traces_path))


COMPARABLE_FIELDS = ("seed", "model", "max_steps", "max_model_calls", "user_id")
"""O que precisa ser idêntico para dois braços serem comparáveis.

A arquitetura é a única variável que o experimento manipula. Qualquer outra
diferença é variável de confusão, e a mais perigosa é a `seed`: ela decide a
degradação que a API devolve, então braços com seeds diferentes enfrentam
ambientes diferentes e a comparação deixa de significar alguma coisa.
"""


def comparability_warnings(configs: dict[str, dict]) -> list[str]:
    """Campos que diferem entre braços e não deveriam.

    Existe porque já aconteceu: uma bateria rodou com `--config` e a outra sem,
    caindo no default, e os braços compararam sob seeds diferentes. O numero
    saiu sem nenhum sinal de que o ambiente havia mudado.
    """
    avisos = []
    for campo in COMPARABLE_FIELDS:
        valores = {braco: cfg.get(campo) for braco, cfg in configs.items()}
        if len(set(map(str, valores.values()))) > 1:
            detalhe = ", ".join(f"{b}={v!r}" for b, v in sorted(valores.items()))
            avisos.append(f"`{campo}` difere entre os braços: {detalhe}")
    return avisos


def render(relatorios: list[ArmReport]) -> str:
    """Documento markdown com as três tabelas."""
    partes = [
        "## Comparação entre braços",
        "",
        comparison_table(relatorios),
        "",
        "## Por categoria de caso",
        "",
        "As três categorias exigem comportamentos diferentes, então a média",
        "global pode esconder que um braço só é melhor numa delas.",
        "",
        category_table(relatorios),
        "",
        "## Degradação enfrentada",
        "",
        "Sob a mesma seed os braços deveriam ver distribuição parecida. Uma",
        "diferença grande indica que trajetórias diferentes tocaram recursos",
        "diferentes, não que a API tratou os braços de forma distinta.",
        "",
        mode_table(relatorios),
        "",
        "## Estabilidade entre repetições",
        "",
    ]
    for r in relatorios:
        instaveis = sorted(r.stability.items(), key=lambda kv: -kv[1])[:5]
        partes.append(f"**Braço {r.arm}** — instabilidade média {r.mean_instability:.3f}")
        partes.append("")
        if instaveis and instaveis[0][1] > 0:
            partes.extend(
                [f"- `{caso}`: desvio {desvio:.3f}" for caso, desvio in instaveis if desvio > 0]
            )
        else:
            partes.append("- todas as repetições produziram a mesma trajetória")
        partes.append("")
    return "\n".join(partes)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Agrega resultados dos braços.")
    parser.add_argument("dirs", nargs="+", help="diretórios de execução")
    parser.add_argument("--out", help="arquivo markdown de saída")
    args = parser.parse_args(argv)

    relatorios = []
    configs: dict[str, dict] = {}
    for d in args.dirs:
        scores, traces = load_arm(d)
        if not scores:
            print(f"(sem pontuações em {d})")
            continue
        relatorio = aggregate(scores, traces)
        relatorios.append(relatorio)
        if traces:
            configs[relatorio.arm] = json.loads(traces[0].config.model_dump_json())

    avisos = comparability_warnings(configs) if len(configs) > 1 else []
    if avisos:
        print("=" * 70)
        print("COMPARACAO INVALIDA — os bracos nao rodaram sob as mesmas condicoes")
        for a in avisos:
            print(f"  - {a}")
        print("A arquitetura deve ser a unica variavel. Refaca o braco divergente.")
        print("=" * 70)
        return 2

    if not relatorios:
        print("nenhum resultado encontrado")
        return 1

    documento = render(relatorios)
    print(documento)
    if args.out:
        Path(args.out).write_text(documento + "\n", encoding="utf-8")
        print(f"\nsalvo em {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
