# Makefile — Challenge TRACTIAN x Inteli
# Sobe tudo que você precisa para testar o agente de ponta a ponta.
#
# Uso típico:
#   make setup           # 1x: cria venv e instala deps (api + agente)
#   make data            # 1x: gera data/, agent-input/, eval/
#   make agent-env       # 1x: cria agent/.env a partir do example (edite a API key)
#   make up              # sobe API industrial (:8000) + agente/UI (:8001) em background
#   make stop            # para os dois
#   make logs            # vê logs dos dois
#
# Variáveis (override: make VAR=val ...):
PYTHON ?= python3
API_PORT ?= 8000
AGENT_PORT ?= 8001
ROOT := $(abspath $(dir $(MAKEFILE_LIST)))
VENV := $(ROOT)/api/.venv
PY := $(VENV)/bin/python
PID_DIR := $(ROOT)/.run
MAKEFLAGS += --no-print-directory

.DEFAULT_GOAL := help

.PHONY: help setup deps data agent-env up up-api up-agent up-all stop logs test clean clean-data

help: ## Mostra esta ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup (1x)
# ---------------------------------------------------------------------------
setup: deps data ## Tudo que o aluno precisa: venv+deps e dados (API + pacotes)

deps: ## Cria o venv e instala dependências da API
	@command -v uv >/dev/null 2>&1 || { echo "Instale o uv: https://docs.astral.sh/uv/"; exit 1; }
	@cd $(ROOT)/api && uv venv --python $(PYTHON) && uv pip install -e ".[dev]"
	@echo "✓ dependências instaladas em $(VENV)"

# ---------------------------------------------------------------------------
# Dados (1x, ou ao mudar seed_data.py / package_material.py)
# ---------------------------------------------------------------------------
data: ## Gera data/*.parquet, agent-input/, eval/
	@cd $(ROOT)/api && $(PY) -m seed_data
	@cd $(ROOT)/api && $(PY) -m package_material
	@echo "✓ dados gerados (data/, agent-input/, eval/)"

agent-env: ## Cria agent/.env a partir do .env.example (edite a API key depois)
	@if [ ! -f agent/.env ]; then cp agent/.env.example agent/.env && echo "✓ agent/.env criado — edite OPENAI_API_KEY/BASE_URL/MODEL"; else echo "✓ agent/.env já existe (não sobrescrito)"; fi

# ---------------------------------------------------------------------------
# Rodar (background)
# ---------------------------------------------------------------------------
# `up` sobe só a API industrial.
# `up-all` sobe também o seu agente/UI (agent/), quando você o tiver criado.
up: up-api ## Sobe a API industrial (:8000) em background
	@echo ""
	@echo "✓ API no ar:"
	@echo "   Swagger UI: http://localhost:$(API_PORT)/docs"
	@echo "(make stop para parar · make logs para ver saída)"

up-all: up-api up-agent ## Sobe API + seu agente/UI (:8001)
	@echo ""
	@echo "✓ Tudo no ar:"
	@echo "   API industrial (Swagger): http://localhost:$(API_PORT)/docs"
	@echo "   Agente / UI de chat:      http://localhost:$(AGENT_PORT)"
	@echo "(make stop para parar · make logs para ver saída)"

# Espera até ~10s por uma porta responder HTTP 200 (evita falsos negativos de "sleep fixo").
define wait_up
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		curl -s -o /dev/null http://localhost:$(1) && break; sleep 1; \
	done
endef

up-api: ## Só a API industrial (:8000) em background
	@mkdir -p $(PID_DIR)
	@cd $(ROOT)/api && $(PY) -m uvicorn app.main:app --host 127.0.0.1 --port $(API_PORT) \
		> $(PID_DIR)/api.log 2>&1 & echo $$! > $(PID_DIR)/api.pid
	$(call wait_up,$(API_PORT))
	@curl -s -o /dev/null -w "✓ API industrial em :$(API_PORT) (HTTP %{http_code})\n" http://localhost:$(API_PORT)/docs \
		|| echo "✗ API não subiu — veja $(PID_DIR)/api.log"

up-agent: up-api ## Só o agente/UI (:8001) em background (sobe a API antes se precisar)
	@mkdir -p $(PID_DIR)
	@if [ ! -f $(ROOT)/agent/.env ]; then echo "✗ rode 'make agent-env' e edite a API key primeiro"; exit 1; fi
	@cd $(ROOT)/api && $(PY) $(ROOT)/agent/server.py \
		> $(PID_DIR)/agent.log 2>&1 & echo $$! > $(PID_DIR)/agent.pid
	$(call wait_up,$(AGENT_PORT))
	@curl -s -o /dev/null -w "✓ Agente/UI em :$(AGENT_PORT) (HTTP %{http_code})\n" http://localhost:$(AGENT_PORT)/ \
		|| echo "✗ Agente não subiu — veja $(PID_DIR)/agent.log"

stop: ## Para API industrial e agente
	@for f in $(PID_DIR)/api.pid $(PID_DIR)/agent.pid; do \
		if [ -f $$f ]; then kill $$(cat $$f) 2>/dev/null && echo "✓ parado $$(basename $$f .pid)"; rm -f $$f; fi; \
	done
	@# mata sobras por nome (caso os pids tenham sumido)
	@-pkill -f "uvicorn app.main:app --host 127.0.0.1 --port $(API_PORT)" 2>/dev/null || true
	@-pkill -f "agent/server.py" 2>/dev/null || true

logs: ## Mostra logs da API e do agente (tail -f)
	@echo "== API ==		== Agente =="
	@tail -f $(PID_DIR)/api.log $(PID_DIR)/agent.log 2>/dev/null || echo "Sem logs — nada rodando? (make up)"

# ---------------------------------------------------------------------------
# Dev
# ---------------------------------------------------------------------------
test: ## Roda os testes da API industrial
	@cd $(ROOT)/api && $(PY) -m pytest -q

clean-data: ## Apaga dados gerados (data/, agent-input/, eval/) — regenere com make data
	@rm -rf data agent-input eval
	@echo "✓ dados apagados (rode make data para regenerar)"

clean: stop clean-data ## Para tudo e apaga dados + venv
	@rm -rf $(VENV) $(PID_DIR)
	@echo "✓ limpo"
