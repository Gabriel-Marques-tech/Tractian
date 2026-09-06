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

**O agente entregue é o braço A**, por custo e estabilidade — um terço das
chamadas ao modelo e trajetória praticamente determinística. A diferença de
**qualidade** entre os braços não é sustentada pelos dados: fica dentro do
ruído. A seção de resultados detalha, incluindo o erro de execução que
comprometeu a comparação.

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

Ele imprime **13 ferramentas**, não 18: o padrão é `include_impact=False`, e as
cinco ações que mudam estado só são registradas quando pedidas. O agente as
recebe (`connect(..., include_impact=True)`); a verificação avulsa não, para não
oferecer ação de escrita a quem só quer conferir que o servidor sobe.

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

A bateria é resumível: rodar de novo com o mesmo `--out-dir` continua de onde
parou. Duas flags cobrem o que uma queda de ambiente deixa para trás:

```bash
# refaz as execucoes que terminaram em erro em vez de pula-las
api/.venv/bin/python -m agent.runner --arm B --out-dir runs/braco-B --retry-failed

# recomputa scores a partir dos traces, sem gastar chamada de modelo
api/.venv/bin/python -m agent.runner --out-dir runs/braco-A --rescore-only
```

Inspetor de traces. **A ordem importa**: o Vite copia `ui/public/` para
`ui/dist/` no momento do build, então exportar depois de buildar deixa a
interface sem dados.

```bash
api/.venv/bin/python -m agent.export      # 1. gera ui/public/data/runs.json
cd ui && npm install && npm run build     # 2. build, que carrega os dados junto
cd .. && make agent-env                   # 3. cria agent/.env (o up-agent exige)
make up-all                               # API em :8000, inspetor em :8001
```

`make agent-env` é exigido pelo `Makefile` da TRACTIAN antes de `up-agent`.
`agent/server.py` é servidor estático e não lê chave nenhuma, mas o guard
existe no Makefile do parceiro, que não é editado aqui.

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

**Nove de nove com custo zero.** Isso tira o custo inteiramente do *pontuar* e
deixa só no *rodar*, o que torna o experimento viável no hardware disponível.

### Por que o judge é determinístico

Os objetos 4 e 5 costumam pedir LLM-judge. O único juiz disponível aqui seria o
próprio `qwen2.5:1.5b` que produziu as respostas — um modelo julgando a si
mesmo, e um modelo pequeno é juiz fraco mesmo julgando outro. O número não se
defenderia numa apresentação.

Regra sobre o trace é auditável linha a linha, e mede exatamente o modo de
falha que as execuções exibem:

| Critério | Regra | Objeto |
|---|---|---|
| Ancoragem | valores citados na resposta que existem na evidência recebida | 4 |
| Alucinação | valores citados que não aparecem em evidência nenhuma | 4 |
| Reconhece a degradação | a resposta menciona os `mode` que de fato ocorreram | 5 |
| Cobre a pergunta raiz | termos de `root_question` presentes na resposta | 5 |

O chamado do cliente conta como fonte válida: repetir um valor que o cliente
informou não é inventar. A rubrica é versionada (`RUBRIC_VERSION`) e gravada em
cada nota, porque comparar notas de rubricas diferentes não é comparação.

**Limitação**: alucinação de *interpretação* escapa. Afirmar "baseline
estabelecido" quando ele está em `learning` é falso e passa, porque nenhum
valor foi inventado. Só valor citado e menção de `mode` são pegáveis por regra.

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

### O que foi medido

**Braço A: 85 execuções** — 17 casos × 5 repetições, seed `exp-2026-09`.

| Métrica | Braço A |
|---|---|
| Trajetória contra o gabarito | 0,09 ± 0,13 |
| Recall de ferramentas | 0,10 ± 0,15 |
| Precisão de ferramentas | 0,34 ± 0,47 |
| Instabilidade entre repetições | 0,004 |
| Chamadas ao modelo por execução | 1,9 |
| Segundos por execução | 33 |
| Ancoragem (objeto 4) | 3,29 ± 2,26 (n=66) |
| Respostas que citam dado | 66 / 85 |
| Alucinação por valor citado | 22% |
| Reconhece a degradação da API | 4,12 / 5 |
| Cobre a pergunta raiz | 0,94 / 5 |
| Ações exigidas não executadas | 35 |
| Ações executadas sem o caso pedir | 0 |

### A hipótese não foi respondida

Esta é a conclusão honesta, e ela é mais fraca do que este documento afirmava
numa versão anterior.

**A comparação entre braços está comprometida por um erro de execução.** A
bateria do braço B rodou sob a seed `exp` enquanto a do A rodou sob
`exp-2026-09` — o comando do braço B foi lançado sem `--config`, caindo num
default divergente. Como a API deriva a degradação de `sha256(seed|recurso|
categoria)`, **54% dos endpoints do gabarito resolvem para `mode` diferente
entre as duas seeds**. Os braços enfrentaram ambientes diferentes.

O relatório agora **recusa** comparar braços cuja configuração difira, nomeando
o campo. O braço B está sendo re-executado sob a seed correta; até que feche, a
comparação de qualidade não é reportável.

**E mesmo com a seed corrigida, as diferenças observadas não sobrevivem ao
teste.** Sobre os dados anteriores, teste pareado por caso (n = 17):

| Métrica | diferença A − B | t(16) | IC 95% |
|---|---|---|---|
| Trajetória | +0,031 | 0,91 | [−0,042; +0,104] |
| Recall | +0,035 | 0,99 | [−0,040; +0,111] |
| Precisão | +0,143 | 1,21 | [−0,107; +0,393] |

Em trajetória, **11 dos 17 casos empatam exatamente**. O intervalo de confiança
cruza zero em todas. Com 17 casos e este tamanho de efeito, o experimento não
tem poder estatístico para distinguir as arquiteturas em qualidade — e dizer o
contrário seria ler ruído como sinal.

### O que os dados sustentam

**O custo é a única diferença sólida.** O braço B faz 5,7 chamadas ao modelo
por execução contra 1,9 do A, e leva 62s contra 33s. Isso é determinado pela
arquitetura — seis papéis fazem seis chamadas — e independe da seed, do
ambiente e do tamanho da amostra.

**O braço A é praticamente determinístico**: instabilidade 0,004, com 15 dos 17
casos produzindo trajetória idêntica nas 5 repetições. Isso é propriedade útil
num agente de suporte: a mesma pergunta recebe a mesma investigação.

**Nenhum dos dois investiga o suficiente.** Trajetória de 0,09 sobre gabaritos
de 1 a 5 passos. E a cobertura da pergunta raiz é 0,94 de 5: em 44 das 85
execuções do braço A, a resposta não toca nenhum termo da pergunta que o caso
faz. O agente descreve o ativo em vez de explicar o evento.

**Quase um quarto do que o agente afirma não está na evidência.** 22% dos
valores citados não aparecem em nenhuma resposta de ferramenta nem no chamado
do cliente.

### O modo de falha, visto no inspetor

Trajetória de 0,09 é um número. O inspetor mostra a causa, no `TKT-CTX-01`:

```
1  GET /assets/asset_M101               conflito
2  GET /companies/comp_forja_br/assets  completo
3  GET /assets/asset_M101               conflito
4  GET /companies/comp_forja_br/assets  completo
...
```

Ao receber `mode=conflict`, o agente **entra em laço** entre dois endpoints em
vez de buscar a fonte que resolveria o conflito, e termina devolvendo o JSON
cru ao cliente. É o modo de falha mais frequente, e o que uma próxima iteração
deve atacar primeiro.

### A escolha do agente entregue

**O agente entregue à TRACTIAN é o braço A**, e o motivo é custo e
estabilidade, não superioridade de qualidade — que os dados não sustentam.

Duas ressalvas que o leitor precisa ter:

O braço A tem **zero ações executadas indevidamente**, mas isso é artefato de
**inação**: ele também executou **zero** ações de impacto corretas, omitindo as
35 que o gabarito exigia. Um agente que nunca age pontua perfeito nessa
métrica. Usá-la como critério de escolha seria seleção conveniente.

Os dois erram em direções opostas — o braço A não age quando deveria, o braço B
agiu quando não devia. **Nenhum dos dois atende ao critério.**

### Como estes números foram corrigidos

Uma revisão adversarial em cinco frentes encontrou defeitos que invalidavam
números publicados numa versão anterior deste documento. Registrados porque
mudam o quanto se deve confiar no resto:

- **Argumentos da chamada contavam como evidência.** Em `case_tkt_inv_06` o
  modelo fabricou um id, a API devolveu 404, e a ancoragem dava 5/5.
- **Silêncio pontuava como fabricação.** 60 dos 93 zeros em ancoragem eram
  respostas que simplesmente não citavam valor. Agora a nota é indefinida e a
  agregação declara o `n`.
- **A régua media a si mesma.** 109 das 154 "alucinações" do braço A eram
  numeradores de lista markdown; timestamps na evidência davam âncora grátis; e
  `S420` na resposta não casava com `asset_S420` na evidência.

Depois das correções, a ancoragem do braço A passou de 2,55 sobre 85 para 3,29
sobre os 66 que de fato citam dado, e a taxa de alucinação caiu de 45% para
22%. Mais da metade do erro medido era da régua, não do agente.

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

**17 casos não dão poder estatístico para comparar arquiteturas.** Com o
tamanho de efeito observado, o intervalo de confiança de 95% cruza zero em
todas as métricas de qualidade. O experimento distingue custo, não qualidade —
e aumentar repetições não resolve, porque a variância entre repetições já é
quase nula; seria preciso mais **casos**.

**A comparação entre braços foi executada com seeds diferentes.** Erro de
operação: a bateria do braço B foi lançada sem `--config`. O relatório agora
recusa comparar braços com configuração divergente, mas os números de
comparação deste documento aguardam a re-execução.

**O judge determinístico mede o que é verificável, não o que importa mais.**
Ancoragem por valor pega afirmação sobre dado não consultado. Não pega
alucinação de *interpretação*: dizer "baseline estabelecido" quando ele está em
`learning` é falso e passa, porque nenhum valor foi inventado.

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
  judge.py        objetos de análise 4 e 5, por regra sobre o trace
  runner.py       bateria resumível
  check_server.py verificação do servidor MCP, sem agente e sem modelo
  demo.py         um caso, com trajetória ao lado do gabarito
  smoke.py        portão de decisão
  report.py       agregação e tabelas
  export.py       JSON estático e tipos para o inspetor
  server.py       serve o inspetor em :8001
ui/               inspetor de traces (React + Vite)
tests/            suíte do projeto
docs/             spec, decisões e resultados
```

Material fornecido pela TRACTIAN (`api/`, `data/`, `eval/`, `agent-input/`,
`STUDENT-GUIDE.md`, `Makefile`) não é editado: é insumo do experimento, e mexer
em `eval/expected-paths.json` invalidaria toda a avaliação.
