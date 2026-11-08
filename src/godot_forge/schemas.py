from typing import Any, Literal

from pydantic import BaseModel, Field


class GameSpec(BaseModel):
    title: str
    genre: str
    description: str
    mechanics: list[str] = Field(min_length=2, max_length=8)
    controls: str
    visual_style: str


class ModuleContract(BaseModel):
    name: str
    responsibility: str
    owned_paths: list[str] = Field(min_length=1, max_length=10)
    public_interfaces: list[str] = Field(default_factory=list, max_length=10)


class DevelopmentPlan(BaseModel):
    architecture: str
    tasks: list[str] = Field(min_length=2, max_length=10)
    file_paths: list[str] = Field(min_length=2, max_length=20)
    modules: list[ModuleContract] = Field(min_length=1, max_length=6)


class DocumentHit(BaseModel):
    document_id: str
    title: str
    topic: str
    content: str
    score: float


class FileChange(BaseModel):
    path: str
    content: str
    purpose: str = "实现对应模块功能"
    owner: str = ""


class ArtifactBundle(BaseModel):
    specialist: str
    changes: list[FileChange] = Field(default_factory=list)
    notes: str = ""
    replace_all: bool = False


class ReviewResult(BaseModel):
    accepted: bool
    feedback: str = ""


class ValidationStageResult(BaseModel):
    name: Literal["import", "smoke_test"]
    status: Literal["passed", "failed"]
    command: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    output: str = ""
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0


class VerificationResult(BaseModel):
    status: Literal["passed", "failed", "skipped"]
    command: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    output: str = ""
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0
    stages: list[ValidationStageResult] = Field(default_factory=list)


class BuildRequest(BaseModel):
    request: str = Field(min_length=4, max_length=5000)
    thread_id: str | None = None


class ApprovalRequest(BaseModel):
    approved: bool
    note: str = Field(default="", max_length=500)


class RunResponse(BaseModel):
    thread_id: str
    status: Literal["completed", "awaiting_approval"]
    response: str | None = None
    approval: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    generated_files: list[str] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
