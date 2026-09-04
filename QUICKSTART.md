# Quickstart — 30 segundos

Como executar o projeto.

## Requisitos

- Python ≥ 3.10
- [`uv`](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

## Rodar

```bash
make setup   # cria venv, instala deps e gera os dados (data/, agent-input/, eval/)
make up      # sobe a API em http://localhost:8000
```

Abra **http://localhost:8000/docs** — Swagger UI para explorar.

## Por onde seguir depois

- **Entender o problema:** [`STUDENT-GUIDE.md`](./STUDENT-GUIDE.md)
- **Explorar a API:** no Swagger, use `seed=complete` (ex.: `GET /assets/asset_C710?seed=complete`)
- **Chamados de exemplo:** [`docs/support-tickets.md`](./docs/support-tickets.md)
- **Cenários de teste:** [`docs/test-scenarios.md`](./docs/test-scenarios.md)
- **Parar:** `make stop`

## Erros comuns

- **`make: *** No rule to make target`** — rode `make` a partir da raiz do projeto (onde está o `Makefile`).
- **`uv: command not found`** — instale o uv (link acima) e abra um novo terminal.
- **API não responde** — rode `make data` se você editou `seed_data.py` ou apagou `data/`.
