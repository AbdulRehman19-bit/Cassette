"""`cassette.yaml`: scenarios, how to start the agent and its MCP servers, diff rules and assertions."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentConfig(_Model):
    command: str
    env: dict[str, str] = Field(default_factory=dict)


class ServerConfig(_Model):
    transport: Literal["stdio"] = "stdio"
    command: str
    args: list[str] | None = None
    env: dict[str, str] = Field(default_factory=dict)

    def split(self) -> tuple[str, list[str]]:
        """`"npx -y pkg"` -> ("npx", ["-y", "pkg"]) unless explicit args are given."""
        if self.args is not None:
            return self.command, list(self.args)
        cmd, *args = self.command.split()
        return cmd, args


class Scenario(_Model):
    name: str = Field(pattern=r"^[\w.-]+$")
    input: dict[str, Any] = Field(default_factory=dict)


class DiffConfig(_Model):
    ignoreArgs: list[str] = Field(default_factory=list)  # noqa: N815
    failOn: list[str] = Field(  # noqa: N815
        default_factory=lambda: ["tool_added", "tool_removed", "tool_args_changed"]
    )
    tolerance: Literal["exact", "normalized"] = "normalized"


class Config(_Model):
    agent: AgentConfig
    servers: dict[str, ServerConfig]
    scenarios: list[Scenario] = Field(min_length=1)
    cassettesDir: str = "cassettes"  # noqa: N815
    diff: DiffConfig = Field(default_factory=DiffConfig)
    assertions: list[dict[str, Any]] = Field(default_factory=list)

    # Set by load_config; not part of the file.
    root: Path = Field(default=Path("."), exclude=True)

    @property
    def cassettes_path(self) -> Path:
        return (self.root / self.cassettesDir).resolve()

    def scenario(self, name: str) -> Scenario:
        for s in self.scenarios:
            if s.name == name:
                return s
        raise KeyError(f"unknown scenario: {name}")


def parse_config(text: str, config_path: str | Path) -> Config:
    cfg = Config.model_validate(yaml.safe_load(text) or {})
    cfg.root = Path(config_path).resolve().parent
    return cfg


def load_config(path: str | Path) -> Config:
    return parse_config(Path(path).read_text(encoding="utf-8"), path)


def expand_env(value: str, env: dict[str, str] | None = None) -> str:
    """Expand `${NAME}` from the environment so configs can reference secrets without containing them."""
    source = os.environ if env is None else env
    return re.sub(r"\$\{(\w+)\}", lambda m: source.get(m.group(1), ""), value)
