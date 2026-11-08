from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver

from godot_forge.config import Settings
from godot_forge.runtime import GodotForgeRuntime
from godot_forge.schemas import VerificationResult


class FakeRunner:
    def __init__(self, results: list[VerificationResult] | None = None) -> None:
        self.results = results or []
        self.calls = 0

    def run(self, workspace: Path) -> VerificationResult:
        self.calls += 1
        if self.results:
            return self.results.pop(0)
        return VerificationResult(
            status="passed",
            command=["fake-godot", "--headless"],
            exit_code=0,
            output="SMOKE_TEST_OK",
        )


@pytest.fixture
def settings(tmp_path):
    return Settings(
        workspace_path=tmp_path / "game",
        database_path=tmp_path / "forge.db",
    )


@pytest.fixture
def runner():
    return FakeRunner()


@pytest.fixture
def runtime(settings, runner):
    with GodotForgeRuntime(
        settings,
        checkpointer=MemorySaver(),
        runner=runner,
    ) as instance:
        yield instance
