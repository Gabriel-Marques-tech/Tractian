"""Ponto de entrada: `python -m agent.mcp_server`."""

from agent.mcp_server.server import register_tools, server

if __name__ == "__main__":
    register_tools(server)
    server.run("stdio")
