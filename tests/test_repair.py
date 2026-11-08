from conftest import FakeRunner
from langgraph.checkpoint.memory import MemorySaver

from godot_forge.models import DemoGodotModel
from godot_forge.runtime import GodotForgeRuntime
from godot_forge.schemas import ArtifactBundle, VerificationResult

REQUEST = "生成一个 2D 生存原型，包含移动、敌人、血量和分数"


class PartialRepairModel(DemoGodotModel):
    def repair(self, spec, changes, errors, knowledge):
        return ArtifactBundle(
            specialist="repair",
            changes=[changes[0]],
            notes="只修复一个文件，其余文件必须保留",
        )


def test_partial_repair_preserves_unmodified_files(settings) -> None:
    runner = FakeRunner(
        [
            VerificationResult(status="failed", errors=["test failure"]),
            VerificationResult(status="passed", output="SMOKE_TEST_OK", exit_code=0),
        ]
    )
    with GodotForgeRuntime(
        settings,
        checkpointer=MemorySaver(),
        model=PartialRepairModel(),
        runner=runner,
    ) as runtime:
        runtime.run(REQUEST, "partial-repair")
        response = runtime.resume("partial-repair", True)

    assert response.verification is not None
    assert response.verification["status"] == "passed"
    assert len(response.generated_files) == 7


class AlwaysUnsafeModel(DemoGodotModel):
    def __init__(self) -> None:
        self.repair_calls = 0

    def develop(self, specialist, spec, plan, knowledge):
        bundle = super().develop(specialist, spec, plan, knowledge)
        if specialist == "scene":
            bundle.changes[0].path = "../unsafe.gd"
        return bundle

    def repair(self, spec, changes, errors, knowledge):
        self.repair_calls += 1
        return ArtifactBundle(specialist="repair", changes=[])


def test_repeated_static_failure_is_bounded_without_verification_state(settings, runner) -> None:
    settings = settings.model_copy(update={"max_repairs": 2})
    model = AlwaysUnsafeModel()
    with GodotForgeRuntime(
        settings,
        checkpointer=MemorySaver(),
        model=model,
        runner=runner,
    ) as runtime:
        response = runtime.run(REQUEST, "bounded-static-repair")
        state = runtime.get_state("bounded-static-repair")

    assert response.status == "completed"
    assert "未通过静态审查" in (response.response or "")
    assert state["repair_count"] == 2
    assert model.repair_calls == 2
    assert runner.calls == 0
