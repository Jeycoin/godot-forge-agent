import pytest
from langgraph.checkpoint.memory import MemorySaver

from godot_forge.config import PROJECT_ROOT, Settings
from godot_forge.runtime import GodotForgeRuntime

GODOT_EXECUTABLE = PROJECT_ROOT / "tools" / "Godot.exe"


@pytest.mark.skipif(not GODOT_EXECUTABLE.is_file(), reason="Godot portable engine not installed")
def test_generated_project_passes_real_godot_headless(tmp_path) -> None:
    settings = Settings(
        workspace_path=tmp_path / "real-game",
        database_path=tmp_path / "real.db",
        godot_path=GODOT_EXECUTABLE,
        engine_timeout_seconds=30,
    )
    with GodotForgeRuntime(settings, checkpointer=MemorySaver()) as runtime:
        runtime.run("生成一个可通过真实引擎验证的 2D 生存原型", "real-engine")
        response = runtime.resume("real-engine", True)

    assert response.verification is not None
    assert response.verification["status"] == "passed", response.verification["output"]
    assert response.verification["exit_code"] == 0
    assert "SMOKE_TEST_OK" in response.verification["output"]
    stages = response.verification["stages"]
    assert [stage["name"] for stage in stages] == ["import", "smoke_test"]
    assert all(stage["status"] == "passed" for stage in stages)
