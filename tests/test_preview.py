from godot_forge.schemas import FileChange
from godot_forge.workspace import WorkspaceManager


def test_preview_shows_unified_diff_for_existing_file(tmp_path) -> None:
    workspace = WorkspaceManager(tmp_path / "game")
    workspace.apply(
        [FileChange(path="scripts/player.gd", content="old line\n", purpose="旧版本")]
    )

    preview = workspace.preview(
        [FileChange(path="scripts/player.gd", content="new line\n", purpose="新版本")]
    )[0]

    assert preview["action"] == "update"
    assert "-old line" in preview["diff"]
    assert "+new line" in preview["diff"]
    assert len(preview["sha256"]) == 64
