import type { ArmRuns, Case, Payload, Run } from "./types";

/**
 * Agregações para a visão geral.
 *
 * Calculadas no cliente a partir do mesmo `runs.json` que alimenta a inspeção,
 * em vez de virem prontas do exportador. Assim existe uma fonte de dados só, e
 * o que a tela mostra é sempre derivável do que o avaliador pode auditar
 * clicando no passo.
 */

export interface ArmStats {
  arm: string;
  runs: number;
  trajectory: number;
  recall: number;
  precision: number;
  modelCalls: number;
  seconds: number;
  /** Fração de casos cujas repetições produziram todas o mesmo caminho. */
  deterministic: number;
  cases: number;
  grounding: number | null;
  groundingN: number;
  answerQuality: number;
  citedValues: number;
  hallucinated: number;
  unrequestedImpact: number;
  refusedByGate: number;
  recovered: number;
  totalCalls: number;
}

const mean = (xs: number[]) =>
  xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;

export function runsOf(caso: Case, arm: string): Run[] {
  return caso.arms[arm]?.runs ?? [];
}

/** Média da similaridade de trajetória de um braço num caso. */
export function caseScore(caso: Case, arm: string): number | null {
  const rs = runsOf(caso, arm);
  if (!rs.length) return null;
  return mean(rs.map((r) => r.scores?.trajectory?.similarity ?? 0));
}

export function statsFor(payload: Payload, arm: string): ArmStats {
  const todas = payload.cases.flatMap((c) => runsOf(c, arm));
  const braços: ArmRuns[] = payload.cases
    .map((c) => c.arms[arm])
    .filter(Boolean) as ArmRuns[];

  const ancoragens = todas
    .map((r) => r.scores?.judgement?.grounding)
    .filter((g) => g && g.score != null) as { score: number }[];

  return {
    arm,
    runs: todas.length,
    cases: braços.length,
    trajectory: mean(todas.map((r) => r.scores?.trajectory?.similarity ?? 0)),
    recall: mean(todas.map((r) => r.scores?.tool_selection?.recall ?? 0)),
    precision: mean(todas.map((r) => r.scores?.tool_selection?.precision ?? 0)),
    modelCalls: mean(todas.map((r) => r.model_calls)),
    seconds: mean(todas.map((r) => r.duration_s)),
    deterministic: braços.length
      ? braços.filter((b) => b.same_path_count === b.total_runs).length / braços.length
      : 0,
    grounding: ancoragens.length ? mean(ancoragens.map((g) => g.score)) : null,
    groundingN: ancoragens.length,
    answerQuality: mean(
      todas.map((r) => r.scores?.judgement?.answer_quality ?? 0),
    ),
    citedValues: todas.reduce(
      (n, r) => n + (r.scores?.judgement?.grounding?.cited ?? 0),
      0,
    ),
    hallucinated: todas.reduce(
      (n, r) => n + (r.scores?.judgement?.grounding?.hallucinated?.length ?? 0),
      0,
    ),
    unrequestedImpact: todas.reduce(
      (n, r) => n + (r.scores?.impact?.unrequested?.length ?? 0),
      0,
    ),
    refusedByGate: todas.reduce(
      (n, r) => n + (r.scores?.safety?.refused_by_gate ?? 0),
      0,
    ),
    recovered: todas.reduce(
      (n, r) => n + r.steps.filter((s) => s.recovered_from_text).length,
      0,
    ),
    totalCalls: todas.reduce((n, r) => n + r.steps.length, 0),
  };
}

/**
 * Teste t pareado por caso entre dois braços.
 *
 * Existe na tela porque a diferença bruta entre médias é a leitura mais fácil
 * de fazer errado: com 17 casos e este tamanho de efeito, quase nada sobrevive.
 * Mostrar a média sem o intervalo convidaria a ler ruído como sinal.
 */
export interface PairedTest {
  metric: string;
  diff: number;
  t: number;
  ciLow: number;
  ciHigh: number;
  ties: number;
  n: number;
  significant: boolean;
}

export function pairedTest(
  payload: Payload,
  a: string,
  b: string,
  metric: string,
  pick: (r: Run) => number | null | undefined,
): PairedTest {
  const difs: number[] = [];
  let ties = 0;

  for (const caso of payload.cases) {
    const va = runsOf(caso, a).map(pick).filter((v) => v != null) as number[];
    const vb = runsOf(caso, b).map(pick).filter((v) => v != null) as number[];
    if (!va.length || !vb.length) continue;
    const d = mean(va) - mean(vb);
    if (Math.abs(d) < 1e-9) ties++;
    difs.push(d);
  }

  const n = difs.length;
  const m = mean(difs);
  const sd =
    n > 1
      ? Math.sqrt(difs.reduce((s, d) => s + (d - m) ** 2, 0) / (n - 1))
      : 0;
  const se = sd / Math.sqrt(n || 1);
  const t = se ? m / se : 0;
  const ci = 1.96 * se;

  return {
    metric,
    diff: m,
    t,
    ciLow: m - ci,
    ciHigh: m + ci,
    ties,
    n,
    // t crítico bilateral para gl=16, α=0,05.
    significant: Math.abs(t) > 2.12,
  };
}
