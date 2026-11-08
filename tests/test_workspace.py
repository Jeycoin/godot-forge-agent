import pytest

from godot_forge.schemas import FileChange
from godot_forge.workspace import WorkspaceError, WorkspaceManager, validate_relative_path


def test_workspace_rejects_path_traversal() -> None:
    with pytest.raises(WorkspaceError):
        validate_relative_path("../outside.gd")
    with pytest.raises(WorkspaceError):
        validate_relative_path("scripts/../../outside.gd")
    with pytest.raises(WorkspaceError):
        validate_relative_path("scripts/../project.godot")


def test_failed_batch_restores_original_files(tmp_path) -> None:
    workspace = WorkspaceManager(tmp_path / "game")
    original = FileChange(path="scripts/player.gd", content="original\n", purpose="原文件")
    workspace.apply([original])

    with pytest.raises(WorkspaceError):
        workspace.apply(
            [
                FileChange(path="scripts/player.gd", content="changed\n", purpose="修改"),
                FileChange(path="../outside.gd", content="unsafe\n", purpose="越界"),
            ]
        )

    assert (tmp_path / "game" / "scripts" / "player.gd").read_text(
        encoding="utf-8"
    ) == "original\n"
    assert not (tmp_path / "outside.gd").exists()
