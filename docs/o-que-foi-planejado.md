# O que foi planejado, e por quem

Documento de prestação de contas. Separa o que **tu** definiu do que **eu** decidi no teu lugar,
com o motivo de cada decisão minha e o custo de reverter.

Companheiro da spec (`spec-agente-avaliacao.md`), que descreve o *quê*. Este descreve o *porquê* e a *autoria*.

---

## 1. O projeto em uma página

A TRACTIAN monitora máquinas industriais. Quando algo quebra, quem abre chamado é a pessoa que
opera a planta, e a pergunta é sempre variação de *"por que quebrou e por que ninguém me avisou"*.

Responder exige juntar coisa espalhada: cadastro e criticidade do ativo, análises anteriores,
qualidade e atualidade do sinal, cobertura e estado do modelo de diagnóstico, procedimento interno.
Hoje é trabalho humano.

O entregável tem **duas metades obrigatórias** — o `STUDENT-GUIDE.md` é explícito de que não são
trilhas escolhíveis:

1. **Um agente** que atende essas solicitações consultando a API industrial e decidindo entre
   orientar, investigar ou executar ação na plataforma.
2. **Uma avaliação sistemática** desse agente: qualidade, confiabilidade, falhas, limitações.

Duas coisas tornam o problema interessante em vez de um CRUD com LLM em cima:

**A informação chega degradada de propósito.** A API devolve `complete`, `partial`, `inconclusive`,
`conflict` ou `unavailable`, com distribuição fixa (60/15/10/8/7). Agente que só opera com dado
limpo produz conclusão confiante sobre evidência inexistente.

**Cinco operações mudam estado.** Reprocessar análise, pedir especialista, pedir retreinamento,
escalar caso, e alterar configuração técnica do ativo. Executar sem justificativa é pior que não executar.

**Prazo**: entrega 08/09/2026. Projeto individual.

---

## 2. O que tu especificou

Isto é teu, e sobreviveu inteiro:

- **Arquitetura multi-agente** com orquestrador distribuindo entre papéis especializados
- **Os papéis**: planejador que conhece os caminhos, orquestrador de tools com gate de segurança e
  avaliação de justificativa, organizador que decide o que fazer com as informações e como mesclar
  caminhos, revisor adversarial que assume persona de outras áreas, decisor que escolhe entre a
  resposta do organizador e a do revisor
- **Fan-out**: múltiplas instâncias de alguns papéis atacando caminhos diferentes — recomendado para
  orquestrador de tools, organizador e adversarial; não para os demais
- **Fluxo variável**, a critério do orquestrador
- **LangGraph** para orquestração, **pydantic** para validação
- **Conexão por MCP**
- **Modelo aberto local** via Ollama
- **Colab** para processamento pesado
- A dúvida que virou o projeto: *"não sei se é eficiente dessa maneira"*

---

## 3. O que eu decidi além de ti

Cada item tem motivo, custo e como reverter.

### 3.1 A hipótese: transformei tua dúvida no experimento

**Tu disse** "não sei se é a melhor pipeline nem a mais otimizada".
**Eu decidi** que essa frase deixa de ser dúvida a resolver antes de começar e vira a pergunta que o
projeto responde.

**Por quê**: a rubrica pede "clareza da hipótese e do experimento" e "qualidade da análise dos
resultados". Construir a pipeline e afirmar que é boa é asserção. Construir a pipeline **mais um
baseline**, rodar os dois sob condição idêntica e medir é experimento. E resolve o conflito de
tempo: em vez de duas entregas disputando 6 dias, vira uma entrega que satisfaz as duas metades.

**Custo**: construir um segundo agente que tu não pediu.
**Reverter**: cara. Reorganiza a spec inteira.

### 3.2 O baseline ReAct como entregável de primeira classe

**Eu decidi** que o braço A não é rascunho nem espantalho: ReAct competente, mesmas 18 ferramentas,
mesmo servidor MCP, mesma política de parada explícita.

**Por quê**: sem baseline não existe eixo de comparação e a metade de avaliação vira suíte de testes
genérica. E baseline fraco de propósito é fraude experimental que um avaliador atento identifica.

**Custo**: um agente inteiro a mais.
**Reverter**: mata o experimento.

### 3.3 O trace como fronteira entre as duas metades

**Eu decidi** que agente e avaliador não se conhecem. Conversam por um artefato de dados.

```
run_case(caso, config) -> Trace          # metade agente
score(trace, expected_path) -> Scores    # metade avaliador
```

**Por quê**: tu disse *"não sei quanto ao analisador dele"*. Esta é a resposta — o analisador não
precisa saber nada do agente além do rastro que ele deixa. Ganhos concretos: scorer vira função pura
testável sem LLM; Colab produz traces e laptop analisa, porque traces são arquivos; reanálise é
grátis, sem re-executar; mudar um braço não toca no avaliador.

**Custo**: disciplina de sempre serializar tudo.
**Reverter**: barato agora, caro depois de 12 tickets.

### 3.4 O gate de segurança dentro do servidor MCP, não do agente

**Tu disse** que o Agente 2 avalia justificativa e tem bloqueios de segurança para escrita.
**Eu decidi** que essa validação mora no **servidor MCP**, não no papel do agente.

**Por quê**: três razões, em ordem de peso.

Primeiro: segurança imposta por prompt não é segurança. Modelo de 1,5B contornando instrução é o
caso esperado, não a exceção. No servidor, a recusa é código.

Segundo: os dois braços precisam da mesma superfície de ferramentas para a comparação isolar a
arquitetura. Se o gate vive no braço B, ele vira uma segunda variável e o experimento perde a limpeza.

Terceiro: vira medição. "Quantas vezes o agente tentou ação de impacto e foi recusado" é uma
métrica do objeto de análise 6, e só existe se a recusa acontecer num lugar que registra.

O Agente 2 continua existindo e continua construindo justificativa — ele deixa de ser a *única*
linha de defesa.

**Custo**: nenhum relevante.
**Reverter**: barato.

### 3.5 Seis papéis, não sete

Cortei o consultor de banco de grafo. Ver 4.1.

### 3.6 Métricas majoritariamente determinísticas

**Eu decidi** que 6 dos 9 objetos de análise não custam chamada de modelo, comparando a trajetória
do agente contra `eval/expected-paths.json` — 17 gabaritos que a TRACTIAN entregou, com a sequência
exata de chamadas esperadas e o motivo de cada passo.

**Por quê**: descobri esse arquivo lendo o material. Ele muda o projeto. O custo de LLM sai do
*pontuar* e fica só no *rodar*, o que torna o experimento viável no teu hardware. E métrica
determinística é a que tu defende na apresentação sem depender de "confia no judge".

Só uso de evidências e qualidade da resposta usam judge.

**Custo**: nenhum.
**Reverter**: sem motivo.

### 3.7 Runner resumível e configuração externa

**Eu decidi** que o runner grava trace incremental com checkpoint por caso, e que modelo, endereço,
braço e seed vêm de config, não de código.

**Por quê**: Colab tem teto de 12h e derruba sessão ociosa. Batch não-resumível é aposta. E os dois
requisitos coincidem com o critério "reprodutibilidade" da rubrica — ganho de graça.

**Custo**: pequeno, se feito desde o começo.
**Reverter**: fica caro depois.

### 3.8 Smoke test como portão antes do batch

**Eu decidi** que 3 casos × 3 repetições rodam **antes** de qualquer bateria grande.

**Por quê**: teu desenho empilha quatro fontes de variância — fluxo variável decidido pelo
orquestrador, fan-out, degradação da API, e modelo de 1,5B. Se a variância dentro de cada braço
superar a diferença entre braços, 170 execuções não concluem nada. O smoke test descobre isso em
20 minutos em vez de na madrugada da véspera. Se não houver sinal, a resposta é **reduzir variância**
(fixar fluxo, desligar fan-out, aumentar repetições), não rodar mais.

**Custo**: 20 minutos.
**Reverter**: não reverte. É a apólice mais barata do projeto.

### 3.9 Fan-out como parâmetro, não como estrutura

**Eu decidi** que ligar e desligar fan-out é uma flag.

**Por quê**: tu queria fan-out em três papéis. Como flag, "com fan-out vs sem" vira um terceiro braço
de experimento praticamente de graça — mesma pipeline, um parâmetro.

**Custo**: nenhum, se desenhado assim desde o início.

### 3.10 Doze tickets com arestas de bloqueio, caminho crítico declarado

**Eu decidi** a decomposição e a ordem: `01 → 02 → 04 → 05 → 06` é o caminho crítico até o portão
de decisão. O braço B (03, 07, 08) espera.

**Por quê**: não adianta construir a pipeline cara antes de saber se o experimento distingue
alguma coisa.

**Custo**: nenhum.
**Reverter**: reordenar tickets é barato.

### 3.11 Escopo declarado fora

Ver seção 4.

---

## 4. O que eu cortei do teu plano

### 4.1 Neo4j, GraphRAG e o Agente 4

**Motivo**: teu Agente 4 consultaria "como outros problemas foram resolvidos". **Esse histórico não
existe.** A TRACTIAN entrega ativos, análises, sinais e conhecimento — não um corpus de resoluções
passadas. Tu teria que fabricar o histórico para depois consultar o histórico que fabricou. Dias de
trabalho alimentando base inventada, e nenhum critério da rubrica premia grafo.

Cortando o grafo, o Agente 4 cai junto — tu mesmo escreveu que ele "pode ser tratado como subagente
do 1".

**Status**: stretch. Tu pediu para tentar entregar se sobrar tempo. Vai para "possibilidades de
evolução" no README, que é seção obrigatória — cortar com justificativa escrita **pontua**.

### 4.2 Fila de eventos

**Motivo**: tua justificativa foi que algumas consultas demoram. Verdade, mas a demora é **latência
de modelo**, não da rede. Isso resolve com `asyncio.gather` nas chamadas paralelas do fan-out.
Concorrência não é fila. E a API não expõe operação assíncrona com ciclo de status que justificasse
uma.

*(Nota: na primeira vez que argumentei isso, citei a cláusula errada do enunciado. Ver 5.3.)*

### 4.3 OpenRouter

**Motivo**: free tier são 50 requisições por dia sem crédito comprado. A pipeline completa gasta
~22 por caso. Não cobre um caso. E manter tudo em modelo aberto local casa com a referência de
viabilidade do enunciado.

### 4.4 Ajuste fino de prompt para maximizar nota

**Motivo**: otimizar um braço e não o outro invalida a comparação. Os dois rodam sob prompts
comparáveis.

---

## 5. Onde eu errei nesta sessão

Registrado porque afeta o quanto tu deve confiar no resto sem checar.

**5.1 Reofereci OpenRouter depois de tu ter descartado.** Tu disse "vamos de Ollama". Uma pergunta
depois, montei uma opção que continha OpenRouter e tu aceitou pegando o espírito, não o item. No
mesmo texto eu avisava para não virar matriz de três modelos e botei três modelos na tabela. Tu pegou.

**5.2 Descartei o modelo de 1,5B como incapaz de tool-calling sem testar.** Testei depois: acertou
função e argumento em caso simples. Afirmação forte sem evidência.

**5.3 Matei a fila com o argumento errado.** Citei "sem ciclo adicional de status", que é sobre
ações assíncronas. Tua justificativa era consulta lenta. A conclusão se sustenta, o argumento não era
esse.

**5.4 Contei 4 ações de impacto, são 5.** Perdi o `PATCH /assets/{id}` lendo só os POSTs. É
justamente a mais destrutiva das cinco — as outras quatro solicitam algo, essa altera o ativo.

**5.5 Coloquei servidor MCP em Out of Scope.** Tu não tinha mencionado MCP ainda, mas eu descartei
sem perguntar, com a justificativa de que "tools nativas bastam". Corrigido.

**5.6 Chamei de bug um comportamento correto.** `asset_G501/rms` ignora `seed=complete`. Parecia
falha. É override de cenário fixo, e o gabarito **espera** exatamente esse retorno. Confirmei
testando em ativo sem override antes de reportar.

---

## 6. O que ainda é decisão tua

### 6.1 Qualidade máxima ou diferença mensurável

Tu disse *"o foco é na melhor resposta por enquanto, e depois otimizamos"*, e escolheu o menor modelo
disponível — o oposto.

Há reconciliação defensável: modelo pequeno preserva margem para o efeito arquitetural aparecer,
enquanto modelo grande satura e esconde a diferença. Mas isso é otimizar para **enxergar o
contraste**, não para a melhor resposta.

**A spec assume o segundo.** Se a intenção for a primeira, o modelo vira variável e a bateria muda.

### 6.2 Arquitetura do avaliador

Tu disse *"não sei quanto ao analisador dele"*. A fronteira do trace (3.3) responde metade — a
forma. A outra metade continua aberta: **runner + scorer + relatório tabular**, que é o que a spec
assume, ou algo maior como aplicação de inspeção de traces ou geração automática de casos
adversariais.

Os dois caminhos são legítimos. Os dois são escopo maior.

### 6.3 Peso entre as metades

Na primeira rodada recomendei **30/70 a favor da avaliação**. Tu respondeu "as duas" e nunca
endereçou o peso — e descreveu o agente em sete níveis de detalhe e o avaliador em nenhum. Esforço
declarado ≈ 90/10 na direção oposta à recomendação.

Tu depois reforçou que *"temos que entregar um agente para a TRACTIAN que responda problemas com as
consultas"*, o que empurra de volta para o agente. Legítimo: o agente **é** entregável, não só
instrumento.

Vale explicitar: a decomposição em 12 tickets é neutra quanto a esse peso — o caminho crítico entrega
um agente funcional (tickets 01, 02, 03) antes de qualquer análise. Mas a alocação das tuas últimas
48 horas depende dessa resposta, e ela ainda não foi dada.

---

## 7. Estado em 02/09/2026

```
✓ uv instalado, dependências da API instaladas
✓ API industrial no ar em :8000, 39 testes próprios passando
✓ Determinismo por seed verificado empiricamente
✓ 18 endpoints mapeados: 13 leitura, 5 impacto
✓ Gabarito analisado: 17 casos, 57 passos, 9 investigar / 5 executar / 3 contextualizar
✓ qwen2.5:1.5b medido: 17,1 tok/s em CPU, tool-calling funcional em caso simples
✓ MCP verificado no Python 3.14: mcp 1.29.1, fastmcp 3.4.7, langchain-mcp-adapters 0.3.2
✓ Repositório reestruturado, CLAUDE.md e docs/agents/ escritos
✓ Spec escrita
✓ 12 tickets desenhados com arestas de bloqueio

✗ Tickets publicados no GitHub
✗ Servidor MCP
✗ Baseline ReAct
✗ Scorer
```

**Próximo**: ticket 01 — servidor MCP expondo as 18 operações, com o gate de segurança nas 5 de
impacto, e o formato do `Trace` fixado.
