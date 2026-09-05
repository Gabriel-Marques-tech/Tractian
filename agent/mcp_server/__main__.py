"""Ponto de entrada: `python -m agent.mcp_server`."""

from agent.mcp_server.server import from_environment

if __name__ == "__main__":
    from_environment().run("stdio")
