from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


@dataclass
class McpServerConfig:
    name: str
    enabled: bool
    transport: str
    command: str | None
    args: list[str]
    url: str | None
    headers: dict[str, str]
    env: dict[str, str]
    timeout_seconds: float
    max_tools: int
    include_name_patterns: list[str]
    required_tool_names: list[str]
    tool_name_prefix: str | None


def _expand_env_var(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        return os.getenv(var_name, "")

    return ENV_VAR_PATTERN.sub(replace, value)


def _expand_env_in_obj(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_env_var(value)
    if isinstance(value, list):
        return [_expand_env_in_obj(item) for item in value]
    if isinstance(value, dict):
        return {k: _expand_env_in_obj(v) for k, v in value.items()}
    return value


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    return current.parents[4]


def load_mcp_servers(config_path: str | None = None) -> list[McpServerConfig]:
    base_dir = _workspace_root()
    load_dotenv(base_dir / ".env", override=False)
    resolved_path = (
        Path(config_path)
        if config_path
        else base_dir / "config" / "mcp" / "servers.yaml"
    )

    if not resolved_path.exists():
        return []

    raw_text = resolved_path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw_text) or {}
    servers = loaded.get("servers", {})

    server_configs: list[McpServerConfig] = []
    for server_name, server_data in servers.items():
        expanded = _expand_env_in_obj(server_data)
        server_configs.append(
            McpServerConfig(
                name=server_name,
                enabled=bool(expanded.get("enabled", True)),
                transport=str(expanded.get("transport", "stdio")),
                command=str(expanded.get("command", "")).strip() or None,
                args=list(expanded.get("args", [])),
                url=str(expanded.get("url", "")).strip() or None,
                headers={
                    str(k): str(v) for k, v in dict(expanded.get("headers", {})).items()
                },
                env={str(k): str(v) for k, v in dict(expanded.get("env", {})).items()},
                timeout_seconds=float(expanded.get("timeout_seconds", 20)),
                max_tools=int(expanded.get("max_tools", 100)),
                include_name_patterns=[
                    str(v) for v in list(expanded.get("include_name_patterns", []))
                ],
                required_tool_names=[
                    str(v) for v in list(expanded.get("required_tool_names", []))
                ],
                tool_name_prefix=expanded.get("tool_name_prefix"),
            )
        )

    return server_configs
