"""The cassette file format (version 1): one JSON file per recorded run."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CASSETTE_VERSION = 1


class _Model(BaseModel):
    # Cassette files are a public format: reject typos instead of silently ignoring them.
    model_config = ConfigDict(extra="forbid")


class ModelStep(_Model):
    i: int = Field(ge=0)
    type: Literal["model"]
    request: Any = None
    response: Any = None
    usage: dict[str, int] | None = None  # {"in": ..., "out": ...}
    ms: float | None = None


class ToolStep(_Model):
    i: int = Field(ge=0)
    type: Literal["tool"]
    server: str
    name: str
    args: dict[str, Any]
    result: Any = None
    isError: bool | None = None  # noqa: N815 - matches the on-disk format
    ms: float | None = None


Step = Annotated[ModelStep | ToolStep, Field(discriminator="type")]


class ToolSchema(_Model):
    name: str
    inputSchema: Any = None  # noqa: N815


class AgentInfo(_Model):
    model: str | None = None
    promptHash: str | None = None  # noqa: N815


class Cassette(_Model):
    version: Literal[1] = 1
    scenario: str
    recordedAt: str  # noqa: N815
    agent: AgentInfo = Field(default_factory=AgentInfo)
    input: dict[str, Any] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list)
    output: str = ""
    toolSchemas: dict[str, list[ToolSchema]] = Field(default_factory=dict)  # noqa: N815

    def tool_steps(self) -> list[ToolStep]:
        return [s for s in self.steps if isinstance(s, ToolStep)]

    def model_steps(self) -> list[ModelStep]:
        return [s for s in self.steps if isinstance(s, ModelStep)]
