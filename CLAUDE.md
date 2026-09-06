# Tractian — Agente Industrial e Framework de Avaliação

Projeto individual TRACTIAN × Inteli. Constrói um agente que consome a API industrial
fornecida e mede sistematicamente a qualidade desse agente.

A spec do projeto está em `docs/spec-agente-avaliacao.md`.

## Comandos

- `make up` — sobe a API industrial em `:8000` (Swagger em `/docs`)
- `make stop` — para os serviços
- `cd api && .venv/bin/python -m pytest -q` — suíte da API fornecida

`make deps` exige `uv` (instalado em `~/.local/bin/uv`).

## Material fornecido pela TRACTIAN

Não editar. É insumo do experimento, não código do projeto.

- `api/` — API industrial (FastAPI). Retornos degradam por `mode`, determinístico por `seed`.
- `data/*.parquet` — dados sintéticos
- `agent-input/cases.json` — 17 casos de suporte
- `eval/expected-paths.json` — gabarito de trajetória dos 17 casos
- `docs/api-contract.openapi.yaml`, `docs/support-tickets.md`, `docs/test-scenarios.md`
- `STUDENT-GUIDE.md`, `README-tractian.md`, `Makefile`

## Agent skills

### Issue tracker

Issues vivem no GitHub Issues deste repo (`Gabriel-Marques-tech/Tractian`), via `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Vocabulário canônico padrão, sem renomeações: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Convenção single-context: quando existirem, um `CONTEXT.md` na raiz e ADRs em
`docs/adr/`. Nenhum dos dois foi criado — o domínio está documentado no
`README.md` e em `docs/spec-agente-avaliacao.md`, e o vocabulário da API vem de
`STUDENT-GUIDE.md` seção 6. See `docs/agents/domain.md`.
