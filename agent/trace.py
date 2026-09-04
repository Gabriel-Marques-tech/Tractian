"""Schema do Trace.

O `Trace` é o contrato entre as duas metades do projeto: o agente produz, o
avaliador consome. Nenhum dos dois lados conhece o outro além deste módulo.

Congelado no ticket #1 de propósito: #2 (baseline) e #4 (scorer) dependem dele
em paralelo, e um schema instável obrigaria os dois a refazer.

A forma sai de duas pontas que já existem em disco:

- o que entra: a resposta de uma ferramenta MCP, `{request, mode, notes, data}`
- o que sai:   `eval/expected-paths.json`, cuja unidade é a string `"GET /assets/asset_G501"`

`ToolCall.as_path_step()` é a ponte entre as duas, e é o que o scorer compara.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Self

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Arm(str, Enum):
    """Braço do experimento. A variável que o experimento manipula."""

    BASELINE = "A"          # ReAct de nó único
    MULTI_AGENT = "B"       # pipeline de seis papéis


class StopReason(str, Enum):
    """Por que o agente parou. Política de parada explícita é objeto de análise."""

    ANSWERED = "answered"                # produziu resposta final
    ESCALATED = "escalated"              # escalou para humano
    MAX_STEPS = "max_steps"              # bateu no limite de passos
    MAX_MODEL_CALLS = "max_model_calls"  # bateu no limite de chamadas ao modelo
    ERROR = "error"                      # falhou


class Mode(str, Enum):
    """Grau de degradação da resposta da API industrial.

    Espelha `api/app/prob.py`. Não é erro: toda leitura devolve HTTP 200 e
    declara aqui o quanto o `data` é confiável.
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    INCONCLUSIVE = "inconclusive"
    CONFLICT = "conflict"
    UNAVAILABLE = "unavailable"


class ToolCall(BaseModel):
    """Uma chamada de ferramenta e o que ela devolveu."""

    step: int
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    # Origem da chamada. No braço A é sempre "react"; no braço B é o papel
    # (planejador, orquestrador_tools, ...) e a instância, quando há fan-out.
    role: str = "react"
    role_instance: int = 0

    # Reconstrução do passo no vocabulário do gabarito.
    http_method: str | None = None
    http_path: str | None = None

    # Envelope da API preservado inteiro. O `mode` é informação, não ruído:
    # descartá-lo apagaria o fenômeno que o experimento estuda.
    mode: Mode | None = None
    notes: str | None = None
    data: Any = None

    ok: bool = True
    error: str | None = None

    # Ações de impacto. `refused` marca recusa pelo gate do servidor MCP, que é
    # evento de segurança medível, não falha de execução.
    is_impact: bool = False
    justification: str | None = None
    refused: bool = False
    refusal_reason: str | None = None

    started_at: datetime = Field(default_factory=_now)
    duration_ms: int = 0

    def as_path_step(self) -> str:
        """Renderiza no formato do gabarito: `"GET /assets/asset_G501"`.

        É a unidade que o scorer compara contra `expected_path[].step`.
        Sem método/caminho resolvidos, cai no nome da ferramenta para que o
        passo ainda apareça na trajetória em vez de sumir.
        """
        if self.http_method and self.http_path:
            return f"{self.http_method} {self.http_path}"
        return self.tool


class RunConfig(BaseModel):
    """Tudo que precisa ser idêntico para duas execuções serem comparáveis."""

    arm: Arm
    model: str
    model_base_url: str
    api_base_url: str

    # Seed repassada à API industrial. Mesma seed = mesma degradação, que é o
    # que torna a comparação entre braços justa.
    seed: str | None = None
    user_id: str | None = None

    max_steps: int = 20
    max_model_calls: int = 40
    fan_out: int = 1

    # Repetição do mesmo caso sob a mesma config, para medir estabilidade.
    repetition: int = 0


class Trace(BaseModel):
    """Registro completo de uma execução. A unidade que o avaliador consome."""

    case_id: str
    ticket_id: str | None = None
    message: str | None = None
    config: RunConfig

    steps: list[ToolCall] = Field(default_factory=list)

    final_answer: str | None = None
    stop_reason: StopReason | None = None

    model_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None

    error: str | None = None

    # --- construção -------------------------------------------------------

    def record(self, call: ToolCall) -> ToolCall:
        """Anexa uma chamada, numerando o passo."""
        call.step = len(self.steps) + 1
        self.steps.append(call)
        return call

    def finish(self, stop_reason: StopReason, final_answer: str | None = None) -> Self:
        self.stop_reason = stop_reason
        self.final_answer = final_answer
        self.finished_at = _now()
        return self

    # --- leitura ----------------------------------------------------------

    @property
    def duration_s(self) -> float:
        end = self.finished_at or _now()
        return (end - self.started_at).total_seconds()

    def path(self) -> list[str]:
        """Trajetória no vocabulário do gabarito, em ordem.

        Chamadas recusadas pelo gate ficam de fora: a ação não aconteceu, e
        contá-la como passo dado inflaria a trajetória com tentativa negada.
        Elas continuam no trace e são medidas pela métrica de segurança.
        """
        return [c.as_path_step() for c in self.steps if not c.refused]

    def tools_used(self) -> set[str]:
        return {c.tool for c in self.steps if not c.refused}

    def impact_calls(self, *, executed_only: bool = True) -> list[ToolCall]:
        return [c for c in self.steps if c.is_impact and (not executed_only or not c.refused)]

    def refusals(self) -> list[ToolCall]:
        return [c for c in self.steps if c.refused]

    def modes_seen(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for c in self.steps:
            if c.mode is not None:
                counts[c.mode.value] = counts.get(c.mode.value, 0) + 1
        return counts

    # --- persistência -----------------------------------------------------

    def append_to(self, path: str | Path) -> None:
        """Grava uma linha JSONL.

        Incremental de propósito: o Colab derruba sessão em 12h ou por
        ociosidade, e trace escrito só no fim é trace perdido.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(self.model_dump_json() + "\n")

    @classmethod
    def read_jsonl(cls, path: str | Path) -> Iterator["Trace"]:
        p = Path(path)
        if not p.exists():
            return
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield cls.model_validate(json.loads(line))
