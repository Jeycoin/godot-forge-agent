import os

import pytest
from langgraph.checkpoint.memory import MemorySaver

from godot_forge.config import PROJECT_ROOT, Settings
from godot_forge.runtime import GodotForgeRuntime

RUN_LIVE = os.getenv("GODOT_FORGE_RUN_LIVE_TESTS") == "1"


@pytest.mark.skipif(not RUN_LIVE, reason="Set GODOT_FORGE_RUN_LIVE_TESTS=1 for live API tests")
def test_deepseek_generates_and_verifies_real_godot_project(tmp_path) -> None:
    settings = Settings(
        model_provider="deepseek",
        workspace_path=tmp_path / "deepseek-game",
        database_path=tmp_path / "deepseek.db",
        godot_path=PROJECT_ROOT / "tools" / "Godot.exe",
        model_timeout_seconds=180,
        engine_timeout_seconds=30,
        max_repairs=2,
    )
    if settings.api_key is None:
        pytest.skip("GODOT_FORGE_API_KEY is required")

    with GodotForgeRuntime(settings, checkpointer=MemorySaver()) as runtime:
        first = runtime.run(
            "为 Game Jam 生成一个 2D 俯视角生存原型：WASD 移动，敌人追踪，"
            "玩家生命值、生存分数和 HUD，使用简单几何图形，不依赖外部素材。",
            "deepseek-live",
        )
        assert first.status == "awaiting_approval", first.model_dump(mode="json")
        response = runtime.resume("deepseek-live", True, "DeepSeek 全链路测试")
        state = runtime.get_state("deepseek-live")

    assert response.status == "completed"
    assert response.verification is not None
    assert response.verification["status"] == "passed", response.verification["output"]
    assert response.generated_files
    assert state["repair_count"] <= settings.max_repairs
