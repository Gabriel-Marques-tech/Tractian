import { useEffect, useMemo, useState } from "react";
import type { Case, Payload, Run, Step } from "./types";
import { caseScore, pairedTest, statsFor } from "./stats";
import "./styles.css";

/**
 * Inspetor de traces.
 *
 * Três níveis de hierarquia, do resumo ao dado cru:
 *
 * 1. **Visão geral** — o veredito do experimento e o teste de significância.
 *    É o que responde "e aí, deu o quê?" sem nenhum clique.
 * 2. **Lista de casos** — barra de pontuação por braço, escaneável, para achar
 *    o caso interessante sem abrir os dezessete.
 * 3. **Inspeção** — abas por dimensão, e o JSON cru atrás de um clique.
 *
 * Lê um único JSON estático; não fala com backend depois de carregado.
 */

const MODE_LABEL: Record<string, string> = {
  complete: "completo",
  partial: "parcial",
  inconclusive: "inconclusivo",
  conflict: "conflito",
  unavailable: "indisponível",
};

const ABAS = ["Trajetória", "Passo a passo", "Resposta", "Deliberação", "Placar"] as const;
type Aba = (typeof ABAS)[number];

const pct = (v: number) => `${Math.round(v * 100)}%`;
const dec = (v: number | null | undefined, casas = 2) =>
  v == null ? "—" : v.toFixed(casas);

// --- blocos pequenos ----------------------------------------------------------

function ModeTag({ mode }: { mode: string | null }) {
  if (!mode) return null;
  return (
    <span className={`tag mode-${mode}`} title={`mode devolvido pela API: ${mode}`}>
      {MODE_LABEL[mode] ?? mode}
    </span>
  );
}

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "ok" | "warn" | "bad";
}) {
  return (
    <div className={tone ? `stat stat-${tone}` : "stat"}>
      <div className="stat-v">{value}</div>
      <div className="stat-k">{label}</div>
      {hint && <div className="stat-h">{hint}</div>}
    </div>
  );
}

/** Barra dupla: pontuação de cada braço no caso, para varrer a lista com o olho. */
function ScoreBars({ caso, arms }: { caso: Case; arms: string[] }) {
  return (
    <span className="bars">
      {arms.map((a) => {
        const s = caseScore(caso, a);
        return (
          <span key={a} className="bar" title={`braço ${a}: ${dec(s)}`}>
            <span
              className={`bar-fill bar-${a}`}
              style={{ width: `${Math.max(2, (s ?? 0) * 100)}%` }}
            />
          </span>
        );
      })}
    </span>
  );
}

// --- nível 1: visão geral -----------------------------------------------------

function Overview({ payload }: { payload: Payload }) {
  const stats = payload.arms.map((a) => statsFor(payload, a));
  const [a, b] = payload.arms;

  const testes =
    a && b
      ? [
          pairedTest(payload, a, b, "Trajetória", (r) => r.scores?.trajectory?.similarity),
          pairedTest(payload, a, b, "Recall", (r) => r.scores?.tool_selection?.recall),
          pairedTest(payload, a, b, "Precisão", (r) => r.scores?.tool_selection?.precision),
          pairedTest(payload, a, b, "Ancoragem", (r) => r.scores?.judgement?.grounding?.score),
          pairedTest(payload, a, b, "Qualidade da resposta", (r) =>
            r.scores?.judgement?.answer_quality,
          ),
        ]
      : [];

  const algumSignificante = testes.some((t) => t.significant);

  return (
    <div className="panel">
      <div className="verdict">
        <h2>
          {algumSignificante
            ? "Há diferença de qualidade detectável entre as arquiteturas"
            : "Nenhuma diferença de qualidade sobrevive ao teste"}
        </h2>
        <p>
          {stats.map((s) => `${s.runs} execuções no braço ${s.arm}`).join(" · ")}
          {" · "}modelo {payload.configs[payload.arms[0]]?.model}
          {" · "}seed {payload.configs[payload.arms[0]]?.seed}
        </p>
      </div>

      {stats.map((s) => (
        <section key={s.arm} className="arm-summary">
          <h3>Braço {s.arm}</h3>
          <div className="stats">
            <Stat label="Trajetória" value={dec(s.trajectory)} hint="contra o gabarito" />
            <Stat label="Recall" value={dec(s.recall)} hint="de ferramentas" />
            <Stat label="Precisão" value={dec(s.precision)} hint="de ferramentas" />
            <Stat
              label="Ancoragem"
              value={dec(s.grounding, 2)}
              hint={`de 5, em ${s.groundingN} respostas que citam dado`}
            />
            <Stat
              label="Chamadas ao modelo"
              value={dec(s.modelCalls, 1)}
              hint="por execução"
              tone={s.modelCalls > 3 ? "warn" : "ok"}
            />
            <Stat label="Segundos" value={dec(s.seconds, 0)} hint="por execução" />
            <Stat
              label="Casos determinísticos"
              value={pct(s.deterministic)}
              hint="mesma trajetória nas repetições"
              tone={s.deterministic > 0.8 ? "ok" : "warn"}
            />
            <Stat
              label="Alucinação"
              value={s.citedValues ? pct(s.hallucinated / s.citedValues) : "—"}
              hint="por valor citado"
              tone="warn"
            />
            <Stat
              label="Ações indevidas"
              value={String(s.unrequestedImpact)}
              hint={`${s.refusedByGate} recusadas pelo gate`}
              tone={s.unrequestedImpact ? "bad" : "ok"}
            />
            <Stat
              label="Resgate de texto"
              value={s.totalCalls ? pct(s.recovered / s.totalCalls) : "—"}
              hint="chamadas escritas em prosa"
              tone={s.recovered ? "warn" : "ok"}
            />
          </div>
        </section>
      ))}

      {testes.length > 0 && (
        <section className="arm-summary">
          <h3>Teste t pareado por caso</h3>
          <p className="note">
            A diferença bruta entre médias é a leitura mais fácil de fazer errado.
            Com {testes[0].n} casos e este tamanho de efeito, o intervalo de
            confiança de 95% cruza zero — o que significa que a diferença
            observada é compatível com acaso.
          </p>
          <table className="grid">
            <thead>
              <tr>
                <th>Métrica</th>
                <th>{a} − {b}</th>
                <th>t</th>
                <th>IC 95%</th>
                <th>Empates</th>
                <th>Significante</th>
              </tr>
            </thead>
            <tbody>
              {testes.map((t) => (
                <tr key={t.metric}>
                  <td>{t.metric}</td>
                  <td className="num">{t.diff >= 0 ? "+" : ""}{dec(t.diff, 3)}</td>
                  <td className="num">{dec(t.t, 2)}</td>
                  <td className="num faded">
                    [{dec(t.ciLow, 3)}; {dec(t.ciHigh, 3)}]
                  </td>
                  <td className="num">{t.ties}/{t.n}</td>
                  <td className={t.significant ? "sig" : "faded"}>
                    {t.significant ? "sim" : "não"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

// --- nível 3: abas de inspeção ------------------------------------------------

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
        {step.refused && <span className="tag bad">recusado</span>}
        {step.recovered_from_text && (
          <span className="tag info" title="o modelo escreveu a chamada como texto; o cliente resgatou">
            resgatado
          </span>
        )}
        {step.role !== "react" && <span className="tag">{step.role}</span>}
        <span className="grow" />
        <span className="faded small">{step.duration_ms} ms</span>
        <span className="chev">{open ? "−" : "+"}</span>
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
      {step.refusal_reason && <p className="step-notes bad-text">{step.refusal_reason}</p>}
      {step.error && !step.refused && <p className="step-notes bad-text">{step.error}</p>}
      {open && <pre className="raw">{JSON.stringify(step.data, null, 2)}</pre>}
    </li>
  );
}

function TabContent({
  aba,
  run,
  expected,
}: {
  aba: Aba;
  run: Run;
  expected: string[];
}) {
  const s = run.scores;

  if (aba === "Trajetória") {
    const linhas = Math.max(run.path.length, expected.length);
    return (
      <table className="grid traj">
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

  if (aba === "Passo a passo") {
    return run.steps.length ? (
      <ul className="steps">
        {run.steps.map((st) => (
          <StepRow key={st.step} step={st} />
        ))}
      </ul>
    ) : (
      <p className="faded">nenhuma ferramenta chamada nesta execução</p>
    );
  }

  if (aba === "Resposta") {
    return (
      <blockquote className="answer">
        {run.final_answer?.trim() || <span className="faded">(sem resposta)</span>}
      </blockquote>
    );
  }

  if (aba === "Deliberação") {
    const notas = Object.entries(run.role_notes);
    return notas.length ? (
      <dl className="notes">
        {notas.map(([papel, texto]) => (
          <div key={papel}>
            <dt>{papel}</dt>
            <dd>{texto}</dd>
          </div>
        ))}
      </dl>
    ) : (
      <p className="faded">
        Sem deliberação: no braço de nó único não há papéis a inspecionar.
      </p>
    );
  }

  const j = s?.judgement;
  return (
    <div className="stats">
      <Stat label="Trajetória" value={dec(s?.trajectory?.similarity)} />
      <Stat label="Recall" value={dec(s?.tool_selection?.recall)} />
      <Stat label="Precisão" value={dec(s?.tool_selection?.precision)} />
      <Stat
        label="Ancoragem"
        value={dec(j?.grounding?.score, 0)}
        hint={
          j?.grounding?.cited
            ? `${j.grounding.supported}/${j.grounding.cited} valores na evidência`
            : "não citou valor"
        }
      />
      <Stat label="Reconhece degradação" value={dec(j?.degradation?.score, 0)} hint="de 5" />
      <Stat label="Cobre a pergunta raiz" value={dec(j?.root_question?.score, 0)} hint="de 5" />
      <Stat label="Passos faltando" value={String(s?.trajectory?.missing?.length ?? 0)} />
      <Stat label="Passos a mais" value={String(s?.trajectory?.unexpected?.length ?? 0)} />
      <Stat
        label="Ações não pedidas"
        value={String(s?.impact?.unrequested?.length ?? 0)}
        tone={s?.impact?.unrequested?.length ? "bad" : undefined}
      />
      <Stat label="Recusas do gate" value={String(s?.safety?.refused_by_gate ?? 0)} />
      {j?.grounding?.hallucinated?.length ? (
        <div className="stat stat-wide">
          <div className="stat-k">Valores sem evidência</div>
          <div className="chips">
            {j.grounding.hallucinated.map((v) => (
              <code key={v} className="chip">{v}</code>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ArmPanel({
  arm,
  caso,
  aba,
  expected,
}: {
  arm: string;
  caso: Case;
  aba: Aba;
  expected: string[];
}) {
  const dados = caso.arms[arm];
  const [i, setI] = useState(dados?.representative ?? 0);
  if (!dados) return null;
  const run = dados.runs[i] ?? dados.runs[0];
  if (!run) return null;

  const estavel = dados.same_path_count === dados.total_runs;

  return (
    <section className="arm">
      <header className="arm-head">
        <h3>Braço {arm}</h3>
        <span className={estavel ? "stability ok" : "stability warn"}>
          {dados.same_path_count} de {dados.total_runs} seguiram este caminho
        </span>
        <span className="grow" />
        <select value={i} onChange={(e) => setI(Number(e.target.value))}>
          {dados.runs.map((r, idx) => (
            <option key={idx} value={idx}>
              repetição {r.repetition}
            </option>
          ))}
        </select>
      </header>

      <p className="run-meta">
        {run.model_calls} chamadas ao modelo · {run.duration_s}s · parada{" "}
        <b>{run.stop_reason ?? "—"}</b>
      </p>

      <TabContent aba={aba} run={run} expected={expected} />
    </section>
  );
}

// --- casca --------------------------------------------------------------------

export default function App() {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ticket, setTicket] = useState<string | null>(null);
  const [aba, setAba] = useState<Aba>("Trajetória");

  useEffect(() => {
    fetch("./data/runs.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setPayload)
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
          Gere com <code>python -m agent.export</code> e rebuilde a interface — o
          Vite copia <code>ui/public/</code> no momento do build.
        </p>
      </main>
    );

  if (!payload) return <main className="empty">carregando…</main>;

  const expected = caso?.expected_path.map((e) => e.endpoint) ?? [];

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <strong>Inspetor de traces</strong>
          <span className="faded small">TRACTIAN × Inteli</span>
        </div>

        <button
          className={ticket === null ? "nav active" : "nav"}
          onClick={() => setTicket(null)}
        >
          Visão geral
        </button>

        <div className="side-label">
          Casos <span className="faded">({payload.cases.length})</span>
        </div>

        <ul className="caselist">
          {payload.cases.map((c) => (
            <li key={c.ticket_id}>
              <button
                className={c.ticket_id === ticket ? "case active" : "case"}
                onClick={() => setTicket(c.ticket_id)}
              >
                <span className="case-id">{c.ticket_id}</span>
                <ScoreBars caso={c} arms={payload.arms} />
              </button>
            </li>
          ))}
        </ul>

        <div className="legend">
          {payload.arms.map((a) => (
            <span key={a}>
              <i className={`swatch bar-${a}`} /> braço {a}
            </span>
          ))}
          <span className="faded small">barra = trajetória do caso</span>
        </div>
      </aside>

      <main className="main">
        {!caso ? (
          <Overview payload={payload} />
        ) : (
          <div className="panel">
            <header className="case-head">
              <h2>{caso.ticket_id}</h2>
              <p className="msg">{caso.message}</p>
              <p className="root">
                <b>Pergunta raiz:</b> {caso.root_question ?? "—"}
              </p>
            </header>

            <nav className="tabs">
              {ABAS.map((t) => (
                <button
                  key={t}
                  className={t === aba ? "tab active" : "tab"}
                  onClick={() => setAba(t)}
                >
                  {t}
                </button>
              ))}
            </nav>

            <div className="arms">
              {payload.arms
                .filter((a) => caso.arms[a])
                .map((a) => (
                  <ArmPanel
                    key={`${caso.ticket_id}-${a}`}
                    arm={a}
                    caso={caso}
                    aba={aba}
                    expected={expected}
                  />
                ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
