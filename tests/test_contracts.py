from langgraph.checkpoint.memory import MemorySaver

from godot_forge.models import DemoGodotModel
from godot_forge.runtime import GodotForgeRuntime
from godot_forge.schemas import FileChange

REQUEST = "生成一个包含移动、敌人、血量和 HUD 的 2D 生存原型"


class CrossModuleOnceModel(DemoGodotModel):
    def __init__(self) -> None:
        self.injected = False

    def develop(self, specialist, spec, plan, knowledge):
        bundle = super().develop(specialist, spec, plan, knowledge)
        if specialist == "gameplay" and not self.injected:
            bundle.changes.append(
                FileChange(
                    path="scripts/hud.gd",
                    content="extends CanvasLayer\n",
                    purpose="故意越权修改 interface 文件",
                )
            )
            self.injected = True
        return bundle


def test_module_ownership_violation_triggers_repair(settings, runner) -> None:
    with GodotForgeRuntime(
        settings,
        checkpointer=MemorySaver(),
        model=CrossModuleOnceModel(),
        runner=runner,
    ) as runtime:
        response = runtime.run(REQUEST, "contract-violation")
        state = runtime.get_state("contract-violation")

    assert response.status == "awaiting_approval"
    assert state["repair_count"] == 1
    assert state["review"]["accepted"] is True


def test_plan_contains_explicit_public_interfaces(runtime) -> None:
    runtime.run(REQUEST, "contract-plan")
    state = runtime.get_state("contract-plan")
    modules = state["plan"]["modules"]

    assert [module["name"] for module in modules] == [
        "gameplay",
        "scene",
        "interface",
    ]
    assert all(module["public_interfaces"] for module in modules)
    assert all(module["owned_paths"] for module in modules)


def test_approval_contains_contracts_hashes_and_diffs(runtime) -> None:
    response = runtime.run(REQUEST, "contract-approval")

    assert response.approval is not None
    assert len(response.approval["contracts"]) == 3
    assert len(response.approval["changes"]) == 7
    assert all(len(item["sha256"]) == 64 for item in response.approval["changes"])
    assert all(item["action"] == "create" for item in response.approval["changes"])
    assert all("+++ b/" in item["diff"] for item in response.approval["changes"])
