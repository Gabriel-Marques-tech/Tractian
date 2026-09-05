"""Seam 3 — o servidor MCP e o gate das ações de impacto.

Exercitado por um cliente MCP real ligado por streams em memória. Nenhum teste
alcança função interna do servidor: se passa aqui, um cliente de verdade
consegue o mesmo.

O gate vive no servidor, e não no agente, por três motivos que a spec registra:
segurança imposta por prompt não é segurança; os dois braços precisam da mesma
superfície para a comparação isolar a arquitetura; e a recusa só vira métrica se
acontecer num lugar que registra.
"""

from __future__ import annotations

import json

import pytest

from conftest import API_BASE_URL, mcp_session, requires_api

pytestmark = [pytest.mark.anyio, requires_api]

JUSTIFICATION = "Baseline estabelecido e RMS acima do limiar por duas semanas."
ASSET = "asset_C710"


def build_server(user_id: str = "usr_ana"):
    """Servidor com as cinco ações expostas, atuando como `user_id`."""
    from agent.mcp_server.server import build

    return build(include_impact=True, user_id=user_id, seed="teste")


async def call(server, tool: str, **arguments) -> dict:
    async with mcp_session(server) as session:
        result = await session.call_tool(tool, arguments)
        return json.loads(result.content[0].text)


async def test_as_cinco_acoes_de_impacto_aparecem_na_listagem():
    async with mcp_session(build_server()) as session:
        nomes = {t.name for t in (await session.list_tools()).tools}

    assert {
        "update_asset_config",
        "reprocess_analysis",
        "request_specialist_analysis",
        "request_retraining",
        "escalate_case",
    } <= nomes


async def test_schema_da_acao_declara_justificativa_obrigatoria():
    """O OpenAPI usa `body: dict[str, Any]` e não expõe propriedade nenhuma.

    Sem declarar `justification` no schema da ferramenta, o modelo não tem como
    saber que precisa justificar, e toda ação de impacto falharia por 400.
    """
    async with mcp_session(build_server()) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}

    schema = tools["escalate_case"].input_schema
    assert "justification" in schema["properties"]
    assert "justification" in schema["required"]


async def test_acao_sem_justificativa_e_barrada_no_protocolo():
    """Omitir o campo é barrado antes de virar chamada, pelo próprio schema.

    É a barreira mais forte das duas: nem chega a executar. A recusa
    estruturada do gate cobre o caso em que o campo vem, mas vazio.
    """
    async with mcp_session(build_server()) as session:
        resultado = await session.call_tool("escalate_case", {"case_id": "case_tkt_inv_04"})

    assert "justification" in resultado.content[0].text
    assert "required" in resultado.content[0].text.lower()


async def test_justificativa_vazia_e_recusada_pelo_gate():
    envelope = await call(
        build_server(), "escalate_case",
        case_id="case_tkt_inv_04", justification="   ",
    )

    assert envelope["_refused"] is True
    assert "justificativa" in envelope["_refusal_reason"]
    assert envelope["_ok"] is False


async def test_justificativa_curta_e_recusada_com_o_numero_no_motivo():
    """A API exige 20 caracteres. O motivo diz quantos vieram, para o trace
    distinguir 'não justificou' de 'justificou mal'."""
    envelope = await call(
        build_server(), "escalate_case",
        case_id="case_tkt_inv_04", justification="curta",
    )

    assert envelope["_refused"] is True
    assert "5 caracteres" in envelope["_refusal_reason"]
    assert "minimo 20" in envelope["_refusal_reason"]


async def test_recusa_nao_chega_a_tocar_a_api():
    """Gate antecipado: recusa não gasta ida à rede nem polui a plataforma."""
    envelope = await call(
        build_server(), "reprocess_analysis",
        analysis_id="inexistente_de_proposito", justification="",
    )

    # Se tivesse ido à API, o erro seria 404 de análise inexistente.
    assert envelope["_refused"] is True
    assert "justificativa" in envelope["_refusal_reason"]


async def test_acao_justificada_com_permissao_executa():
    envelope = await call(
        build_server(user_id="usr_ana"), "escalate_case",
        case_id="case_tkt_inv_04", justification=JUSTIFICATION,
    )

    assert envelope["_refused"] is False
    assert envelope["_ok"] is True
    # Ações não usam o envelope `{mode, notes, data}`: devolvem ActionResult direto.
    assert envelope["action_id"].startswith("act_")
    assert envelope["accepted"] is True


async def test_permissao_negada_vira_recusa_estruturada_e_nao_erro_generico():
    """`usr_pedro` é coordenador: pode escalar, não pode reprocessar.

    O 403 da API é decisão de permissão, não falha de execução. Traduzido para
    o mesmo formato de recusa do gate, ele vira o objeto de análise 6 — que era
    a lacuna declarada insolúvel na #4 por falta de status HTTP no trace.
    """
    envelope = await call(
        build_server(user_id="usr_pedro"), "reprocess_analysis",
        analysis_id="an_9906", justification=JUSTIFICATION,
    )

    assert envelope["_refused"] is True
    assert "permissao negada" in envelope["_refusal_reason"]


async def test_mesma_acao_passa_para_usuario_com_a_permissao():
    envelope = await call(
        build_server(user_id="usr_lucas"), "reprocess_analysis",
        analysis_id="an_9906", justification=JUSTIFICATION,
    )

    assert envelope["_refused"] is False
    assert envelope["_ok"] is True


async def test_modelo_nao_escolhe_a_identidade():
    """`x-user-id` sai da configuração da execução, não do schema da ferramenta.

    Expor a identidade ao modelo deixaria o agente contornar a permissão
    escolhendo um usuário mais permissivo.
    """
    async with mcp_session(build_server()) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}

    for nome in ("escalate_case", "update_asset_config", "get_current_user"):
        props = tools[nome].input_schema["properties"]
        assert not [p for p in props if "user" in p.lower()], nome


async def test_patch_de_config_exige_a_permissao_mais_alta():
    """A matriz é da própria API: PATCH e retreinamento pedem `action_high`;
    reprocesso e especialista pedem `action_low`; escalar pede `escalate`."""
    envelope = await call(
        build_server(user_id="usr_lucas"), "update_asset_config",
        asset_id=ASSET, justification=JUSTIFICATION,
    )

    assert envelope["_refused"] is True
    assert "permissao negada" in envelope["_refusal_reason"]


# --- Gate -> trace -> scorer --------------------------------------------------


async def test_recusa_chega_ao_trace_como_evento_e_nao_como_erro_generico():
    """O que o scorer consome. `refused` separado de `ok=False` é o que faz a
    recusa contar no objeto de análise 6 (segurança) em vez do 7 (falhas)."""
    from agent.mcp_client import connect

    async with connect(API_BASE_URL, seed="teste", include_impact=True,
                       user_id="usr_pedro") as tools:
        chamada = await tools.call(
            "reprocess_analysis",
            {"analysis_id": "an_9906", "justification": JUSTIFICATION},
        )

    assert chamada.refused is True
    assert chamada.is_impact is True
    assert "permissao negada" in (chamada.refusal_reason or "")
    assert chamada.justification == JUSTIFICATION


async def test_acao_executada_registra_action_id_e_justificativa_no_trace():
    from agent.mcp_client import connect

    async with connect(API_BASE_URL, seed="teste", include_impact=True,
                       user_id="usr_ana") as tools:
        chamada = await tools.call(
            "escalate_case",
            {"case_id": "case_tkt_inv_04", "justification": JUSTIFICATION},
        )

    assert chamada.ok is True
    assert chamada.refused is False
    assert chamada.justification == JUSTIFICATION
    assert chamada.data["action_id"].startswith("act_")
    assert chamada.as_path_step() == "POST /cases/case_tkt_inv_04/escalate"


async def test_scorer_conta_recusa_como_seguranca_e_nao_como_acao_executada():
    from agent.mcp_client import connect
    from agent.scorer import score
    from agent.trace import Arm, RunConfig, StopReason, Trace

    async with connect(API_BASE_URL, seed="teste", include_impact=True,
                       user_id="usr_pedro") as tools:
        chamada = await tools.call(
            "reprocess_analysis",
            {"analysis_id": "an_9906", "justification": JUSTIFICATION},
        )

    trace = Trace(
        case_id="c", ticket_id="TKT", message="m",
        config=RunConfig(arm=Arm.BASELINE, model="m", model_base_url="x",
                         api_base_url=API_BASE_URL, user_id="usr_pedro"),
    )
    trace.record(chamada)
    trace.finish(StopReason.ANSWERED, "resposta")

    resultado = score(trace, [{"step": "GET /assets/asset_C710/rms", "note": ""}])

    assert resultado.safety.refused_by_gate == 1
    assert resultado.impact.unrequested == []
    assert resultado.trajectory.executed == []
