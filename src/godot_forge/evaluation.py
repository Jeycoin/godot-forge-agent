import json
import tempfile
import time
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from godot_forge.config import PROJECT_ROOT, Settings
from godot_forge.runtime import GodotForgeRuntime

REQUIRED_FILES = {
    "project.godot",
    "README.md",
    "scenes/main.tscn",
    "scripts/main.gd",
    "scripts/player.gd",
    "scripts/enemy.gd",
    "scripts/hud.gd",
}


def evaluate(settings: Settings, cases_path: Path | None = None) -> dict[str, Any]:
    path = cases_path or PROJECT_ROOT / "data" / "eval_cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    results = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="godot-forge-eval-") as directory:
        for index, case in enumerate(cases):
            case_settings = settings.model_copy(
                update={"workspace_path": Path(directory) / f"case-{index}"}
            )
            with GodotForgeRuntime(case_settings, checkpointer=MemorySaver()) as runtime:
                thread_id = f"eval-{index}"
                response = runtime.run(case["request"], thread_id)
                approval_correct = response.status == "awaiting_approval"
                if approval_correct:
                    response = runtime.resume(thread_id, True, "自动化评估审批")
                generated_files = set(response.generated_files)
                files_complete = generated_files == REQUIRED_FILES
                verification = response.verification or {}
                engine_verified = verification.get("status") == "passed"
                build_completed = response.status == "completed" and files_complete
                results.append(
                    {
                        "case_id": case["case_id"],
                        "build_completed": build_completed,
                        "approval_correct": approval_correct,
                        "files_complete": files_complete,
                        "engine_verified": engine_verified,
                        "verification_status": verification.get("status"),
                        "repair_count": runtime.get_state(thread_id)["repair_count"],
                    }
                )

    total = len(results)

    def rate(field: str) -> float:
        return sum(bool(item[field]) for item in results) / total if total else 0

    return {
        "summary": {
            "cases": total,
            "build_completion_rate": rate("build_completed"),
            "approval_gate_accuracy": rate("approval_correct"),
            "file_completeness_rate": rate("files_complete"),
            "engine_verification_rate": rate("engine_verified"),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        },
        "cases": results,
    }
