"""Objetos de análise 4 e 5, medidos por regra sobre o trace.

O único juiz disponível seria o `qwen2.5:1.5b` que produziu as respostas. Um
modelo julgando a si mesmo produz um número que não se defende, e um de 1,5B é
juiz fraco mesmo julgando outro. Regra sobre o trace é auditável linha a linha
e não custa chamada de modelo — o que mantém **nove de nove** objetos de
análise com custo zero de pontuação.

Três critérios, cada um de 0 a 5:

- **Ancoragem** (objeto 4): dos valores que a resposta cita, quantos aparecem na
  evidência que o agente de fato recebeu. Mede o modo de falha observado nas
  execuções: afirmar sobre dado que não foi consultado.
- **Reconhecimento da degradação** (objeto 5): a resposta menciona os `mode` que
  ocorreram. Concluir com confiança sobre dado `unavailable` é a falha central
  do problema, e ela é detectável sem interpretar texto.
- **Cobertura da pergunta raiz** (objeto 5): quanto dos termos de `root_question`
  a resposta toca.

Limitação declarada: alucinação de **interpretação** escapa. Dizer "baseline
estabelecido" quando ele está em `learning` é falso e passa, porque nenhum valor
foi inventado. Só valor citado e menção de `mode` são pegáveis por regra.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Iterable

from pydantic import BaseModel, Field

from agent.trace import Trace

RUBRIC_VERSION = "1.0"
"""Versão da rubrica, gravada junto de cada nota.

O critério de aceite pedia prompt versionado. Sem prompt, o equivalente é isto:
um número precisa saber sob que regra foi produzido, senão comparar notas de
execuções diferentes vira comparação entre rubricas diferentes.
"""

MODE_TERMS: dict[str, tuple[str, ...]] = {
    "partial": ("parcial", "incompleto", "faltam", "faltando", "ausente"),
    "inconclusive": ("inconclusiv", "nao conclusiv", "nao sustenta", "insuficiente"),
    "conflict": ("conflit", "divergen", "discordam", "contradi"),
    "unavailable": ("indisponivel", "nao disponivel", "sem dado", "nao existe",
                    "offline", "sem informacao"),
    "complete": (),
}
"""Como cada degradação costuma ser reconhecida em português.

`complete` não tem termo: não há nada a reconhecer quando o dado veio íntegro.
"""

# Um "valor" é número (com ou sem decimal) ou identificador do domínio
# (`asset_C710`, `mdl_vib_v3`). Palavra comum não conta: senão qualquer termo da
# resposta viraria "valor citado" e a ancoragem mediria prosa, não dado.
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_IDENT = re.compile(r"\b[a-zA-Z]+(?:_[a-zA-Z0-9]+)+\b|\b[A-Za-z]{1,6}\d{2,}\b")
"""Identificador do domínio.

Duas formas: `asset_C710` com underscore, e o código curto `S420` sem ele. A
segunda existe porque a resposta costuma citar o sufixo (`o ativo S420`)
enquanto a evidência traz o id completo (`asset_S420`) — sem ela, o sufixo
virava o número solto `420` e era contado como alucinação em 13 traces.
"""
_LIST_MARKER = re.compile(r"(?m)^\s{0,3}(?:[-*+]|\d{1,2}[.)])\s+")
"""Marcador de lista markdown.

109 das 154 "alucinações" medidas no braço A eram numeradores de lista — "1.",
"2.", "3.". A rubrica contava enumerador como valor citado e penalizava quem
escreve resposta organizada.
"""

MIN_DIGITS = 3
"""Inteiro com menos dígitos que isto não conta como valor de domínio.

Timestamps na evidência (`2024-07-01T10:00:00Z`) espalham `07`, `01`, `10`,
`00` e davam âncora grátis: 31 dos 226 valores "sustentados" eram números de um
ou dois dígitos. Ordinais ("1º"), horas e percentuais caem no mesmo balde.

**Decimal escapa da regra**: `4.2 mm/s` é medição, e o limiar de RMS vive
nessa ordem de grandeza. Contar dígitos ignorando o separador descartaria
justamente o dado mais relevante do domínio.
"""

STOPWORDS = {
    "por", "que", "nao", "ha", "apesar", "da", "do", "de", "a", "o", "e", "as",
    "os", "um", "uma", "para", "com", "em", "no", "na", "qual", "quais", "como",
    "foi", "ser", "esta", "sao", "dos", "das", "ao", "aos", "se", "ou", "mais",
}


def _fold(texto: str) -> str:
    """Minúsculas sem acento, para comparar termo com termo."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()


def values_in(texto: str | None) -> set[str]:
    """Valores citáveis num texto: números e identificadores do domínio.

    Os identificadores saem primeiro e o texto restante é que fornece os
    números. Sem isso, `asset_C710` conta como dois valores — o identificador e
    o `710` dentro dele — inflando o denominador da ancoragem.
    """
    if not texto:
        return set()
    limpo = _LIST_MARKER.sub(" ", texto)
    identificadores = {m.group() for m in _IDENT.finditer(limpo)}
    resto = _IDENT.sub(" ", limpo)
    numeros = {
        m.group().replace(",", ".")
        for m in _NUMBER.finditer(resto)
        if ("." in m.group() or "," in m.group()) or len(m.group()) >= MIN_DIGITS
    }
    return numeros | identificadores


def _evidence_values(trace: Trace) -> set[str]:
    """O que a plataforma de fato devolveu, mais o próprio chamado.

    **Os argumentos da chamada ficam de fora.** Incluí-los deixava o agente
    sustentar o que ele mesmo havia inventado: em `case_tkt_inv_06` o modelo
    fabricou o id `case_tkt_inv_06_asset_S420`, a API devolveu 404, e a
    ancoragem dava 5/5 porque o argumento contava como evidência.

    **Chamada que falhou também fica de fora.** Resposta com erro não entrega
    dado, então não pode ancorar afirmação.

    O chamado do cliente entra: repetir um valor que o cliente informou não é
    inventar.
    """
    encontrados = values_in(trace.message)
    for call in trace.steps:
        if not call.ok or call.refused:
            continue
        encontrados |= values_in(json.dumps(call.data, ensure_ascii=False, default=str))
        encontrados |= values_in(call.notes)

    # `asset_S420` também sustenta uma resposta que diz apenas `S420`. Só os
    # pedaços com dígito entram: `asset` sozinho casaria com qualquer coisa.
    partes = {
        pedaco
        for valor in encontrados
        for pedaco in valor.split("_")
        if any(c.isdigit() for c in pedaco) and len(pedaco) >= MIN_DIGITS
    }
    return encontrados | partes


def _scale(fracao: float) -> int:
    """Fração em [0,1] para nota inteira de 0 a 5."""
    return max(0, min(5, round(fracao * 5)))


class Grounding(BaseModel):
    """Objeto de análise 4."""

    cited: int = 0
    supported: int = 0
    hallucinated: list[str] = Field(default_factory=list)

    score: int | None = None
    """`None` quando a resposta não cita valor nenhum.

    Silêncio e fabricação não são a mesma falha. Dos 93 traces que pontuavam 0
    na primeira versão, 60 apenas não citaram valor — colapsar os dois numa nota
    só tornava a média ilegível.
    """


class Degradation(BaseModel):
    """Parte do objeto 5: enfrentou a degradação que os dados trouxeram?"""

    occurred: list[str] = Field(default_factory=list)
    acknowledged: list[str] = Field(default_factory=list)
    score: int = 0


class RootQuestion(BaseModel):
    """Parte do objeto 5: respondeu ao que foi perguntado?"""

    terms: int = 0
    covered: int = 0
    score: int = 0


class Judgement(BaseModel):
    """Nota dos objetos 4 e 5, com a rubrica que a produziu."""

    rubric_version: str = RUBRIC_VERSION
    grounding: Grounding = Field(default_factory=Grounding)
    degradation: Degradation = Field(default_factory=Degradation)
    root_question: RootQuestion = Field(default_factory=RootQuestion)
    answer_quality: int = 0
    """Objeto 5: média de reconhecimento da degradação e cobertura da pergunta."""


def _grounding(trace: Trace) -> Grounding:
    resposta = trace.final_answer or ""
    citados = values_in(resposta)
    if not citados:
        # Sem valor citado não há ancoragem a medir. `score=None` deixa a
        # agregação ignorar o caso em vez de contá-lo como fabricação total.
        return Grounding()

    evidencia = _evidence_values(trace)
    sustentados = citados & evidencia
    inventados = sorted(citados - evidencia)

    return Grounding(
        cited=len(citados),
        supported=len(sustentados),
        hallucinated=inventados,
        score=_scale(len(sustentados) / len(citados)),
    )


def _degradation(trace: Trace) -> Degradation:
    resposta = _fold(trace.final_answer or "")
    ocorridos = sorted(
        {c.mode.value for c in trace.steps if c.mode and MODE_TERMS.get(c.mode.value)}
    )
    if not ocorridos:
        # Nada a reconhecer não pode contar como falha de reconhecimento.
        return Degradation(score=5)

    reconhecidos = [
        modo for modo in ocorridos
        if any(termo in resposta for termo in MODE_TERMS[modo])
    ]
    return Degradation(
        occurred=ocorridos,
        acknowledged=reconhecidos,
        score=_scale(len(reconhecidos) / len(ocorridos)),
    )


def _root_question(trace: Trace, root_question: str | None) -> RootQuestion:
    if not root_question:
        return RootQuestion(score=5)

    termos = {
        t for t in re.findall(r"[a-zA-Zà-üÀ-Ü]{3,}", _fold(root_question))
        if t not in STOPWORDS
    }
    if not termos:
        return RootQuestion(score=5)

    resposta = _fold(trace.final_answer or "")
    cobertos = {t for t in termos if t in resposta}
    return RootQuestion(
        terms=len(termos),
        covered=len(cobertos),
        score=_scale(len(cobertos) / len(termos)),
    )


def judge(trace: Trace, root_question: str | None = None) -> Judgement:
    """Pontua os objetos 4 e 5. Função pura: sem rede, sem modelo."""
    if not (trace.final_answer or "").strip():
        return Judgement()

    ancoragem = _grounding(trace)
    degradacao = _degradation(trace)
    pergunta = _root_question(trace, root_question)

    return Judgement(
        grounding=ancoragem,
        degradation=degradacao,
        root_question=pergunta,
        answer_quality=round((degradacao.score + pergunta.score) / 2),
    )
