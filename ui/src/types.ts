/**
 * Formato do `runs.json` que `agent/export.py` produz.
 *
 * As formas de `Trace` e `Scores` vêm do pydantic: `npm run types` gera
 * `types.generated.d.ts` a partir de `src/schema.json`, que por sua vez sai de
 * `model_json_schema()`. Escrever esses tipos à mão criaria uma segunda fonte
 * de verdade que divergiria em silêncio — mostrando campo vazio na tela em vez
 * de erro.
 *
 * O que está declarado aqui é só o envelope do exportador, que não existe no
 * pydantic: o agrupamento por caso e o indicador de estabilidade.
 */

/**
 * `Scores` é despejado do pydantic sem transformação, então vem do arquivo
 * gerado. Redigitá-lo aqui seria a segunda fonte de verdade que a geração
 * existe para evitar.
 */
export type { Scores } from "./types.generated";
import type { Scores } from "./types.generated";

export type Mode =
  | "complete"
  | "partial"
  | "inconclusive"
  | "conflict"
  | "unavailable";

export interface Step {
  step: number;
  tool: string;
  path: string;
  arguments: Record<string, unknown>;
  role: string;
  mode: Mode | null;
  notes: string | null;
  data: unknown;
  ok: boolean;
  error: string | null;
  is_impact: boolean;
  justification: string | null;
  refused: boolean;
  refusal_reason: string | null;
  recovered_from_text: boolean;
  duration_ms: number;
}

export interface Run {
  repetition: number;
  steps: Step[];
  path: string[];
  final_answer: string | null;
  stop_reason: string | null;
  error: string | null;
  model_calls: number;
  duration_s: number;
  role_notes: Record<string, string>;
  modes: Record<string, number>;
  scores: Scores | null;
}

export interface ArmRuns {
  runs: Run[];
  total_runs: number;
  /** Quantas das N repetições seguiram o caminho dominante. Objeto de análise 8. */
  same_path_count: number;
  distinct_paths: number;
  representative: number;
}

export interface ExpectedStep {
  step: string;
  note: string;
  /** Método e caminho sem query: a query é argumento, não rota. */
  endpoint: string;
}

export interface Case {
  ticket_id: string;
  case_id: string | null;
  message: string | null;
  asset_id: string | null;
  root_question: string | null;
  scenario_mode: string | null;
  expected_path: ExpectedStep[];
  arms: Record<string, ArmRuns>;
}

export interface RunConfig {
  arm: string;
  model: string;
  seed: string | null;
  max_steps: number;
  max_model_calls: number;
  user_id: string | null;
}

export interface Payload {
  generated_at: string;
  configs: Record<string, RunConfig>;
  arms: string[];
  cases: Case[];
}
