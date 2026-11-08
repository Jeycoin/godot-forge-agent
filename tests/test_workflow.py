from conftest import FakeRunner
from langgraph.checkpoint.memory import MemorySaver

from godot_forge.models import DemoGodotModel
from godot_forge.runtime import GodotForgeRuntime
from godot_forge.schemas import VerificationResult

REQUEST = "为 Game Jam 做一个 2D 生存游戏，包含玩家移动、敌人追踪、血量和计分"


def test_generation_waits_for_approval_before_writing_files(runtime, settings) -> None:
    response = runtime.run(REQUEST, "approval-gate")

    assert response.status == "awaiting_approval"
    assert response.approval is not None
    assert len(response.approval["files"]) == 7
    assert not (settings.workspace_path / "project.godot").exists()
    develop_traces = [item for item in response.trace if item["node"] == "develop"]
    assert len(develop_traces) == 3


def test_approved_build_writes_playable_project_and_verifies(runtime, runner, settings) -> None:
    runtime.run(REQUEST, "approved-build")
    response = runtime.resume("approved-build", True, "确认写入隔离目录")

    assert response.status == "completed"
    assert response.verification is not None
    assert response.verification["status"] == "passed"
    assert runner.calls == 1
    assert len(response.generated_files) == 7
    assert (settings.workspace_path / "scripts" / "player.gd").exists()
    assert "SMOKE_TEST_OK" in (
        settings.workspace_path / "scripts" / "main.gd"
    ).read_text(encoding="utf-8")


def test_rejected_build_never_writes_or_runs(runtime, runner, settings) -> None:
    runtime.run(REQUEST, "rejected-build")
    response = runtime.resume("rejected-build", False)

    assert response.status == "completed"
    assert "未写入任何文件" in (response.response or "")
    assert runner.calls == 0
    assert not settings.workspace_path.exists()


def test_failed_engine_run_triggers_one_bounded_repair(settings) -> None:
    runner = FakeRunner(
        [
            VerificationResult(status="failed", errors=["Parse Error: test failure"]),
            VerificationResult(status="passed", output="SMOKE_TEST_OK", exit_code=0),
        ]
    )
    with GodotForgeRuntime(
        settings,
        checkpointer=MemorySaver(),
        runner=runner,
    ) as runtime:
        runtime.run(REQUEST, "repair-loop")
        response = runtime.resume("repair-loop", True)
        state = runtime.get_state("repair-loop")

    assert response.verification is not None
    assert response.verification["status"] == "passed"
    assert state["repair_count"] == 1
    assert runner.calls == 2


class UnsafeOnceModel(DemoGodotModel):
    def __init__(self) -> None:
        self.injected = False

    def develop(self, specialist, spec, plan, knowledge):
        bundle = super().develop(specialist, spec, plan, knowledge)
        if specialist == "scene" and not self.injected:
            bundle.changes[0].path = "../outside.gd"
            self.injected = True
        return bundle


def test_static_review_repairs_path_traversal_before_approval(settings, runner) -> None:
    with GodotForgeRuntime(
        settings,
        checkpointer=MemorySaver(),
        model=UnsafeOnceModel(),
        runner=runner,
    ) as runtime:
        response = runtime.run(REQUEST, "unsafe-path")
        state = runtime.get_state("unsafe-path")

    assert response.status == "awaiting_approval"
    assert state["repair_count"] == 1
    assert state["review"]["accepted"] is True
    assert not (settings.workspace_path.parent / "outside.gd").exists()


def test_sqlite_checkpoint_resumes_after_runtime_restart(settings) -> None:
    runner = FakeRunner()
    with GodotForgeRuntime(settings, runner=runner) as first_runtime:
        first = first_runtime.run(REQUEST, "durable-build")
        assert first.status == "awaiting_approval"

    with GodotForgeRuntime(settings, runner=runner) as second_runtime:
        response = second_runtime.resume("durable-build", True)

    assert response.status == "completed"
    assert response.verification is not None
    assert response.verification["status"] == "passed"
