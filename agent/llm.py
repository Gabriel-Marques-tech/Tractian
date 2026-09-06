"""Cliente de modelo com dois backends.

Medido nesta máquina, com `qwen2.5:1.5b` e as mesmas 3 ferramentas:

    nativo /api/chat        -> tool_calls: SIM
    compat /v1              -> tool_calls: NAO
    compat /v1 + required   -> tool_calls: NAO (tool_choice ignorado)

A camada compatível com OpenAI do Ollama não emite `tool_calls` para este
modelo. Como o experimento inteiro mede escolha de ferramenta e acurácia de
argumento, usar `/v1` mediria o bug do transporte, não o agente.

Daí os dois backends: `ollama` fala o protocolo nativo, `openai` fala o
compatível. O resto do código não sabe qual está em uso, então trocar de
provedor continua sendo mudar configuração.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ToolRequest:
    id: str
    name: str
    arguments: dict[str, Any]
    recovered: bool = False
    """Veio de texto em prosa, não do campo `tool_calls`.

    Marcado para que a taxa de resgate seja reportável em vez de escondida:
    "quantas chamadas o agente só conseguiu fazer porque o cliente resgatou"
    é medida de robustez, não detalhe de implementação.
    """


@dataclass
class Completion:
    content: str | None
    tool_calls: list[ToolRequest] = field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


_CALL_KEYS = {"name", "arguments"}


def recover_tool_calls(content: str | None,
                       valid_names: list[str]) -> list[ToolRequest]:
    """Extrai chamadas que o modelo escreveu como texto em vez de emitir.

    Medido: `qwen2.5:1.5b` com 18 ferramentas escreve
    `{"name": "get_rms", "arguments": {...}}` no corpo da resposta. A escolha
    de ferramenta está correta; o que falha é o protocolo. Descartar isso
    mediria a formatação do modelo em vez do raciocínio do agente.

    Só resgata nome que existe entre as ferramentas expostas. Sem essa trava,
    qualquer JSON em prosa viraria chamada.
    """
    if not content:
        return []

    permitidos = set(valid_names)
    encontrados: list[ToolRequest] = []

    # Varredura por chaves balanceadas: `json.JSONDecoder.raw_decode` a partir
    # de cada `{` encontra objetos embutidos em prosa e em bloco de código sem
    # precisar de expressão regular para JSON aninhado.
    decoder = json.JSONDecoder()
    posicao = 0
    while True:
        inicio = content.find("{", posicao)
        if inicio == -1:
            break
        try:
            objeto, fim = decoder.raw_decode(content, inicio)
        except json.JSONDecodeError:
            posicao = inicio + 1
            continue
        posicao = fim

        if not isinstance(objeto, dict) or not _CALL_KEYS <= objeto.keys():
            continue
        nome = objeto.get("name")
        if nome not in permitidos:
            continue

        argumentos = _as_dict(objeto.get("arguments"))
        encontrados.append(
            ToolRequest(
                id=f"recovered_{len(encontrados)}",
                name=nome,
                # O modelo preenche opcionais com null; o servidor não deve
                # recebê-los como se tivessem sido informados.
                arguments={k: v for k, v in argumentos.items() if v is not None},
                recovered=True,
            )
        )

    return encontrados


def _to_ollama_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Traduz o historico do formato OpenAI para o nativo do Ollama.

    O formato OpenAI e a forma canonica interna, porque e o denominador comum
    entre provedores. O nativo difere em dois pontos que causam HTTP 400:

    - `tool_calls[].function.arguments` e objeto, nao string JSON
    - mensagens de resultado nao carregam `tool_call_id`; carregam `tool_name`
    """
    out: list[dict[str, Any]] = []
    id_to_name: dict[str, str] = {}

    for message in messages:
        role = message.get("role")

        if role == "assistant" and message.get("tool_calls"):
            calls = []
            for call in message["tool_calls"]:
                fn = call.get("function", {})
                if call.get("id"):
                    id_to_name[call["id"]] = fn.get("name", "")
                calls.append(
                    {"function": {"name": fn.get("name"), "arguments": _as_dict(fn.get("arguments"))}}
                )
            out.append(
                {"role": "assistant", "content": message.get("content") or "", "tool_calls": calls}
            )
            continue

        if role == "tool":
            entry: dict[str, Any] = {"role": "tool", "content": message.get("content") or ""}
            name = id_to_name.get(message.get("tool_call_id", ""))
            if name:
                entry["tool_name"] = name
            out.append(entry)
            continue

        out.append({"role": role, "content": message.get("content") or ""})

    return out


class LLMClient:
    """`backend` é inferido da base_url quando não informado."""

    def __init__(self, base_url: str, model: str, backend: str | None = None,
                 temperature: float = 0.0, timeout: float = 240.0,
                 keep_alive: str = "30m", max_output_tokens: int = 512) -> None:
        self.model = model
        self.keep_alive = keep_alive
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

        if backend is None:
            backend = "ollama" if "11434" in base_url and "/v1" not in base_url else "openai"
        self.backend = backend

    async def chat(self, messages: list[dict[str, Any]],
                   tools: list[dict[str, Any]] | None = None) -> Completion:
        if self.backend == "ollama":
            resposta = await self._ollama(messages, tools)
        else:
            resposta = await self._openai(messages, tools)

        # Resgate só quando o campo estruturado veio vazio: se o modelo emitiu
        # `tool_calls` corretamente, não há nada a recuperar e mexer no texto
        # só criaria chamada duplicada.
        if not resposta.tool_calls and tools:
            nomes = [t.get("function", {}).get("name", "") for t in tools]
            recuperadas = recover_tool_calls(resposta.content, nomes)
            if recuperadas:
                resposta.tool_calls = recuperadas
                # O texto era a chamada, não resposta ao cliente. Mantê-lo
                # faria o JSON cru vazar para o histórico e para o relatório.
                resposta.content = ""
        return resposta

    async def _ollama(self, messages, tools) -> Completion:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": _to_ollama_messages(messages),
            "stream": False,
            "options": {
                "temperature": self.temperature,
                # Teto de geracao. Um turno de agente e uma tool call ou uma
                # resposta curta; sem teto, entrada anomala faz o modelo correr
                # solto. Medido: TKT-CTX-01, cuja mensagem mistura portugues e
                # caracteres chineses (`间隙`), gerou por 900s ate o timeout.
                "num_predict": self.max_output_tokens,
            },
            # Mantém o modelo residente entre as execuções do batch. Sem isso o
            # Ollama o descarrega por ociosidade e cada recarga custa dezenas de
            # segundos — medido: 28s a frio contra 2s com o modelo já carregado.
            "keep_alive": self.keep_alive,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=self.timeout) as http:
            response = await http.post(f"{self.base_url}/api/chat", json=payload)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"ollama HTTP {response.status_code}: {response.text[:400]}"
                )
            body = response.json()

        message = body.get("message", {}) or {}
        calls = [
            ToolRequest(
                id=call.get("id") or f"call_{i}",
                name=call["function"]["name"],
                arguments=_as_dict(call["function"].get("arguments")),
            )
            for i, call in enumerate(message.get("tool_calls") or [])
        ]
        return Completion(
            content=message.get("content"),
            tool_calls=calls,
            prompt_tokens=body.get("prompt_eval_count"),
            completion_tokens=body.get("eval_count"),
        )

    async def _openai(self, messages, tools) -> Completion:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
        }
        if tools:
            payload["tools"] = tools

        headers = {"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', 'none')}"}
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            response = await http.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"openai-compat HTTP {response.status_code}: {response.text[:400]}"
                )
            body = response.json()

        message = body["choices"][0]["message"]
        usage = body.get("usage") or {}
        calls = [
            ToolRequest(
                id=call.get("id") or f"call_{i}",
                name=call["function"]["name"],
                arguments=_as_dict(call["function"].get("arguments")),
            )
            for i, call in enumerate(message.get("tool_calls") or [])
        ]
        return Completion(
            content=message.get("content"),
            tool_calls=calls,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
