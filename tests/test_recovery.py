"""Resgate de chamada emitida como texto.

`qwen2.5:1.5b` com 18 ferramentas escreve a chamada em prosa em vez de emitir
`tool_calls` estruturada. O conteúdo está certo — para TKT-INV-05 ele escolhe
`get_rms`, o primeiro passo do gabarito — e o que falha é o protocolo.

Sem o resgate, o experimento mediria a formatação do modelo em vez do
raciocínio do agente, e os dois braços ficariam em zero.

O resgate não inventa nada: só executa a chamada que o modelo já decidiu, com
a ferramenta e os argumentos que ele mesmo escolheu. Cada resgate fica marcado
no trace, então a taxa é reportável em vez de escondida.
"""

from __future__ import annotations

from agent.llm import recover_tool_calls

TOOLS = ["get_rms", "get_asset", "escalate_case"]


def test_json_puro_vira_chamada():
    pedidos = recover_tool_calls(
        '{"name": "get_rms", "arguments": {"asset_id": "asset_C710"}}', TOOLS
    )

    assert len(pedidos) == 1
    assert pedidos[0].name == "get_rms"
    assert pedidos[0].arguments == {"asset_id": "asset_C710"}
    assert pedidos[0].recovered is True


def test_json_embutido_em_prosa_e_encontrado():
    texto = (
        "Vou verificar o RMS do ativo.\n"
        '{"name": "get_rms", "arguments": {"asset_id": "asset_C710"}}\n'
        "Depois analiso."
    )

    pedidos = recover_tool_calls(texto, TOOLS)

    assert [p.name for p in pedidos] == ["get_rms"]


def test_json_em_bloco_de_codigo_e_encontrado():
    texto = '```json\n{"name": "get_asset", "arguments": {"asset_id": "asset_G501"}}\n```'

    assert [p.name for p in recover_tool_calls(texto, TOOLS)] == ["get_asset"]


def test_argumentos_nulos_sao_descartados():
    """O modelo preenche opcionais com null; o servidor não deve recebê-los."""
    pedidos = recover_tool_calls(
        '{"name": "get_rms", "arguments": {"asset_id": "a", "seed": null}}', TOOLS
    )

    assert pedidos[0].arguments == {"asset_id": "a"}


def test_ferramenta_desconhecida_nao_e_resgatada():
    """Só nomes que existem. Senão qualquer JSON em prosa viraria chamada."""
    assert recover_tool_calls(
        '{"name": "ferramenta_inventada", "arguments": {}}', TOOLS
    ) == []


def test_json_que_nao_e_chamada_e_ignorado():
    assert recover_tool_calls('{"resultado": "tudo certo", "rms": 4.2}', TOOLS) == []


def test_resposta_em_prosa_normal_nao_produz_chamada():
    texto = "O compressor esta com RMS acima do limiar ha duas semanas."

    assert recover_tool_calls(texto, TOOLS) == []


def test_texto_vazio_nao_quebra():
    assert recover_tool_calls("", TOOLS) == []
    assert recover_tool_calls(None, TOOLS) == []


def test_varias_chamadas_no_mesmo_texto():
    texto = (
        '{"name": "get_asset", "arguments": {"asset_id": "a"}} e depois '
        '{"name": "get_rms", "arguments": {"asset_id": "a"}}'
    )

    assert [p.name for p in recover_tool_calls(texto, TOOLS)] == ["get_asset", "get_rms"]
