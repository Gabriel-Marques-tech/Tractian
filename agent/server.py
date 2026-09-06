"""Serve a build do inspetor em :8001.

O `Makefile` da TRACTIAN já prevê este arquivo em `up-agent`, então `make up-all`
sobe API e inspetor sem que uma linha do Makefile precise ser editada — ele é
material do parceiro e não deve ser tocado.

Serve estático e nada mais: o inspetor lê `data/runs.json` e não fala com
backend em runtime. É o que faz a mesma `ui/dist/` servir aqui, no `npm run
dev` e num deploy estático.
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "ui" / "dist"
PORT = int(os.environ.get("AGENT_PORT", "8001"))

app = FastAPI(title="Inspetor de traces")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": DIST.exists(), "dist": str(DIST)})


if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="ui")
else:
    @app.get("/")
    def sem_build() -> JSONResponse:
        return JSONResponse(
            {
                "erro": "ui/dist nao existe",
                "como": "cd ui && npm install && npm run build",
                "dados": "python -m agent.export",
            },
            status_code=503,
        )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT)
