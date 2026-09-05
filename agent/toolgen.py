"""Geração das ferramentas a partir do contrato OpenAPI da API industrial.

Fonte única de verdade: o contrato servido pela própria API em `/openapi.json`,
não a documentação. Escrever 18 schemas à mão criaria uma segunda fonte que
diverge silenciosamente na primeira mudança da API.

O nome de cada ferramenta vem do `summary` da operação ("Get Data Quality" ->
`get_data_quality`), porque o `operationId` que o FastAPI gera é ilegível
(`get_data_quality_assets__asset_id__data_quality_get`) e o nome da ferramenta
é lido pelo modelo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_API = "http://localhost:8000"

# GET consulta; qualquer outro método muda estado da plataforma.
IMPACT_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

JUSTIFICATION_ARG = "justification"
MIN_JUSTIFICATION = 20
"""Espelha `_require_justification` em `api/app/main.py`.

Declarado aqui, ao lado do schema que o usa, para existir num lugar só: o
servidor MCP importa daqui em vez de repetir o número.
"""


def _slug(summary: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", summary.lower()).strip("_")


def _ident(name: str) -> str:
    """Nome de parâmetro da API -> identificador Python válido.

    A API usa cabeçalhos como `x-user-id`, que não são identificadores.
    A tradução é registrada em `ToolSpec.alias` para a volta.
    """
    ident = re.sub(r"[^0-9a-zA-Z_]", "_", name).strip("_")
    if not ident or ident[0].isdigit():
        ident = f"p_{ident}"
    return ident


@dataclass
class ToolSpec:
    name: str
    method: str
    path: str
    summary: str
    description: str
    tag: str
    path_params: list[str] = field(default_factory=list)
    query_params: list[str] = field(default_factory=list)
    header_params: list[str] = field(default_factory=list)
    alias: dict[str, str] = field(default_factory=dict)
    """identificador Python -> nome real do parâmetro na API."""
    body_props: dict[str, Any] = field(default_factory=dict)
    body_required: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)

    @property
    def is_impact(self) -> bool:
        return self.method in IMPACT_METHODS

    def http_step(self, arguments: dict[str, Any]) -> str:
        """Renderiza no formato de `expected_path[].step` do gabarito."""
        rendered = self.path
        for p in self.path_params:
            api_name = self.alias.get(p, p)
            rendered = rendered.replace(
                "{" + api_name + "}", str(arguments.get(p, f"<{p}>"))
            )
        return f"{self.method} {rendered}"


def _resolve(schema: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Resolve um `$ref` de um nível — o suficiente para este contrato."""
    if "$ref" in schema:
        ref = schema["$ref"].split("/")[-1]
        return spec.get("components", {}).get("schemas", {}).get(ref, {})
    return schema


def _clean(schema: dict[str, Any]) -> dict[str, Any]:
    """Achata `anyOf: [T, null]` para T.

    Modelos pequenos lidam mal com `anyOf`; o campo opcional já é comunicado
    por ausência em `required`.
    """
    if "anyOf" in schema:
        non_null = [s for s in schema["anyOf"] if s.get("type") != "null"]
        if len(non_null) == 1:
            merged = dict(non_null[0])
            if "description" in schema:
                merged.setdefault("description", schema["description"])
            return merged
    return {k: v for k, v in schema.items() if k != "title"}


def load_specs(api_base: str = DEFAULT_API) -> list[ToolSpec]:
    """Busca o contrato e devolve uma ToolSpec por operação."""
    doc = httpx.get(f"{api_base}/openapi.json", timeout=20).json()
    specs: list[ToolSpec] = []

    for path, operations in doc["paths"].items():
        for method, op in operations.items():
            if method.upper() not in {"GET", "POST", "PATCH", "PUT", "DELETE"}:
                continue

            spec = ToolSpec(
                name=_slug(op["summary"]),
                method=method.upper(),
                path=path,
                summary=op["summary"],
                description=op.get("description") or op["summary"],
                tag=(op.get("tags") or ["Outros"])[0],
            )

            props: dict[str, Any] = {}
            required: list[str] = []

            for param in op.get("parameters", []):
                schema = _clean(_resolve(param.get("schema", {}), doc))
                if param.get("description"):
                    schema.setdefault("description", param["description"])
                api_name = param["name"]
                py_name = _ident(api_name)
                spec.alias[py_name] = api_name
                props[py_name] = schema

                location = param["in"]
                if location == "path":
                    spec.path_params.append(py_name)
                    required.append(py_name)
                elif location == "header":
                    spec.header_params.append(py_name)
                else:
                    spec.query_params.append(py_name)

            body = op.get("requestBody", {}).get("content", {}).get("application/json", {})
            if body:
                body_schema = _resolve(body.get("schema", {}), doc)
                for prop_name, prop_schema in (body_schema.get("properties") or {}).items():
                    py_name = _ident(prop_name)
                    spec.alias[py_name] = prop_name
                    props[py_name] = _clean(_resolve(prop_schema, doc))
                    spec.body_props[py_name] = props[py_name]
                spec.body_required = [_ident(r) for r in (body_schema.get("required") or [])]
                required.extend(spec.body_required)

            if spec.is_impact and JUSTIFICATION_ARG not in spec.body_props:
                # O contrato mente por omissão: os cinco endpoints de ação
                # recebem `body: dict[str, Any]`, então o OpenAPI não expõe
                # propriedade nenhuma — mas `_require_justification` em
                # `api/app/main.py` rejeita com 400 sem uma `justification` de
                # 20 caracteres ou mais.
                #
                # Sem declarar aqui, o campo não entra em `body_props`, o corpo
                # sai vazio e a API responde 422 antes mesmo de chegar na
                # validação de justificativa.
                schema = {
                    "type": "string",
                    "minLength": MIN_JUSTIFICATION,
                    "description": (
                        f"Justificativa da acao, no minimo {MIN_JUSTIFICATION} "
                        "caracteres. Obrigatoria: a plataforma recusa sem ela."
                    ),
                }
                props[JUSTIFICATION_ARG] = schema
                spec.body_props[JUSTIFICATION_ARG] = schema
                spec.body_required.append(JUSTIFICATION_ARG)
                required.append(JUSTIFICATION_ARG)

            spec.input_schema = {
                "type": "object",
                "properties": props,
                "required": required,
            }
            specs.append(spec)

    return specs


def describe(spec: ToolSpec) -> str:
    """Descrição entregue ao modelo."""
    parts = [spec.description.strip(), f"[{spec.tag}]"]
    if spec.is_impact:
        parts.append(
            "ACAO DE IMPACTO: altera estado da plataforma e exige justificativa."
        )
    return " ".join(parts)


def execute(
    spec: ToolSpec,
    arguments: dict[str, Any],
    api_base: str = DEFAULT_API,
    seed: str | None = None,
    timeout: float = 30.0,
) -> tuple[bool, dict[str, Any]]:
    """Executa a operação. Devolve (ok, envelope-ou-erro).

    O envelope `{mode, notes, data}` sobe intacto: `mode` é a informação de
    degradação, e o experimento inteiro depende dela.
    """
    url = spec.path
    for p in spec.path_params:
        if p not in arguments:
            return False, {"error": f"parametro obrigatorio ausente: {p}"}
        url = url.replace("{" + spec.alias.get(p, p) + "}", str(arguments[p]))

    params = {spec.alias.get(k, k): arguments[k] for k in spec.query_params if k in arguments}
    if seed is not None and "seed" in spec.query_params:
        params["seed"] = seed

    headers = {
        spec.alias.get(k, k): str(arguments[k]) for k in spec.header_params if k in arguments
    }
    body = {spec.alias.get(k, k): arguments[k] for k in spec.body_props if k in arguments} or None

    try:
        response = httpx.request(
            spec.method,
            f"{api_base}{url}",
            params=params,
            json=body,
            headers=headers or None,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        return False, {"error": f"falha de transporte: {exc}"}

    try:
        payload = response.json()
    except ValueError:
        return False, {"error": f"resposta nao-JSON (HTTP {response.status_code})"}

    if response.status_code >= 400:
        return False, {"error": payload, "status": response.status_code}

    return True, payload
