# Engenharia e Avaliação de Agentes Industriais

Parceiro: TRACTIAN
Instituição: Inteli
Formato: projeto individual
Duração estimada: 1 mês

## 1. Contextualização do problema

A TRACTIAN apoia indústrias no monitoramento da condição de máquinas e na gestão da manutenção. Uma solicitação de suporte pode exigir dados do ativo, análises anteriores, qualidade dos sinais, cobertura dos modelos e ações dentro da plataforma.

Agentes de IA podem organizar essa investigação. O modelo recebe uma solicitação, consulta recursos especializados, interpreta os retornos e decide o próximo passo. Esse fluxo exige integrações bem construídas e critérios claros para orientar, agir ou escalar.

Estudos como ReAct, Toolformer e TAU-bench evidenciam o potencial de agentes com ferramentas e os desafios de confiabilidade, uso consistente de APIs e execução de políticas em múltiplas interações.

O projeto oferece um ambiente controlado para explorar engenharia e avaliação de agentes. Cada estudante realizará um único projeto — construir um agente e avaliá-lo — sobre uma API industrial simplificada, com dados fictícios e cenários inspirados em situações de suporte.

## 2. Objetivo do projeto

Desenvolver um agente de IA que se conecta à API industrial e que é capaz de interpretar solicitações, usar ferramentas para investigar dados do cliente e decidir entre orientar, agir ou escalar — e, em seguida, avaliar sistematicamente a qualidade e a confiabilidade desse agente.

Em termos práticos, o projeto unifica duas atividades:

- **Construção de agente:** criar a camada de integração — tools, servidor MCP ou equivalente — e o comportamento do agente.
- **Avaliação do agente:** medir a qualidade do que foi construído, identificando pontos fortes, falhas e limitações.

A documentação deve registrar as duas dimensões: a arquitetura do agente e a metodologia da avaliação.

## 3. Pergunta norteadora

Como construir e avaliar agentes de IA capazes de usar sistemas industriais com precisão, interpretar evidências e executar ações adequadas ao contexto?

## 4. Contexto de uso

A solução deve atender solicitações do cliente de três formas:

- **Contextualizar:** acessar conhecimento e explicar ao usuário de forma responsável;
- **Investigar:** usar ferramentas para estudar de forma especialista as máquinas do cliente, a fim de recomendar ações e explicar eventos;
- **Executar:** usar ferramentas que produzem impacto na solução para o cliente.

As ações podem incluir:

- solicitar informações adicionais (Contextualizar);
- consultar ativos, análises e dados técnicos (Investigar);
- recomendar próximos passos (Investigar);
- executar ações justificadas na plataforma (Executar);
- encaminhar o caso para análise humana (Executar).

Os dados técnicos estão em formatos didáticos e simplificados. O desafio está na integração, no comportamento do agente e na análise dos resultados.

## 5. Recursos fornecidos

A TRACTIAN disponibiliza uma API funcional com contrato Swagger e dados sintéticos gerados a partir de casos reais anonimizados. Os casos internos serviram apenas como inspiração para criar empresas, ativos, análises e situações simuladas. **O material entregue não utiliza dados pessoais, formatos internos ou informações identificáveis de clientes**.

A API representa recursos de uma plataforma industrial. Categorias e exemplos:

| Categoria | Exemplos de recursos e operações |
| :--- | :--- |
| Contexto | empresa fictícia, perfil da pessoa usuária, permissões e ativos relacionados |
| Ativos | cadastro, criticidade, hierarquia e configuração técnica |
| Análises | resultados anteriores, evidências, confiança e limitações |
| Dados técnicos | disponibilidade, qualidade, atualidade, espectros e sinais simplificados |
| Modelos | versão, cobertura, requisitos e estado de processamento |
| Conhecimento | procedimentos, glossário e orientações de suporte |
| Ações | solicitar análise especializada, reprocessar análise, solicitar retreinamento e alterar configurações técnicas |

A lista final de endpoints e parâmetros está no contrato da API (`docs/api-contract.openapi.yaml`).

### 5.1 Estrutura do material entregue

O repositório contém a API industrial implementada e o material de suporte. Os dados são sintéticos: 8 empresas, 26 ativos, 24 análises, 17 chamados e 16 cenários.

| Recurso | Local | Descrição |
| :--- | :--- | :--- |
| Guia do estudante | `STUDENT-GUIDE.md` | Contextualização do problema e da entrega (este documento). |
| Contrato da API | `docs/api-contract.openapi.yaml` | OpenAPI 3.1 com 18 endpoints nas sete categorias. |
| Chamados | `docs/support-tickets.md` | Dúvidas de clientes e do time de suporte que definem o espaço do problema. |
| Cenários de teste | `docs/test-scenarios.md` | 16 cenários no estilo TAU-bench: objetivo, política, trajetória e métricas. |
| Schema dos dados | `docs/data-schema.md` | Tabelas parquet e controle do comportamento probabilístico. |
| Implementação da API | `api/` | Aplicação FastAPI que serve o contrato, com Swagger UI em `/docs`. |
| Dados sintéticos | `data/` | Arquivos parquet que populam a API, além de `seed.json`. |
| Input do agente | `agent-input/` | Casos com mensagem e contexto; o que o agente deve ver. |
| Gabarito | `eval/` | Material de avaliação do agente, usado após a execução. |

### 5.2 Comportamento da API

Os endpoints de consulta poderão apresentar variações probabilísticas:

- retorno completo;
- informação parcial;
- resultado inconclusivo;
- conflito entre fontes;
- indisponibilidade temporária.

A variação é controlada pelo parâmetro `seed`, o que permite tornar uma execução determinística para fins de reprodutibilidade. Omitir o `seed` faz a API amostrar o comportamento por uma distribuição fixa.

As ações de maior impacto exigem parâmetros válidos e justificativa adequada. Uma chamada aceita representa a execução da ação e retorna sucesso, sem ciclo adicional de status. O contexto da pessoa usuária (header `x-user-id`) define o perfil e as permissões; nem toda ação pode ser executada por qualquer perfil.

## 6. Domínio técnico

Para interpretar os retornos da API, estes conceitos são necessários:

- **Baseline:** estado normal aprendido do próprio ativo a partir de histórico sadío. Ciclo de vida: `learning` (dados insuficientes), `established` (utilizável) e `invalidated` (após manutenção ou mudança de configuração; exige reaprendizado).
- **Limiar de alarme de RMS:** derivado do baseline (referência mais tolerância), não de norma ISO nem de tabela fixa por classe de máquina. Cada ativo tem o seu.
- **Modos de detecção de falha:**
  - `baseline`: detecção por desvio em relação ao baseline (desbalanceamento, desalinhamento, falha de rolamento, falha elétrica). Exige baseline `established`.
  - `symptom`: detecção sintomática (lubrificação). A presença do sintoma já indica a falha e independe de baseline; pode ser detectada mesmo com baseline em `learning`.
- **Espectro (FFT):** revela falhas por frequência característica (1× desbalanceamento, 2x desalinhamento, BPFO/BPFI/BSF/FTF rolamentos, 2x frequência de linha elétrica para falha elétrica).
- **Análise (insight):** diagnóstico automático do modelo, com tipo, severidade, confiança, evidência, limitações e modo de detecção.
- **Qualidade e frescor dos dados:** completude, relação sinal-ruído e atualidade. Afetam a capacidade do modelo de inferir e a confiabilidade do baseline. Compare sempre com os requisitos do modelo.
- **Decisão do agente:** orientar (explicar, sem alterar nada), agir (executar ação justificada) ou escalar (encaminhar para análise humana quando o caso extrapola o atendimento remoto).

## 7. Solução a ser entregue

O projeto único contempla duas partes relacionadas e interdependentes:

### Parte 1 — agente de suporte

Um agente capaz de interpretar solicitações, consultar a API e conduzir ações adequadas. São aceitas tools, servidor MCP ou abordagem equivalente. Pontos relevantes a considerar durante a construção:

- interpretação dos contratos HTTP;
- definição de tools e schemas;
- seleção de funções;
- construção dos argumentos;
- planejamento e política de parada;
- tratamento de retornos incompletos e falhas;
- fundamentação das respostas;
- memória e contexto entre interações;
- decisão entre orientar, agir ou escalar;
- rastreabilidade da execução.

O agente pode operar em atendimento direto, como copiloto ou em fluxos autônomos com escopo definido. Não há agente pré-pronto na entrega: o estudante parte da API e do material de suporte e constrói sua própria solução.

### Parte 2 — avaliação do agente

Uma metodologia — implementada como código, processo ou aplicação — para investigar a qualidade e a confiabilidade do agente construído. O formato permanece aberto. Exemplos:

- suíte de testes contra os cenários;
- biblioteca de métricas;
- runner de cenários com captura de trace;
- aplicação para inspeção de traces;
- geração de casos adversariais;
- avaliação de robustez e consistência;
- processo de captura, anonimização e reprodução de execuções.

Objetos de análise:

- escolha das funções;
- acurácia dos argumentos;
- trajetória de execução;
- uso das evidências;
- qualidade da resposta;
- segurança;
- desempenho diante de falhas;
- estabilidade entre execuções;
- comportamento em ações de maior impacto.

## 8. Metodologia experimental

O projeto deve seguir um método explícito, nos moldes abaixo. Variações são bem-vindas quando justificadas.

1. **Hipótese** — formular uma proposição testável sobre a arquitetura ou o comportamento do agente (ex.: "inspecionar o estado do baseline antes de confiar num insight reduz falsos positivos"). A hipótese pode tratar do agente em si ou de como ele deve ser avaliado.
2. **Método** — justificar a abordagem escolhida (cenários usados, métricas definidas, critérios de sucesso, variações de comportamento exploradas).
3. **Execução** — rodar o experimento de forma organizada: o agente executa os cenários e a avaliação aplica critérios aprovados sobre o trace resultante.
4. **Análise** — apresentar os resultados com honestidade: o que funcionou, o que falhou, o que a hipótese sustenta ou refuta.
5. **Limitações** — registrar explicitamente os limites do experimento (dados sintéticos, modelo usado, cobertura de cenários, incertezas).

A clareza sobre o que se provou e o que não se provou vale mais do que demonstrar qualquer resultado.

## 9. Separação entre material do agente e material de avaliação

Para preservar a integridade da avaliação, o material está dividido em dois pacotes:

- `agent-input/` — o que o agente deve ver. Contém `cases.json` com a mensagem do cliente e o contexto (empresa, pessoa usuária, ativo), além do contrato da API.
- `eval/` — o que a avaliação usa. Contém o gabarito (`expected-paths.json`), os cenários comentados, um protocolo de avaliação (`README-eval.md`) e um runner de exemplo.

O agente deve trabalhar apenas com `agent-input/` e com a API, por HTTP. O gabarito **nunca** deve entrar no contexto do agente, sob pena de invalidar a avaliação: com acesso à resposta, o agente deixa de raciocinar e passa a procurá-la. O gabarito é aplicado após a execução, comparando o trace do agente (chamadas, justificativas, decisão, resposta final) contra o esperado.

## 10. Arquitetura de referência

```
Solicitação ou objetivo
        ↓
Agente ou sistema avaliado
        ↓
Tools, MCP ou integração equivalente
        ↓
API industrial Tractian
        ↓
Consultas e ações na plataforma
        ↓
Resposta, orientação, execução ou escalonamento
        ↓
Trace e resultados do experimento
```

A arquitetura pode usar um agente único ou componentes especializados. A implementação deve permitir inspeção das chamadas e dos resultados.

## 11. Tecnologias sugeridas

A referência de viabilidade são modelos abertos, execução local e opções gratuitas. Cada estudante deverá registrar o modelo, a versão, as configurações e as limitações observadas.

- Python: implementação principal.
- FastAPI, Flask ou cliente HTTP equivalente: consumo e exploração dos contratos da API.
- LangGraph, LangChain, Pydantic AI ou SDK equivalente: orquestração e chamadas de ferramentas.
- MCP SDK: criação de uma camada MCP, caso essa abordagem seja escolhida.
- Pydantic ou JSON Schema: validação de entradas e saídas.
- pytest: automação de testes e experimentos;
- pandas e Plotly: análise e visualização de resultados.
- Streamlit ou Gradio: interface de demonstração.
- Modelos abertos ou roteadores gratuitos: execução dos agentes e avaliações.

RAG, busca híbrida, reranking e observabilidade podem complementar a solução quando contribuírem para o experimento.

## 12. Entregáveis

Cada estudante entregará:

1. **Código-fonte** do agente (integração com a API por tools, MCP ou abordagem equivalente), funcional em um contexto de uso declarado (atendimento direto, copiloto ou autônomo com escopo).
2. **Código/processo da avaliação** aplicado sobre o agente (suíte, runner, biblioteca ou aplicação), com método e hipótese justificados.
3. **Experimento** sobre a hipótese formulada, com resultados e análise.
4. **Documentação técnica** (README), cobrindo:
   - problema considerado e recorte da solução;
   - arquitetura do agente;
   - instalação e execução;
   - modelos e configurações;
   - metodologia experimental;
   - resultados;
   - limitações;
   - possibilidades de evolução.

A documentação deve ser suficiente para que outra pessoa consiga executar a solução de ponta a ponta.

## 13. Critérios gerais de avaliação

A avaliação acadêmica utilizará uma rubrica flexível, compatível com o escopo e a hipótese declarados.

Critérios gerais:

- qualidade da integração com a API;
- coerência técnica da solução;
- clareza da hipótese e do experimento;
- qualidade da análise dos resultados;
- tratamento de limitações e riscos;
- reprodutibilidade;
- documentação;
- qualidade da demonstração.

## 14. Como executar localmente

O repositório traz um `Makefile` com os comandos principais. São necessários Python 3.10 ou superior e o `uv` ([instruções de instalação](https://docs.astral.sh/uv/)).

```
make setup     # cria o ambiente, instala dependências e gera os dados
make up        # sobe a API em http://localhost:8000
make stop      # encerra a API
make test      # roda os testes da API
```

Após `make up`, a interface de exploração (Swagger UI) fica disponível em `http://localhost:8000/docs`. Use `seed=complete` na query para ver respostas completas durante a exploração; omita o `seed` para observar o comportamento probabilístico da API. Instruções detalhadas estão no `README.md`.

## 15. Materiais recomendados

- ReAct: raciocínio intercalado com ações e observações.
- Toolformer: aprendizado de quando e como usar APIs externas.
- TAU-bench: avaliação de agentes em conversas com tools e políticas de domínio.
- LangGraph: construção de fluxos com estado e transições condicionais.
- LangChain Agents: definição e execução de agentes com ferramentas.
- Model Context Protocol: padrão aberto para conectar aplicações de IA a sistemas externos.
- OpenAI Evals: exemplos de estruturas de avaliação.
- promptfoo: testes e comparação de aplicações com LLMs.
- DeepEval: métricas e testes para sistemas com LLMs.
- Phoenix: traces, observabilidade e avaliação.
