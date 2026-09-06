import { useEffect, useMemo, useState } from "react";
import type { ArmRuns, Case, Payload, Run, Step } from "./types";
import "./styles.css";

/**
 * Inspetor de traces.
 *
 * Lê um único JSON estático e não fala com backend nenhum em runtime. As
 * seções seguem a ordem acordada: passo a passo, comparação entre braços,
 * resposta final, trajetória contra o gabarito, e placar.
 */

const MODE_LABEL: Record<string, string> = {
  complete: "completo",
  partial: "parcial",
  inconclusive: "inconclusivo",
  conflict: "conflito",
  unavailable: "indisponível",
};

function ModeTag({ mode }: { mode: string | null }) {
  if (!mode) return null;
  return (
    <span className={`tag mode-${mode}`} title={`mode da API: ${mode}`}>
      {MODE_LABEL[mode] ?? mode}
    </span>
  );
}

/** Um passo: o que foi chamado, com que argumentos, e o que voltou. */
function StepRow({ step }: { step: Step }) {
  const [open, setOpen] = useState(false);
  const args = Object.entries(step.arguments).filter(([, v]) => v != null);

  return (
    <li className={step.refused ? "step refused" : "step"}>
      <button className="step-head" onClick={() => setOpen((v) => !v)}>
        <span className="step-n">{step.step}</span>
        <code className="step-path">{step.path}</code>
        <ModeTag mode={step.mode} />
        {step.is_impact && <span className="tag impact">impacto</span>}
        {step.refused && <span className="tag refused">recusado</span>}
        {step.recovered_from_text && (
          <span className="tag recovered" title="o modelo escreveu a chamada como texto; o cliente resgatou">
            resgatado
          </span>
        )}
        {step.role !== "react" && <span className="tag role">{step.role}</span>}
        <span className="step-ms">{step.duration_ms} ms</span>
      </button>

      {args.length > 0 && (
        <div className="step-args">
          {args.map(([k, v]) => (
            <span key={k}>
              <b>{k}</b>=<code>{String(v)}</code>
            </span>
          ))}
        </div>
      )}

      {step.notes && <p className="step-notes">{step.notes}</p>}
      {step.refusal_reason && <p className="step-notes danger">{step.refusal_reason}</p>}
      {step.error && !step.refused && <p className="step-notes danger">{step.error}</p>}

      {open && (
        <pre className="step-data">{JSON.stringify(step.data, null, 2)}</pre>
      )}
    </li>
  );
}

/** Trajetória executada contra o gabarito, passo a passo. */
function Trajectory({ run, expected }: { run: Run; expected: string[] }) {
  const linhas = Math.max(run.path.length, expected.length);
  return (
    <table className="traj">
      <thead>
        <tr>
          <th>Executada</th>
          <th />
          <th>Gabarito</th>
        </tr>
      </thead>
      <tbody>
        {Array.from({ length: linhas }, (_, i) => {
          const esq = run.path[i];
          const dir = expected[i];
          const igual = esq && dir && esq === dir;
          return (
            <tr key={i} className={igual ? "hit" : undefined}>
              <td>{esq ? <code>{esq}</code> : <span className="faded">—</span>}</td>
              <td className="mark">{igual ? "=" : ""}</td>
              <td>{dir ? <code>{dir}</code> : <span className="faded">—</span>}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Scoreboard({ run }: { run: Run }) {
  const s = run.scores;
  if (!s) return <p className="faded">sem pontuação</p>;

  // Os tipos gerados marcam como opcional todo campo que tem default no
  // pydantic, o que é mais fiel que assumir presença: um trace antigo, gravado
  // antes de a métrica existir, chega sem ela.
  const num = (v: number | undefined) => (v == null ? "—" : v.toFixed(2));
  const qtd = (v: unknown[] | undefined) => String(v?.length ?? 0);

  const itens: [string, string][] = [
    ["Trajetória", num(s.trajectory?.similarity)],
    ["Recall", num(s.tool_selection?.recall)],
    ["Precisão", num(s.tool_selection?.precision)],
    ["Argumentos", num(s.arguments?.accuracy ?? undefined)],
    ["Passos faltando", qtd(s.trajectory?.missing)],
    ["Passos a mais", qtd(s.trajectory?.unexpected)],
    ["Ações exigidas não feitas", qtd(s.impact?.missing)],
    ["Ações não pedidas", qtd(s.impact?.unrequested)],
    ["Sem justificativa", qtd(s.safety?.unjustified)],
    ["Recusas do gate", String(s.safety?.refused_by_gate ?? 0)],
  ];

  return (
    <div className="score">
      {itens.map(([k, v]) => (
        <div key={k}>
          <span className="score-v">{v}</span>
          <span className="score-k">{k}</span>
        </div>
      ))}
    </div>
  );
}

function ArmPanel({
  arm,
  data,
  expected,
}: {
  arm: string;
  data: ArmRuns;
  expected: string[];
}) {
  const [i, setI] = useState(data.representative);
  const run = data.runs[i] ?? data.runs[0];
  if (!run) return null;

  const estavel = data.same_path_count === data.total_runs;

  return (
    <section className="arm">
      <header className="arm-head">
        <h3>Braço {arm}</h3>
        <span className={estavel ? "stability stable" : "stability"}>
          {data.same_path_count} de {data.total_runs} execuções seguiram este caminho
        </span>
        <select value={i} onChange={(e) => setI(Number(e.target.value))}>
          {data.runs.map((r, idx) => (
            <option key={idx} value={idx}>
              repetição {r.repetition}
            </option>
          ))}
        </select>
      </header>

      <p className="run-meta">
        {run.model_calls} chamadas ao modelo · {run.duration_s}s · parada:{" "}
        <b>{run.stop_reason ?? "—"}</b>
      </p>

      <h4>Passo a passo</h4>
      {run.steps.length === 0 ? (
        <p className="faded">nenhuma ferramenta chamada</p>
      ) : (
        <ul className="steps">
          {run.steps.map((s) => (
            <StepRow key={s.step} step={s} />
          ))}
        </ul>
      )}

      {Object.keys(run.role_notes).length > 0 && (
        <>
          <h4>Deliberação</h4>
          <dl className="notes">
            {Object.entries(run.role_notes).map(([papel, texto]) => (
              <div key={papel}>
                <dt>{papel}</dt>
                <dd>{texto}</dd>
              </div>
            ))}
          </dl>
        </>
      )}

      <h4>Resposta ao cliente</h4>
      <blockquote className="answer">
        {run.final_answer?.trim() || <span className="faded">(sem resposta)</span>}
      </blockquote>

      <h4>Trajetória</h4>
      <Trajectory run={run} expected={expected} />

      <h4>Placar</h4>
      <Scoreboard run={run} />
    </section>
  );
}

export default function App() {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ticket, setTicket] = useState<string | null>(null);

  useEffect(() => {
    fetch("./data/runs.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d: Payload) => {
        setPayload(d);
        setTicket(d.cases[0]?.ticket_id ?? null);
      })
      .catch((e) => setErro(String(e)));
  }, []);

  const caso: Case | undefined = useMemo(
    () => payload?.cases.find((c) => c.ticket_id === ticket),
    [payload, ticket],
  );

  if (erro)
    return (
      <main className="empty">
        <h1>Sem dados</h1>
        <p>
          Falhou ao ler <code>data/runs.json</code>: {erro}
        </p>
        <p>
          Gere com <code>python -m agent.export</code>.
        </p>
      </main>
    );

  if (!payload || !caso) return <main className="empty">carregando…</main>;

  const expected = caso.expected_path.map((e) => e.endpoint);

  return (
    <main>
      <header className="top">
        <h1>Inspetor de traces</h1>
        <select value={ticket ?? ""} onChange={(e) => setTicket(e.target.value)}>
          {payload.cases.map((c) => (
            <option key={c.ticket_id} value={c.ticket_id}>
              {c.ticket_id}
            </option>
          ))}
        </select>
        <span className="faded">
          {payload.cases.length} casos · braços {payload.arms.join(", ")} ·{" "}
          {payload.configs[payload.arms[0]]?.model} · seed{" "}
          {payload.configs[payload.arms[0]]?.seed}
        </span>
      </header>

      <section className="case">
        <p className="msg">{caso.message}</p>
        <p className="root">
          <b>Pergunta raiz:</b> {caso.root_question ?? "—"}
        </p>
      </section>

      <div className="arms">
        {payload.arms
          .filter((a) => caso.arms[a])
          .map((a) => (
            <ArmPanel key={a} arm={a} data={caso.arms[a]} expected={expected} />
          ))}
      </div>
    </main>
  );
}
