import difflib
import hashlib
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import Any

from godot_forge.config import PROJECT_ROOT
from godot_forge.schemas import (
    FileChange,
    ValidationStageResult,
    VerificationResult,
)


class WorkspaceError(Exception):
    pass


def validate_relative_path(raw_path: str) -> str:
    if "\\" in raw_path:
        raise WorkspaceError("文件路径必须使用 POSIX 格式")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise WorkspaceError(f"非法工作区路径: {raw_path}")
    normalized = path.as_posix()
    allowed = (
        normalized in {"project.godot", "README.md"}
        or (normalized.startswith("scripts/") and normalized.endswith(".gd"))
        or (normalized.startswith("scenes/") and normalized.endswith(".tscn"))
    )
    if not allowed:
        raise WorkspaceError(f"文件类型或目录不在允许列表中: {normalized}")
    return normalized


class WorkspaceManager:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def preview(self, changes: list[FileChange]) -> list[dict[str, Any]]:
        previews = []
        for change in changes:
            relative_path = validate_relative_path(change.path)
            target = self._target(relative_path)
            previous = target.read_text(encoding="utf-8") if target.exists() else ""
            diff = "\n".join(
                difflib.unified_diff(
                    previous.splitlines(),
                    change.content.splitlines(),
                    fromfile=f"a/{relative_path}",
                    tofile=f"b/{relative_path}",
                    lineterm="",
                )
            )
            if len(diff) > 6000:
                diff = diff[:6000] + "\n... diff truncated ..."
            previews.append(
                {
                    "path": relative_path,
                    "owner": change.owner,
                    "action": "update" if target.exists() else "create",
                    "sha256": hashlib.sha256(change.content.encode("utf-8")).hexdigest(),
                    "diff": diff,
                }
            )
        return previews

    def apply(self, changes: list[FileChange]) -> list[str]:
        self.root.mkdir(parents=True, exist_ok=True)
        backups: dict[str, str | None] = {}
        written = []
        try:
            for change in changes:
                relative_path = validate_relative_path(change.path)
                target = self._target(relative_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                backups[relative_path] = (
                    target.read_text(encoding="utf-8") if target.exists() else None
                )
                temporary = target.with_suffix(target.suffix + ".tmp")
                temporary.write_text(change.content, encoding="utf-8", newline="\n")
                temporary.replace(target)
                written.append(relative_path)
        except (OSError, UnicodeError, WorkspaceError) as exc:
            self._restore(backups)
            raise WorkspaceError(f"写入失败，已恢复原工程: {exc}") from exc
        return written

    def _target(self, relative_path: str) -> Path:
        target = (self.root / relative_path).resolve()
        if not target.is_relative_to(self.root):
            raise WorkspaceError("目标文件逃逸出工作区")
        return target

    def _restore(self, backups: dict[str, str | None]) -> None:
        for relative_path, content in backups.items():
            target = self.root / relative_path
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.write_text(content, encoding="utf-8", newline="\n")


class GodotRunner:
    def __init__(self, executable: Path | None = None, timeout_seconds: int = 20) -> None:
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def _find_executable(self) -> str | None:
        candidates = [self.executable, PROJECT_ROOT / "tools" / "Godot.exe"]
        for candidate in candidates:
            if candidate and candidate.is_file():
                return str(candidate)
        return shutil.which("godot") or shutil.which("godot4")

    def run(self, workspace: Path) -> VerificationResult:
        executable = self._find_executable()
        if executable is None:
            return VerificationResult(
                status="skipped",
                output="未找到 Godot 4；已完成静态审查，但未执行引擎验证。",
                errors=["Godot executable not found"],
            )

        root = str(workspace.resolve())
        stages = [
            self._run_stage(
                "import",
                [executable, "--headless", "--editor", "--path", root, "--quit"],
            )
        ]
        if stages[0].status == "passed":
            stages.append(
                self._run_stage(
                    "smoke_test",
                    [
                        executable,
                        "--headless",
                        "--path",
                        root,
                        "--quit-after",
                        "120",
                        "--",
                        "--smoke-test",
                    ],
                    required_marker="SMOKE_TEST_OK",
                )
            )

        output = "\n".join(
            f"[{stage.name}]\n{stage.output}" for stage in stages if stage.output
        )
        errors = [error for stage in stages for error in stage.errors]
        final_stage = stages[-1]
        passed = len(stages) == 2 and all(stage.status == "passed" for stage in stages)
        return VerificationResult(
            status="passed" if passed else "failed",
            command=final_stage.command,
            exit_code=final_stage.exit_code,
            output=output[-16000:],
            errors=errors[-30:],
            duration_seconds=round(sum(stage.duration_seconds for stage in stages), 3),
            stages=stages,
        )

    def _run_stage(
        self,
        name: str,
        command: list[str],
        required_marker: str | None = None,
    ) -> ValidationStageResult:
        started = time.perf_counter()
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = self._as_text(exc.stdout) + self._as_text(exc.stderr)
            return ValidationStageResult(
                name=name,
                status="failed",
                command=command,
                output=output[-12000:],
                errors=[f"{name} 验证超过 {self.timeout_seconds} 秒"],
                duration_seconds=round(time.perf_counter() - started, 3),
            )

        output = "\n".join(part for part in (process.stdout, process.stderr) if part)
        error_lines = [
            line
            for line in output.splitlines()
            if any(marker in line for marker in ("ERROR", "Error", "SMOKE_TEST_FAIL"))
        ]
        passed = process.returncode == 0 and not error_lines
        if required_marker and required_marker not in output:
            passed = False
            error_lines.append(f"未发现验证成功标记: {required_marker}")
        if process.returncode != 0 and not error_lines:
            error_lines.append(f"Godot 退出码 {process.returncode}")
        return ValidationStageResult(
            name=name,
            status="passed" if passed else "failed",
            command=command,
            exit_code=process.returncode,
            output=output[-12000:],
            errors=error_lines[-20:],
            duration_seconds=round(time.perf_counter() - started, 3),
        )

    @staticmethod
    def _as_text(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value
