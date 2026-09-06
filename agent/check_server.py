"""Verificação do servidor MCP sem agente e sem modelo (critérios da issue #1)."""

from __future__ import annotations

import asyncio
import os

from agent.mcp_client import connect

API = os.environ.get("TRACTIAN_API", "http://localhost:8000")


async def main() -> None:
    async with connect(API, seed="demo") as tools:
        listed = await tools.list_tools()
        print(f"ferramentas expostas: {len(listed)}")
        for t in listed:
            print(f"  - {t.name}")

        print("\nchamada real (get_asset asset_G501):")
        call = await tools.call("get_asset", {"asset_id": "asset_G501"})
        print(f"  passo     : {call.as_path_step()}")
        print(f"  ok        : {call.ok}")
        print(f"  mode      : {call.mode.value if call.mode else None}")
        print(f"  notes     : {call.notes}")
        name = (call.data or {}).get("name") if isinstance(call.data, dict) else None
        print(f"  data.name : {name}")
        print(f"  latencia  : {call.duration_ms} ms")

        print("\ndeterminismo (mesma seed, 2x em get_data_quality):")
        for i in (1, 2):
            c = await tools.call("get_data_quality", {"asset_id": "asset_C710"})
            print(f"  run{i}: mode={c.mode.value if c.mode else None}")

        print("\nferramenta inexistente:")
        bad = await tools.call("nao_existe", {})
        print(f"  ok={bad.ok} error={bad.error}")


if __name__ == "__main__":
    asyncio.run(main())
