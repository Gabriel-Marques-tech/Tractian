# Agente Industrial e Framework de Avaliação — TRACTIAN × Inteli

Um agente que atende chamados de suporte industrial consultando a API da
TRACTIAN por MCP, e um experimento que mede se orquestração multi-agente vale
o que custa.

---

## 1. O problema

Quando uma máquina monitorada falha, quem abre o chamado é a pessoa que opera a
planta, e a pergunta é sempre variação de *"por que quebrou e por que ninguém me
avisou"*. Responder exige juntar coisa espalhada: cadastro e criticidade do
ativo, análises anteriores, qualidade e atualidade do sinal, cobertura e estado
do modelo de diagnóstico, procedimento interno.

Duas coisas tornam isso mais que um CRUD com LLM em cima:

**A informação chega degradada de propósito.** Toda leitura devolve HTTP 200 e
declara num campo `mode` o quanto o dado é confiável: `complete`, `partial`,
`inconclusive`, `conflict` ou `unavailable`, com distribuição fixa
(60/15/10/8/7). Um agente que só opera com dado limpo produz conclusão
confiante sobre evidência que não existe.

**Cinco operações mudam estado.** Reprocessar análise, pedir especialista, pedir
retreinamento, escalar caso e alterar configuração técnica do ativo. Executar
sem justificativa é pior que não executar.

## 2. Recorte

O `STUDENT-GUIDE.md` define um projeto único com duas metades obrigatórias:
construir o agente e avaliá-lo. Este repositório entrega as duas de uma vez, com
um recorte que as une em vez de dividir o tempo entre elas.

**A hipótese**: orquestração multi-agente com papéis especializados melhora a
acurácia de ferramentas e o uso de evidências sob degradação de API, ao custo de
mais chamadas ao modelo.

Testar isso exige **dois agentes** sobre a mesma superfície de ferramentas, o que
transforma "construir um agente" e "avaliar um agente" no mesmo trabalho.

- **Braço A** — agente ReAct de nó único. Baseline honesto, não espantalho:
  mesmas ferramentas, mesmo servidor MCP, mesma seed.
- **Braço B** — grafo de seis papéis: executor, planejador, orquestrador de
  ferramentas, organizador de evidências, revisor adversarial e decisor.

A variável manipulada é **a arquitetura**. Todo o resto — modelo, seed,
ferramentas, permissões — é idêntico, porque qualquer diferença viraria variável
de confusão.

## 3. Arquitetura

```
chamado do cliente
      │
      ├── Braço A: ReAct de nó único
      │
      └── Braço B: planejador → orquestrador ⟲ → organizador → adversarial → decisor
      │
      ▼
  cliente MCP  ──── captura o trace ────┐
      │                                 │
      ▼                                 │
 servidor MCP (stdio)                   │
   18 ferramentas do OpenAPI            │
   gate das 5 ações de impacto          │
      │                                 │
      ▼                                 ▼
 API industrial (FastAPI :8000)      Trace (JSONL)
   degrada por `mode`, seed fixa         │
                                         ▼
                                    scorer determinístico
                                    vs eval/expected-paths.json
                                         │
                                         ▼
                                    tabelas agregadas
```

### O trace é a fronteira

A decisão que carrega o resto: **agente e avaliador não se conhecem**. Conversam
por um artefato de dados.

```python
run_case(caso, config) -> Trace          # metade agente
score(trace, expected_path) -> Scores    # metade avaliador
```

Isso torna o scorer uma função pura, testável sem LLM; permite produzir traces
numa máquina e analisá-los em outra; e torna reanálise grátis, sem re-executar.

### O servidor MCP

Os schemas das 18 ferramentas são **gerados do contrato OpenAPI** servido pela
própria API. Escrevê-los à mão criaria uma segunda fonte de verdade que
divergiria na primeira mudança.

O gate das ações de impacto vive **no servidor**, não no agente:

- Segurança imposta por prompt não é segurança. Modelo pequeno ignorando
  instrução é o caso esperado.
- Os dois braços precisam da mesma superfície para a comparação isolar a
  arquitetura.
- A recusa só vira métrica se acontecer num lugar que a registra.

Justificativa é validada antes de sair para a rede; permissão é decidida pela
API, que devolve 403, e o servidor traduz em recusa estruturada. Replicar a
matriz de permissões seria uma segunda fonte de verdade.

A identidade (`x-user-id`) sai da configuração e é injetada pelo servidor,
**fora do schema da ferramenta** — expô-la deixaria o agente contornar permissão
escolhendo um usuário mais permissivo.

## 4. Instalação e execução

```bash
make setup                                             # venv + dados
uv pip install --python api/.venv/bin/python -r agent/requirements.txt
make up                                                # API industrial em :8000
ollama serve && ollama pull qwen2.5:1.5b               # modelo local
```

Verificar o servidor MCP sem agente e sem modelo:

```bash
api/.venv/bin/python -m agent.check_server
```

Um caso, com trajetória comparada ao gabarito:

```bash
api/.venv/bin/python -m agent.demo TKT-INV-05
```

Portão de decisão antes de qualquer bateria:

```bash
api/.venv/bin/python -m agent.smoke
```

Bateria e relatório:

```bash
api/.venv/bin/python -m agent.runner --config experiment.json --repetitions 5 --out-dir runs/braco-A
api/.venv/bin/python -m agent.runner --arm B --repetitions 5 --out-dir runs/braco-B
api/.venv/bin/python -m agent.report runs/braco-A runs/braco-B --out docs/resultados.md
```

Testes:

```bash
api/.venv/bin/python -m pytest        # suíte do projeto
cd api && .venv/bin/python -m pytest  # suíte da API fornecida
```

## 5. Modelos e configuração

| | |
|---|---|
| Modelo | `qwen2.5:1.5b`, quantização Q4_K_M, 1,5B parâmetros |
| Servidor | Ollama, protocolo nativo `/api/chat` |
| Contexto | 4096 tokens |
| Temperatura | 0, fixa |
| Teto de geração | 512 tokens |
| Hardware | Intel Core Ultra 5 235U, 15 GB RAM, **sem GPU** (`size_vram: 0`) |
| Throughput medido | 17,1 tokens/s em CPU |

Toda configuração que afeta o comportamento do modelo vive no `RunConfig`, que
vai para o trace. Um parâmetro lido do ambiente produziria execuções diferentes
com traces de config idêntica, e a comparação entre braços deixaria de ser
honesta.

### Por que o protocolo nativo e não o compatível com OpenAI

Medido nesta máquina, mesmo modelo e mesmas 3 ferramentas:

```
nativo /api/chat        -> tool_calls: SIM
compat /v1              -> tool_calls: NAO
compat /v1 + required   -> tool_calls: NAO (tool_choice ignorado)
```

A camada `/v1` do Ollama não emite `tool_calls` para este modelo. Como o
experimento mede escolha de ferramenta e acurácia de argumento, usar `/v1`
mediria o bug do transporte em vez do agente. `agent/llm.py` mantém os dois
backends; o formato OpenAI segue sendo a forma canônica interna.

## 6. Metodologia

### Reprodutibilidade

A API é determinística por seed: `resolve_mode` deriva o modo de
`sha256(seed|resource|category)`, sem aleatoriedade. Verificado empiricamente —
mesma seed devolve o mesmo modo. Os dois braços rodam sob seeds idênticas, então
enfrentam a mesma degradação.

### O que é medido, e a que custo

Seis dos nove objetos de análise são **determinísticos**, comparados contra os
17 gabaritos de `eval/expected-paths.json`:

| # | Objeto | Método | Custo |
|---|---|---|---|
| 1 | Escolha de funções | precisão, recall e F1 sobre endpoints | zero |
| 2 | Acurácia de argumentos | query e recurso errado, separados | zero |
| 3 | Trajetória | Damerau-Levenshtein normalizado | zero |
| 6 | Segurança | sem justificativa, recusas do gate | zero |
| 7 | Sob degradação | contagem por `mode` | zero |
| 8 | Estabilidade | desvio entre repetições | zero |
| 9 | Ações de impacto | corretas, omitidas, não pedidas | zero |
| 4 | Uso de evidências | LLM-judge | modelo |
| 5 | Qualidade da resposta | LLM-judge | modelo |

Isso tira o custo do *pontuar* e deixa só no *rodar*, o que torna o experimento
viável no hardware disponível.

### Decisões de medição que mudaram os números

**Query string é argumento, não rota.** Cinco dos 57 passos do gabarito carregam
query (`GET /knowledge/search?q=BPFO`). Comparação por string exata reprovaria o
agente acertando. Misturar as duas contaria o mesmo acerto duas vezes e faria uma
busca com termo errado parecer endpoint errado — diagnósticos diferentes.

**Damerau, não Levenshtein.** Com Levenshtein puro, visitar os endpoints certos
na ordem errada e visitar os errados pontuavam igual: zero. Transposição custa 1,
e a métrica volta a separar "investigou na ordem errada" de "investigou o lugar
errado".

**Acurácia de argumento é `None`, não 1.0, quando não há o que acertar.** Doze
dos dezessete casos não têm query no gabarito; devolver 1.0 ali inflaria a média
com acertos que ninguém teve.

**`missing` não deduplica.** O gabarito de `TKT-EXE-14` relê o ativo depois do
`PATCH` para confirmar a alteração. Colapsar as duas leituras esconderia metade
da omissão.

### O portão antes da bateria

O desenho empilha quatro fontes de variância: fluxo variável, fan-out,
degradação da API e um modelo de 1,5B. Um smoke test de 3 casos × 3 repetições
roda antes de qualquer bateria e responde se há sinal a medir. Ele checa três
coisas — efeito de piso, variância dentro do caso, e **profundidade de
investigação** avaliada por caso.

A terceira existe porque as duas primeiras não pegam o defeito mais comum: as
repetições podem ser perfeitamente estáveis e a média estar acima do chão, com o
agente ainda assim desistindo no primeiro passo.

## 7. Resultados

> Bateria em execução. Preenchido a partir de `docs/resultados.md`, gerado por
> `python -m agent.report`.

## 8. Limitações

**O modelo é o gargalo, e é pequeno de propósito.** `qwen2.5:1.5b` em CPU sem
GPU. Um modelo maior provavelmente satura os casos e esconde o efeito da
arquitetura; um modelo deste tamanho preserva margem para a diferença aparecer.
A contrapartida é que parte dos erros observados é do modelo, não do desenho.

**Achados que são do modelo, não do agente:**

- Acima de ~2000 tokens de prompt, ele abandona a emissão estruturada de
  `tool_calls` e escreve a chamada em prosa. Por isso os prompts de papel são
  curtos, e por isso existe um resgate no cliente — cuja taxa é reportada.
- Sem teto de geração, entrada anômala o faz correr solto. `TKT-CTX-01`, cuja
  mensagem mistura português e caracteres chineses (`orientação de 间隙 e
  torque`) no material fornecido, gerou por 901 segundos até estourar o timeout.

**Permissão negada só é detectável porque o gate a traduz.** O `ToolCall` não
guarda status HTTP; se a recusa acontecesse só na API, casar string de erro seria
frágil.

**O LLM-judge (objetos 4 e 5) não roda na bateria oficial** pelo custo em CPU. As
outras sete métricas não dependem dele.

**Um smoke test de 3 casos não substitui os 17.** Ele existe para barrar bateria
inútil, não para concluir.

## 9. Possibilidades de evolução

**Neo4j e GraphRAG.** Cortados com justificativa: não existe corpus de resoluções
passadas nos dados entregues. Consultar um histórico que precisaria ser
fabricado primeiro custaria dias sem responder a hipótese. Com dados reais de
atendimento, o consultor de grafo volta a fazer sentido.

**Fan-out configurável.** A pipeline já isola os papéis; instanciar vários do
mesmo papel e mesclar as saídas é parâmetro, não reestruturação. Vira um terceiro
braço quase de graça.

**Modelo maior via Colab.** A pilha inteira roda dentro do notebook — os termos
proíbem usar o runtime como servidor para fora, então nada de túnel. Com GPU,
`qwen2.5:7b` muda a ordem de grandeza do throughput.

**Inspetor de traces.** Interface para navegar a trajetória lado a lado com o
gabarito. Os traces já são JSONL estático, então não precisa de backend nem de
streaming.

**Casos adversariais gerados.** O revisor adversarial do braço B e o gerador de
casos adversariais do framework são o mesmo componente usado nas duas pontas.

## 10. Estrutura

```
agent/
  mcp_server/     servidor MCP, 18 ferramentas do OpenAPI, gate de impacto
  toolgen.py      geração das ferramentas a partir do contrato
  mcp_client.py   cliente, e onde o trace é capturado
  llm.py          cliente de modelo, dois backends, resgate de texto
  trace.py        o contrato entre as duas metades
  react.py        braço A
  graph.py        braço B, seis papéis em LangGraph
  scorer.py       pontuação determinística contra o gabarito
  runner.py       bateria resumível
  smoke.py        portão de decisão
  report.py       agregação e tabelas
tests/            suíte do projeto
docs/             spec, decisões e resultados
```

Material fornecido pela TRACTIAN (`api/`, `data/`, `eval/`, `agent-input/`,
`STUDENT-GUIDE.md`, `Makefile`) não é editado: é insumo do experimento, e mexer
em `eval/expected-paths.json` invalidaria toda a avaliação.
