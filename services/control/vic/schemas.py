from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateRun(StrictModel):
    task_id: int = Field(ge=1, le=100)
    variant: Literal["A", "B", "C"]
    seed: int = Field(ge=0, le=2147483647)
    mode: Literal["demo", "eval"] = "eval"
    runtime: Literal["web-dev", "browser", "windows", "linux", "android"] = "browser"


class Action(StrictModel):
    epoch: int = Field(ge=0)
    action_id: str = Field(min_length=1, max_length=100)
    frame: int = Field(ge=0)
    kind: Literal["click", "double_click", "drag", "scroll", "key", "text", "wait"]
    x: int | None = Field(default=None, ge=0, lt=1280)
    y: int | None = Field(default=None, ge=0, lt=960)
    to_x: int | None = Field(default=None, ge=0, lt=1280)
    to_y: int | None = Field(default=None, ge=0, lt=960)
    text: str = Field(default="", max_length=16000)
    key: str = Field(default="", max_length=100)
    delta_y: int = Field(default=0, ge=-3000, le=3000)
    wait_ms: int = Field(default=250, ge=0, le=2000)


class Mutation(StrictModel):
    epoch: int = Field(ge=0)
    action_id: str = Field(min_length=1, max_length=100)
    op: str = Field(max_length=40)
    target: str = Field(default="", max_length=100)
    value: str = Field(default="", max_length=16000)
    ids: list[str] = Field(default_factory=list, max_length=100)


class Review(StrictModel):
    approved: bool
    reviewer: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=2000)


class EvaluateTask(StrictModel):
    run_id: str = Field(pattern=r"^[a-f0-9]{32}$")
