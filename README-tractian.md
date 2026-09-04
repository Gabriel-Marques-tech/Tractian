# Challenge TRACTIAN × Inteli — Engenharia e Avaliação de Agentes Industriais

Repositório com o material-base para construir e avaliar agentes de IA sobre uma API industrial. 
O briefing completo está em [`STUDENT-GUIDE.md`](./STUDENT-GUIDE.md).

> **Para começar:** rode `make setup && make up` e abra http://localhost:8000/docs. Veja também o
> [`QUICKSTART.md`](./QUICKSTART.md) (30 segundos) e o briefing completo em
> [`STUDENT-GUIDE.md`](./STUDENT-GUIDE.md).

## O que tem aqui

| Artefato | Arquivo | Para quê |
| :------- | :------ | :------- |
| Guia do estudante | [`STUDENT-GUIDE.md`](./STUDENT-GUIDE.md) | Problema, solução esperada, entregáveis, método. **Comece por aqui.** |
| Contrato da API | [`docs/api-contract.openapi.yaml`](./docs/api-contract.openapi.yaml) | OpenAPI 3.1 com 18 endpoints nas 7 categorias. |
| Chamados | [`docs/support-tickets.md`](./docs/support-tickets.md) | 17 dúvidas reais de cliente e suporte. |
| Cenários de teste | [`docs/test-scenarios.md`](./docs/test-scenarios.md) | 16 cenários no estilo TAU-bench. |
| Schema de dados | [`docs/data-schema.md`](./docs/data-schema.md) | Tabelas parquet e comportamento probabilístico. |
| Implementação da API | [`api/`](./api/) | FastAPI que serve o contrato, gerador de dados, testes. |
| Dados sintéticos | [`data/`](./data/) | Arquivos parquet + `seed.json` que populam a API. Gerados por `make data`. |
| Pacote do agente | [`agent-input/`](./agent-input/) | `cases.json` (mensagem + contexto) + contrato. O que o agente deve ver. |
| Pacote de avaliação | [`eval/`](./eval/) | Gabarito: trajetórias esperadas, cenários, protocolo de avaliação, runner de exemplo. |

## Como os artefatos se conectam

```
Chamado de suporte (contexto)  ─►  Cenário de teste  ─►  Trajetória de chamadas à API  ─►  Resolução
        ▲                           (TAU-bench)                       │
        │                                                             ▼
   dados sintéticos (parquet)  ◄──  populam  ────────────────────  API industrial (contrato OpenAPI)
```

Cada chamado tem um ativo cujos dados sustentam a pergunta; a API é desenhada para responder a
essas perguntas; os cenários traduzem um chamado em sequência de chamadas e na resolução esperada.

## Conceitos de domínio essenciais

- **Baseline** — estado normal aprendido do próprio ativo/ponto. Ciclo de vida: `learning →
  established → invalidated`. O limiar de alarme de RMS **deriva do baseline** (referência +
  tolerância), não de norma ISO nem de tabela por classe de máquina.
- **Dois modos de detecção de falha:**
  - `baseline` — por desvio (desbalanceamento, desalinhamento, rolamento, elétrica). Exige baseline
    `established`.
  - `symptom` — sintomática (lubrificação): a presença do sintoma já indica a falha, independente
    de baseline.
- **Insight / análise** — diagnóstico automático do modelo, com tipo, severidade, confiança,
  evidência, limitações e `detection_mode`.
- **Qualidade e frescor dos dados** — completude, relação sinal-ruído, atualidade. Afetam a
  capacidade do modelo de inferir e a confiabilidade do baseline. Compare com os `requirements` do
  modelo.
- **Decisão do agente** — **orientar** / **agir** / **escalar** (encaminhar para humano quando o
  caso extrapola o remoto).

## O projeto — como trabalhar

O projeto unifica **construção e avaliação de agente**: o estudante constrói o agente (tools, MCP ou
equivalente), testa-o contra os tickets e, em seguida, avalia sua qualidade e confiabilidade usando
os cenários e o gabarito.

1. **Explore o espaço do problema** — leia os [chamados](./docs/support-tickets.md) e o [contrato
  da API](./docs/api-contract.openapi.yaml); suba a API (`make up`); explore o Swagger
  (`:8000/docs`, com `seed=complete`).
2. **Construa o agente** — conecte-se à API, investigue antes de responder, trate retornos
  incompletos com honestidade, decida entre orientar/agir/escalar. Teste nos tickets de
  `agent-input/cases.json`.
3. **Avalie o agente** — use os [cenários](./docs/test-scenarios.md) como itens de benchmark.
  Rode o agente isolado do gabarito, capture o trace e aplique os critérios em `eval/` após a
  execução (asserts + rubrica). Veja `eval/README-eval.md`.
4. **Registre e demonstre** — formule uma hipótese (de arquitetura ou de comportamento), justifique
  o método, apresente resultados e limitações.

## Separação entre o agente e a avaliação

| Pacote | Local | Para quem | Conteúdo |
| :----- | :---- | :-------- | :------- |
| Input do agente | `agent-input/` | Agente | `cases.json` (mensagem + contexto), `api-contract.openapi.yaml` |
| Gabarito | `eval/` | Avaliação | `expected-paths.json`, `test-scenarios.md`, `README-eval.md` |

> **Atenção:** o agente não deve ter acesso ao gabarito (`eval/`, `docs/test-scenarios.md`,
> `data/cases.parquet`). Com acesso à resposta, ele deixa de raciocinar — a avaliação se torna
> inválida. O gabarito é aplicado **após** a execução, sobre o trace do agente.

## Executar localmente

Precisa de **Python ≥ 3.10** e **`uv`** ([instalação do uv](https://docs.astral.sh/uv/)).

```bash
make setup   # 1x: cria venv, instala deps e gera os dados (data/, agent-input/, eval/)
make up      # sobe a API em http://localhost:8000 (Swagger UI em /docs)
make stop    # para a API
make test    # roda os testes automatizados
```

Use **`seed=complete`** na query string para ver respostas completas durante a exploração; omita o
`seed` para observar o comportamento probabilístico. Ativos com override de cenário fixo (ex.: G501 com
`rms=unavailable`) mantêm o comportamento do cenário mesmo com `seed=complete`.

Para endpoints de ação, envie o header `x-user-id` (define perfil/permissões). Os usuários estão em
`data/users.parquet` e nos `cases.json` do `agent-input/`.

## Escala do material

8 empresas, 26 ativos, 24 análises, 17 chamados, 16 cenários. 
