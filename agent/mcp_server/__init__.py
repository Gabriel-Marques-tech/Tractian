"""Servidor MCP que expõe a API industrial da TRACTIAN como ferramentas."""

from agent.mcp_server.server import register_tools, server

__all__ = ["register_tools", "server"]
