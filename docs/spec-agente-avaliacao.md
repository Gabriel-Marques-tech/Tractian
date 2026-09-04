# Spec — Agente Industrial e Framework de Avaliação

**Projeto**: Engenharia e Avaliação de Agentes Industriais (TRACTIAN × Inteli)
**Data**: 2026-09-02
**Entrega**: 2026-09-08
**Status**: rascunho — dois pontos em aberto marcados como `[DECISÃO PENDENTE]`

---

## Problem Statement

Quando uma máquina monitorada pela TRACTIAN falha, quem abre o chamado é a pessoa que opera a planta, e a pergunta dela é sempre alguma variação de "por que isso aconteceu e por que ninguém me avisou". Responder exige juntar coisas espalhadas: cadastro e criticidade do ativo, análises anteriores e o que elas concluíram, qualidade e atualidade do sinal, se o modelo de diagnóstico cobre aquele tipo de máquina e em que estado de processamento ele está, e o que o procedimento interno manda fazer.

Hoje esse trabalho é humano e caro. O analista de suporte navega vários recursos, cruza evidências, e decide entre três desfechos: explicar ao cliente, investigar mais fundo, ou executar uma ação na plataforma.

Três coisas tornam a automação difícil:

1. **A informação chega degradada.** A plataforma nem sempre devolve resposta completa. Ela devolve resposta parcial, inconclusiva, conflitante entre fontes, ou simplesmente indisponível. Um agente que só sabe operar com dado limpo produz conclusão confiante sobre evidência que não existe.
2. **Algumas ações têm consequência real.** Reprocessar análise, pedir retreinamento de modelo, escalar caso e alterar configuração técnica do ativo mudam estado. Executar sem justificativa é pior que não executar.
3. **Não se sabe qual arquitetura de agente serve aqui.** Um agente ReAct único é simples e barato. Uma pipeline multi-agente com fan-out e revisão adversarial é cara e promete mais qualidade. Ninguém mediu a diferença sob degradação de API.

O problema deste projeto é o terceiro. Os dois primeiros são o ambiente onde ele se manifesta.

## Solution

Construir um **servidor MCP** que expõe a API industrial como ferramentas, e sobre ele **dois agentes** que consomem exatamente a mesma superfície, e então **medir a diferença entre eles** num experimento reprodutível.

- **Braço A — baseline**: agente ReAct único, com acesso às 18 ferramentas, laço de raciocínio-ação-observação, política de parada explícita.
- **Braço B — pipeline multi-agente**: orquestrador que distribui o trabalho entre papéis especializados (planejamento, execução de ferramentas com gate de segurança, organização de evidências, revisão adversarial, decisão final), com fan-out configurável em alguns papéis.

Ambos emitem o mesmo artefato: um **trace** estruturado de tudo que aconteceu — cada chamada de ferramenta, cada argumento, cada retorno com seu `mode` de degradação, cada decisão, e a resposta final.

Sobre os traces roda um **scorer** que compara o que o agente fez com o gabarito de trajetória que a TRACTIAN entregou (`eval/expected-paths.json`, 17 casos), produzindo métricas por caso e agregadas.

O entregável não é "um agente que funciona". É **a resposta a uma pergunta**: orquestração multi-agente com fan-out e revisão adversarial melhora a acurácia de ferramentas e o uso de evidências sob degradação de API, e a que custo?

## User Stories

### Pessoa usuária da plataforma (cliente da TRACTIAN)

1. Como operadora de planta, quero perguntar em linguagem natural por que meu ativo falhou sem aviso, para entender a causa sem precisar navegar a plataforma.
2. Como operadora de planta, quero que o agente me diga quando ele **não** conseguiu concluir, para não agir com base em resposta inventada.
3. Como operadora de planta, quero que o agente cite qual dado sustenta cada afirmação, para eu conseguir verificar por conta própria.
4. Como operadora de planta, quero que o agente peça informação adicional quando faltar contexto, em vez de chutar o ativo ao qual me refiro.
5. Como operadora de planta, quero que o agente escale para humano quando a evidência for insuficiente, para meu caso não morrer numa resposta vaga.
6. Como operadora de planta, quero que o agente explique um termo técnico quando eu perguntar, sem consultar dados que não são necessários para a pergunta.
7. Como operadora de planta, quero que o agente distinga "o sensor está offline" de "não há falha", para eu não interpretar ausência de alerta como ausência de problema.
8. Como operadora de planta, quero que o agente diga quando duas fontes discordam, em vez de escolher uma silenciosamente.

### Analista de suporte da TRACTIAN

9. Como analista de suporte, quero que o agente execute ações de plataforma somente com justificativa registrada, para que eu consiga auditar depois.
10. Como analista de suporte, quero que o agente nunca altere configuração técnica de ativo sem que a alteração seja o pedido explícito do caso, porque essa é a única ação que muda estado do ativo em si.
11. Como analista de suporte, quero receber os casos escalados com a investigação já feita anexada, para não recomeçar do zero.
12. Como analista de suporte, quero que o agente respeite as permissões do usuário que abriu o chamado, para não expor dados de outra empresa.

### Pesquisador/estudante (dono do experimento)

13. Como pesquisador, quero rodar os 17 casos oficiais contra qualquer braço com um comando, para comparar arquiteturas sem trabalho manual.
14. Como pesquisador, quero que cada execução grave um trace completo em disco, para poder analisar depois sem re-executar.
15. Como pesquisador, quero fixar a seed da API, para que a degradação seja idêntica entre braços e a comparação seja justa.
16. Como pesquisador, quero repetir o mesmo caso N vezes, para medir estabilidade entre execuções.
17. Como pesquisador, quero que o scorer compare a trajetória do agente com o gabarito, para pontuar escolha de função e acurácia de argumento sem julgamento subjetivo.
18. Como pesquisador, quero que o runner seja resumível por caso, para que uma sessão de Colab que caia às 11h50 não perca o batch inteiro.
19. Como pesquisador, quero trocar modelo e endereço do modelo por configuração, para rodar a mesma bateria no laptop e no Colab sem editar código.
20. Como pesquisador, quero um smoke test de poucos casos, para descobrir em minutos se o experimento tem sinal antes de comprometer horas de execução.
21. Como pesquisador, quero medir custo por caso em chamadas de modelo e tempo de parede, para reportar o preço da qualidade extra.
22. Como pesquisador, quero que o scorer separe erro de escolha de função de erro de argumento, porque as duas falhas têm causas diferentes.
23. Como pesquisador, quero contabilizar ações de impacto executadas indevidamente como categoria própria, porque um falso positivo aqui é mais grave que uma resposta ruim.
24. Como pesquisador, quero exportar os resultados agregados em tabela, para colar na documentação sem formatação manual.
25. Como pesquisador, quero que o desempenho seja quebrado por `mode` de retorno da API, para saber se o agente falha mais sob conflito ou sob indisponibilidade.
26. Como pesquisador, quero que o desempenho seja quebrado por categoria de caso (contextualizar, investigar, executar), porque as três exigem comportamentos diferentes.

### Avaliador acadêmico

27. Como avaliador, quero reproduzir os resultados a partir do repositório, para confirmar que os números vieram do código entregue.
28. Como avaliador, quero ver a hipótese declarada antes dos resultados, para julgar se o experimento a testa de fato.
29. Como avaliador, quero ver as limitações declaradas, incluindo as do modelo escolhido.

## Implementation Decisions

### Fronteira central: o trace é o contrato

A decisão mais importante da arquitetura: **agente e avaliador não se conhecem**. Eles se comunicam por um artefato de dados, o `Trace`.

```
run_case(caso, config) -> Trace          # metade agente
score(trace, expected_path) -> Scores    # metade avaliador
```

Consequências que justificam a escolha:

- O scorer é **função pura**, determinística, testável sem LLM nenhum.
- Traces podem ser produzidos no Colab e pontuados no laptop, porque são só arquivos.
- Trocar a arquitetura do agente não toca no avaliador.
- Um trace gravado é evidência permanente: reanalisar não custa nova execução.

O `Trace` registra, no mínimo: identificação do caso, config usada (modelo, versão, braço, seed), sequência ordenada de passos com nome da ferramenta, argumentos, resposta crua incluindo o `mode` da API, timestamps, contagem de chamadas ao modelo, resposta final e motivo de parada.

### Camada de ferramentas: servidor MCP

A integração entre agente e API industrial é um **servidor MCP**. O agente é cliente MCP; nenhum braço fala HTTP com a API diretamente.

Isso põe uma fronteira de processo entre agente e API, com três consequências que valem o custo do salto extra:

- **O gate de segurança mora no servidor, não no agente.** Uma ação de impacto sem justificativa é recusada na camada MCP, para qualquer cliente. Nenhum prompt, em nenhum braço, contorna. Segurança que depende do prompt não é segurança.
- **Os dois braços compartilham exatamente a mesma superfície de ferramentas.** Comparar arquiteturas exige que a única diferença seja a arquitetura; ferramenta idêntica por construção elimina uma variável de confusão.
- **O servidor é entregável por si.** A TRACTIAN recebe uma peça que qualquer cliente MCP consome, não código acoplado a este agente.

Detalhes:

- Schemas derivados do contrato OpenAPI servido pela própria API em `/openapi.json`, não escritos à mão a partir da documentação. Fonte única de verdade.
- 18 operações: **13 de leitura**, **5 de impacto**.
- As 5 de impacto (`PATCH /assets/{id}`, `POST /analyses/{id}/reprocess`, `POST /analyses/{id}/request-specialist`, `POST /models/{id}/request-retraining`, `POST /cases/{id}/escalate`) formam classe separada, com campo de justificativa obrigatório validado no servidor.
- Transporte stdio. O servidor sobe como subprocesso, o que funciona igual no laptop e dentro do notebook do Colab, sem porta exposta.
- A captura do trace acontece no **cliente**, envolvendo cada chamada MCP. O servidor permanece sem estado de experimento.
- `PATCH /assets/{id}` recebe tratamento mais restritivo que as outras quatro: as demais *solicitam* algo a um humano ou a um pipeline; essa altera diretamente o estado do ativo.
- Validação de entrada e saída com pydantic.
- O envelope da API é `{mode, notes, data}`. O `mode` **não é descartado** ao entregar ao modelo: a degradação é informação, e esconder isso do agente elimina o fenômeno que o experimento estuda.

### Determinismo e reprodutibilidade

- A API já é determinística: `resolve_mode` deriva o modo de `sha256(seed|resource|category)`, sem aleatoriedade. Verificado empiricamente — mesma seed devolve o mesmo modo.
- Seeds especiais: `complete` força retorno completo, `degraded` força parcial.
- Ativos de cenário fixo (ex.: `asset_G501`) têm overrides que vencem as seeds especiais. Isso é intencional e alinhado ao gabarito; não é defeito.
- Toda execução declara sua seed no trace. Braços diferentes rodam sob seeds idênticas.

### Orquestração

- **LangGraph** para o grafo de estados do braço B.
- Braço A é ReAct de nó único, deliberadamente simples — precisa ser um baseline honesto, não um espantalho.
- Papéis do braço B, após o corte do consultor de grafo: planejador, orquestrador de ferramentas com gate de segurança, organizador de evidências, revisor adversarial, decisor, sob um executor que roteia. **Seis papéis, não sete.**
- Fan-out configurável, aplicável ao orquestrador de ferramentas, ao organizador e ao revisor adversarial. Desligar o fan-out é um parâmetro, o que o torna um terceiro braço barato se houver tempo.
- Chamadas paralelas do fan-out usam `asyncio`. Não há fila de eventos: a API não expõe operação assíncrona com ciclo de status, e a latência real é do modelo, não da rede.

### Modelo

- `qwen2.5:1.5b` via Ollama para laço de desenvolvimento e smoke test. Medido em **17,1 tok/s** em CPU nesta máquina. Verificado que emite tool call válida com função e argumento corretos em caso simples.
- `qwen2.5:7b` via Ollama no Google Colab para a rodada oficial, se houver GPU.
- Fallback: `qwen2.5:1.5b` local em execução noturna.
- Acesso via endpoint compatível com OpenAI (`/v1`), o que mantém o código independente de provedor.
- Modelo é **infraestrutura, não variável do experimento**. A variável é a arquitetura.

### Execução no Colab

Os termos do Colab proíbem acesso remoto e processos longos em background alheios a computação interativa. Portanto a pilha inteira — API, agente, modelo, runner — roda **dentro do notebook**, em `localhost`. Não há túnel expondo o modelo para fora.

Isso impõe três requisitos, que coincidem com o critério de reprodutibilidade da rubrica:

1. Ponto de entrada Python headless. O notebook é um invólucro fino; `make` não é dependência de execução.
2. Runner resumível com checkpoint por caso, gravando trace incremental. Teto de 12 horas e desconexão por ociosidade tornam batch não-resumível uma aposta ruim.
3. Configuração externa. Trocar laptop por Colab é trocar arquivo de config.

### Métricas

Dos nove objetos de análise exigidos, **seis são determinísticos** e não custam chamada de modelo:

| # | Objeto | Método | Custo |
|---|---|---|---|
| 1 | Escolha de funções | conjunto de chamadas vs. gabarito | zero |
| 2 | Acurácia de argumentos | diferença de argumentos | zero |
| 3 | Trajetória | distância de edição contra `expected_path` | zero |
| 6 | Segurança | ação sem justificativa, ou fora de permissão | zero |
| 7 | Desempenho sob falha | taxa de sucesso por `mode` da API | zero |
| 8 | Estabilidade | variância entre repetições | zero |
| 9 | Ações de impacto | executou as corretas? justificou? | zero |
| 4 | Uso de evidências | resposta cita dado retornado | híbrido |
| 5 | Qualidade da resposta | LLM-judge | modelo |

O custo de modelo fica em **rodar** o agente, não em **pontuar**. Isso é o que torna o experimento viável sob restrição de hardware.

### Dados do experimento

- 17 casos oficiais em `agent-input/cases.json`, com gabarito correspondente em `eval/expected-paths.json`.
- Distribuição: 9 investigar, 5 executar, 3 contextualizar.
- Trajetórias de 1 a 5 passos, média 3,4, total 57 passos.
- 7 casos exigem ação de impacto; 7 passos de escrita no total.

### [DECISÃO PENDENTE] 1 — Qualidade máxima ou diferença mensurável

Declarado na conversa: "o foco é na melhor resposta por enquanto". Escolhido: o menor modelo disponível.

Há reconciliação defensável — modelo pequeno preserva margem para o efeito arquitetural aparecer, enquanto modelo grande satura e esconde a diferença. Mas isso é "otimizar para enxergar o contraste", não "otimizar para a melhor resposta". **A spec assume o primeiro.** Se a intenção for o segundo, o modelo passa a ser variável e a bateria muda.

### [DECISÃO PENDENTE] 2 — Arquitetura do avaliador

Declarado na conversa: "não sei quanto ao analisador dele". O agente foi especificado em detalhe; o avaliador não recebeu nenhuma decisão do autor.

**A spec assume**: runner + scorer determinístico + relatório tabular, sem interface de inspeção de traces e sem geração automática de casos adversariais. Ambos são caminhos legítimos e ambos são escopo maior.

## Testing Decisions

### O que é um bom teste aqui

Testa comportamento externo observável, não estrutura interna. Nenhum teste afirma que um prompt tem certo formato, que o grafo tem certo número de nós, ou que uma classe tem certo método. Testes falham quando o comportamento muda, não quando o código é reorganizado.

### Seams

A meta é o menor número possível de costuras. **Duas**, e a primeira é de longe a principal:

**Seam 1 — `score(trace, expected_path) -> Scores`.** Função pura. Recebe dados, devolve dados. Nenhum I/O, nenhuma rede, nenhum modelo. Ela concentra a maior parte da lógica de valor do projeto e é 100% testável com traces sintéticos escritos à mão. É a costura mais alta possível para a metade avaliadora.

Casos a cobrir: trajetória idêntica ao gabarito; trajetória correta com passos a mais; trajetória com passo faltando; ordem trocada; função certa com argumento errado; ação de impacto executada sem justificativa; ação de impacto correta executada; ação de impacto **não** executada quando o gabarito a exigia; trace vazio; trace que termina por limite de passos.

**Seam 2 — `run_case(caso, config) -> Trace`.** Testada com cliente de modelo dublê que devolve sequências de tool call roteirizadas. Prova que o laço monta argumentos, envia à API real, registra o trace e para pelo motivo certo — sem depender de um LLM real, portanto rápido e determinístico.

Casos a cobrir: caso que resolve em um passo; caso que exige encadeamento; retorno `unavailable` que força caminho alternativo; retorno `conflict`; modelo que pede ação de impacto sem justificativa (deve ser bloqueado pelo gate); limite de passos atingido.

**Seam 3 — o servidor MCP.** Fronteira de processo, testável por um cliente MCP de teste sem agente nenhum: lista as ferramentas, chama uma, confere a resposta. Ganha costura própria porque é peça entregável separada e porque é onde o gate de segurança é imposto — a garantia mais importante do sistema precisa de teste que não dependa de prompt.

Casos a cobrir: as 18 ferramentas aparecem na listagem; leitura devolve o envelope com `mode` intacto; ação de impacto sem justificativa é recusada; ação de impacto com justificativa passa; `PATCH /assets/{id}` sob a regra mais restrita; erro da API vira erro MCP bem formado em vez de exceção crua.

**Deliberadamente sem seam**: prompts individuais, papéis isolados do braço B, e o cliente HTTP interno ao servidor MCP. O cliente é gerado do OpenAPI e a API já traz **39 testes próprios, todos passando** — retestá-lo duplica cobertura sem ganho.

### Prior art

`api/tests/` do material da TRACTIAN é a referência de estilo: pytest, `TestClient` do FastAPI, asserções sobre resposta e não sobre implementação. Os testes novos seguem a mesma convenção e o mesmo runner.

### Testes de integração

Uma bateria marcada como lenta roda 3 casos ponta a ponta contra a API real e o modelo local. Não afirma qualidade de resposta — afirma que o sistema executa sem quebrar e produz trace bem formado. É o smoke test que precede qualquer batch grande.

## Out of Scope

- **Neo4j e GraphRAG.** Nenhum histórico de resoluções passadas existe nos dados entregues; consultar um corpus que teria de ser fabricado primeiro custa dias e não pontua em nenhum critério da rubrica. Vai para "possibilidades de evolução". Se sobrar tempo depois do experimento fechado, entra como extra.
- **Consultor de banco de grafo como papel do agente.** Cai junto com o item acima.
- **Fila de eventos.** A API não expõe operação assíncrona com ciclo de status. Concorrência de fan-out é resolvida com `asyncio`.
- **OpenRouter e qualquer modelo proprietário.** O free tier são 50 requisições por dia sem crédito comprado, insuficiente para um único caso da pipeline completa. Manter tudo em modelo aberto e execução local alinha com a referência de viabilidade do enunciado.
- **Interface de demonstração além do mínimo.** A UI em `:8001` prevista pelo Makefile fica para o fim, se houver tempo.
- **Ajuste fino de prompts para maximizar nota.** O experimento compara arquiteturas sob prompts comparáveis; otimizar um braço e não o outro invalida a comparação.

## Further Notes

**Achado no material entregue.** `api/app/prob.py` tem código inalcançável: dentro do ramo `if seed == "degraded":`, há um `return` após o `return Mode.PARTIAL`. Inofensivo em execução. Vale registrar na documentação — evidencia leitura da implementação, não só do Swagger.

**Contradição entre os documentos da TRACTIAN.** O PDF descreve duas trilhas escolhíveis. O `STUDENT-GUIDE.md` afirma que cada estudante realiza um único projeto, construindo *e* avaliando. Esta spec segue o guia, que é o documento mais recente e mais específico.

**`make deps` exige `uv`**, não declarado como pré-requisito no guia. Instalado nesta máquina.

**`make agent-env` está quebrado** no material entregue: copia `agent/.env.example`, arquivo que não veio no pacote.

**Risco principal do experimento.** Quatro fontes de variância empilhadas — fluxo variável decidido pelo orquestrador, fan-out, degradação da API e um modelo de 1,5B. Se a variância dentro de cada braço superar a diferença entre braços, a comparação não conclui nada. O smoke test de 3 casos × 3 repetições existe para detectar isso em minutos, antes de comprometer horas. Se o sinal não aparecer, a resposta é reduzir variância (fixar fluxo, desligar fan-out, aumentar repetições), não rodar mais.
