from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.types import Send, interrupt

from godot_forge.config import Settings
from godot_forge.models import GameModel
from godot_forge.retrieval import GodotKnowledgeBase
from godot_forge.schemas import (
    ArtifactBundle,
    DevelopmentPlan,
    DocumentHit,
    FileChange,
    GameSpec,
    ReviewResult,
    VerificationResult,
)
from godot_forge.state import ForgeState
from godot_forge.workspace import (
    GodotRunner,
    WorkspaceError,
    WorkspaceManager,
    validate_relative_path,
)


def trace_event(node: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "node": node,
        "message": message,
        "details": details,
    }


class ForgeNodes:
    def __init__(
        self,
        settings: Settings,
        model: GameModel,
        knowledge_base: GodotKnowledgeBase,
        workspace: WorkspaceManager,
        runner: GodotRunner,
    ) -> None:
        self.settings = settings
        self.model = model
        self.knowledge_base = knowledge_base
        self.workspace = workspace
        self.runner = runner

    def design(self, state: ForgeState) -> dict[str, Any]:
        spec = self.model.design(state["request"])
        return {
            "spec": spec.model_dump(mode="json"),
            "trace": [
                trace_event(
                    "design",
                    "完成结构化游戏需求设计",
                    title=spec.title,
                    mechanics=spec.mechanics,
                )
            ],
        }

    def plan(self, state: ForgeState) -> dict[str, Any]:
        spec = GameSpec.model_validate(state["spec"])
        plan = self.model.plan(spec)
        return {
            "plan": plan.model_dump(mode="json"),
            "trace": [
                trace_event(
                    "plan",
                    "完成模块拆分与文件计划",
                    architecture=plan.architecture,
                    file_count=len(plan.file_paths),
                )
            ],
        }

    def retrieve(self, state: ForgeState) -> dict[str, Any]:
        spec = GameSpec.model_validate(state["spec"])
        query = " ".join([state["request"], spec.description, *spec.mechanics])
        hits = self.knowledge_base.search(query, self.settings.retrieval_top_k)
        return {
            "knowledge": [hit.model_dump(mode="json") for hit in hits],
            "trace": [
                trace_event(
                    "retrieve",
                    "检索 Godot 4 开发与验证文档",
                    document_ids=[hit.document_id for hit in hits],
                )
            ],
        }

    def fan_out(self, state: ForgeState) -> list[Send]:
        plan = DevelopmentPlan.model_validate(state["plan"])
        return [
            Send("develop", {**state, "specialist": module.name})
            for module in plan.modules
        ]

    def develop(self, state: ForgeState) -> dict[str, Any]:
        bundle = self.model.develop(
            state["specialist"],
            GameSpec.model_validate(state["spec"]),
            DevelopmentPlan.model_validate(state["plan"]),
            [DocumentHit.model_validate(hit) for hit in state.get("knowledge", [])],
        )
        return {
            "artifacts": [bundle.model_dump(mode="json")],
            "trace": [
                trace_event(
                    "develop",
                    f"{state['specialist']} 模块生成完成",
                    file_paths=[change.path for change in bundle.changes],
                )
            ],
        }

    def integrate(self, state: ForgeState) -> dict[str, Any]:
        bundles = [ArtifactBundle.model_validate(item) for item in state.get("artifacts", [])]
        changes = [
            change.model_copy(update={"owner": bundle.specialist})
            for bundle in bundles
            for change in bundle.changes
        ]
        return {
            "file_changes": [change.model_dump(mode="json") for change in changes],
            "trace": [
                trace_event(
                    "integrate",
                    "按模块契约汇总并行开发产物",
                    file_count=len(changes),
                    owners={bundle.specialist: len(bundle.changes) for bundle in bundles},
                )
            ],
        }

    def review(self, state: ForgeState) -> dict[str, Any]:
        changes = [FileChange.model_validate(item) for item in state["file_changes"]]
        plan = DevelopmentPlan.model_validate(state["plan"])
        paths = [change.path for change in changes]
        problems = []
        required = {"project.godot", "scenes/main.tscn", "scripts/main.gd"}
        missing = required - set(paths)
        if missing:
            problems.append(f"缺少运行必需文件: {sorted(missing)}")
        duplicates = sorted({path for path in paths if paths.count(path) > 1})
        if duplicates:
            problems.append(f"多个模块修改同一文件: {duplicates}")
        owned_paths = [path for module in plan.modules for path in module.owned_paths]
        contract_duplicates = sorted(
            {path for path in owned_paths if owned_paths.count(path) > 1}
        )
        if contract_duplicates:
            problems.append(f"模块契约存在文件所有权冲突: {contract_duplicates}")
        ownership = {
            path: module.name for module in plan.modules for path in module.owned_paths
        }
        for change in changes:
            try:
                validate_relative_path(change.path)
            except WorkspaceError as exc:
                problems.append(str(exc))
            expected_owner = ownership.get(change.path)
            if expected_owner is None:
                problems.append(f"{change.path} 不属于任何模块契约")
            elif change.owner != expected_owner:
                problems.append(
                    f"{change.path} 应由 {expected_owner} 负责，实际为 {change.owner}"
                )
            if "OS.execute(" in change.content:
                problems.append(f"{change.path} 包含被禁止的 OS.execute")
        main_script = next(
            (change.content for change in changes if change.path == "scripts/main.gd"),
            "",
        )
        if "--smoke-test" not in main_script or "SMOKE_TEST_OK" not in main_script:
            problems.append("主场景缺少可执行的冒烟测试协议")
        review = ReviewResult(accepted=not problems, feedback="；".join(problems))
        return {
            "review": review.model_dump(mode="json"),
            "trace": [
                trace_event(
                    "review",
                    "契约与安全审查通过" if review.accepted else "契约与安全审查未通过",
                    feedback=review.feedback,
                )
            ],
        }

    def route_after_review(self, state: ForgeState) -> str:
        if not state["review"]["accepted"]:
            if state.get("repair_count", 0) < self.settings.max_repairs:
                return "repair"
            return "respond"
        return "apply" if state.get("approval_granted") else "approval"

    def approval(self, state: ForgeState) -> dict[str, Any]:
        spec = GameSpec.model_validate(state["spec"])
        plan = DevelopmentPlan.model_validate(state["plan"])
        changes = [FileChange.model_validate(item) for item in state["file_changes"]]
        decision = interrupt(
            {
                "type": "workspace_change_approval",
                "run_id": state["run_id"],
                "title": spec.title,
                "workspace": str(self.workspace.root),
                "contracts": [
                    module.model_dump(mode="json") for module in plan.modules
                ],
                "files": [
                    {
                        "path": change.path,
                        "purpose": change.purpose,
                        "owner": change.owner,
                        "bytes": len(change.content.encode("utf-8")),
                    }
                    for change in changes
                ],
                "changes": self.workspace.preview(changes),
                "instruction": "确认模块契约、目标目录和文件 diff；批准后执行导入与运行验证",
            }
        )
        approved = isinstance(decision, dict) and decision.get("approved") is True
        if not approved:
            return {
                "approval_granted": False,
                "final_response": "已取消本次工程变更，未写入任何文件。",
                "trace": [trace_event("approval", "用户拒绝工程变更")],
            }
        return {
            "approval_granted": True,
            "trace": [trace_event("approval", "用户批准工程变更与自动验证")],
        }

    def route_after_approval(self, state: ForgeState) -> str:
        return "apply" if state.get("approval_granted") else "respond"

    def apply(self, state: ForgeState) -> dict[str, Any]:
        if not state.get("approval_granted"):
            result = VerificationResult(
                status="failed", errors=["缺少工程修改授权，已阻止写入"]
            )
            return {"verification": result.model_dump(mode="json")}
        changes = [FileChange.model_validate(item) for item in state["file_changes"]]
        try:
            written = self.workspace.apply(changes)
        except WorkspaceError as exc:
            result = VerificationResult(status="failed", errors=[str(exc)])
            return {
                "verification": result.model_dump(mode="json"),
                "trace": [trace_event("apply", "工程写入失败并已回滚")],
            }
        return {
            "applied_files": written,
            "trace": [trace_event("apply", "工程文件已原子写入", files=written)],
        }

    def route_after_apply(self, state: ForgeState) -> str:
        return "respond" if state.get("verification") else "verify"

    def verify(self, state: ForgeState) -> dict[str, Any]:
        result = self.runner.run(Path(self.settings.workspace_path))
        return {
            "verification": result.model_dump(mode="json"),
            "trace": [
                trace_event(
                    "verify",
                    "Godot Headless 验证完成",
                    status=result.status,
                    errors=result.errors,
                    duration_seconds=result.duration_seconds,
                )
            ],
        }

    def route_after_verify(self, state: ForgeState) -> str:
        if state["verification"]["status"] in {"passed", "skipped"}:
            return "respond"
        if state.get("repair_count", 0) < self.settings.max_repairs:
            return "repair"
        return "respond"

    def repair(self, state: ForgeState) -> dict[str, Any]:
        changes = [FileChange.model_validate(item) for item in state["file_changes"]]
        verification = state.get("verification") or {}
        errors = verification.get("errors", [])
        if not errors:
            errors = [state.get("review", {}).get("feedback", "静态审查失败")]
        bundle = self.model.repair(
            GameSpec.model_validate(state["spec"]),
            changes,
            errors,
            [DocumentHit.model_validate(hit) for hit in state.get("knowledge", [])],
        )
        if bundle.replace_all:
            merged_changes = bundle.changes
        else:
            patches = {change.path: change for change in bundle.changes}
            merged_changes = []
            applied_paths = set()
            for change in changes:
                if change.path not in patches:
                    merged_changes.append(change)
                elif change.path not in applied_paths:
                    merged_changes.append(patches[change.path])
                    applied_paths.add(change.path)
            original_paths = {change.path for change in changes}
            merged_changes.extend(
                change for path, change in patches.items() if path not in original_paths
            )
        plan = DevelopmentPlan.model_validate(state["plan"])
        ownership = {
            path: module.name for module in plan.modules for path in module.owned_paths
        }
        merged_changes = [
            change.model_copy(
                update={"owner": ownership.get(change.path, change.owner or "repair")}
            )
            for change in merged_changes
        ]
        repair_count = state.get("repair_count", 0) + 1
        return {
            "file_changes": [change.model_dump(mode="json") for change in merged_changes],
            "repair_count": repair_count,
            "verification": None,
            "trace": [
                trace_event(
                    "repair",
                    "根据审查或运行日志生成修复版本",
                    repair=repair_count,
                    errors=errors,
                    patched_files=[change.path for change in bundle.changes],
                )
            ],
        }

    def respond(self, state: ForgeState) -> dict[str, Any]:
        if state.get("final_response"):
            response = state["final_response"]
        elif not state.get("review", {}).get("accepted", False):
            response = f"工程未通过静态审查，已停止自动修改：{state['review']['feedback']}"
        else:
            spec = GameSpec.model_validate(state["spec"])
            verification = state.get("verification", {})
            status = verification.get("status", "skipped")
            response = (
                f"已生成 Godot 4 原型《{spec.title}》。\n"
                f"工程目录：{self.workspace.root}\n"
                f"文件：{', '.join(state.get('applied_files', []))}"
            )
            if status == "passed":
                response += "\nGodot Headless 冒烟测试通过，发现 SMOKE_TEST_OK 标记。"
            elif status == "failed":
                errors = verification.get("errors", [])
                response += f"\n自动验证仍未通过，已保留工程和日志供人工排查：{errors}"
            else:
                response += "\n静态审查通过；当前环境未找到 Godot，因此未执行引擎验证。"
        return {
            "final_response": response,
            "trace": [trace_event("respond", "游戏原型开发流程结束")],
        }
