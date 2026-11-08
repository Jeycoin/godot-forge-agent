import os
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from godot_forge.config import Settings
from godot_forge.graph import build_graph
from godot_forge.models import GameModel, build_model
from godot_forge.retrieval import GodotKnowledgeBase
from godot_forge.schemas import RunResponse
from godot_forge.workspace import GodotRunner, WorkspaceManager


class GodotForgeRuntime:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        checkpointer: BaseCheckpointSaver | None = None,
        model: GameModel | None = None,
        runner: GodotRunner | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self._connection: sqlite3.Connection | None = None
        if checkpointer is None:
            database_path = Path(self.settings.database_path)
            database_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(database_path, check_same_thread=False)
            self._connection.execute("PRAGMA journal_mode=WAL")
            checkpointer = SqliteSaver(self._connection)

        if self.settings.langsmith_tracing:
            os.environ["LANGSMITH_TRACING"] = "true"
        self.model = model or build_model(self.settings)
        self.knowledge_base = GodotKnowledgeBase.from_path(self.settings.knowledge_path)
        self.workspace = WorkspaceManager(Path(self.settings.workspace_path))
        self.runner = runner or GodotRunner(
            self.settings.godot_path,
            self.settings.engine_timeout_seconds,
        )
        self.graph = build_graph(
            self.settings,
            self.model,
            self.knowledge_base,
            self.workspace,
            self.runner,
            checkpointer,
        )

    def run(self, request: str, thread_id: str | None = None) -> RunResponse:
        thread_id = thread_id or uuid4().hex
        result = self.graph.invoke(
            {"run_id": thread_id, "request": request},
            config=self._config(thread_id),
        )
        return self._to_response(thread_id, result)

    def resume(self, thread_id: str, approved: bool, note: str = "") -> RunResponse:
        result = self.graph.invoke(
            Command(resume={"approved": approved, "note": note}),
            config=self._config(thread_id),
        )
        return self._to_response(thread_id, result)

    def get_state(self, thread_id: str) -> dict[str, Any]:
        snapshot = self.graph.get_state(self._config(thread_id))
        values = snapshot.values
        return {
            "thread_id": thread_id,
            "next": list(snapshot.next),
            "spec": values.get("spec"),
            "plan": values.get("plan"),
            "review": values.get("review"),
            "repair_count": values.get("repair_count", 0),
            "verification": values.get("verification"),
            "generated_files": values.get("applied_files", []),
            "final_response": values.get("final_response"),
            "trace": values.get("trace", []),
        }

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()

    def __enter__(self) -> "GodotForgeRuntime":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": 60}

    @staticmethod
    def _to_response(thread_id: str, result: dict[str, Any]) -> RunResponse:
        interrupts = result.get("__interrupt__", [])
        if interrupts:
            approval = getattr(interrupts[0], "value", interrupts[0])
            return RunResponse(
                thread_id=thread_id,
                status="awaiting_approval",
                approval=approval,
                trace=result.get("trace", []),
            )
        return RunResponse(
            thread_id=thread_id,
            status="completed",
            response=result.get("final_response"),
            verification=result.get("verification"),
            generated_files=result.get("applied_files", []),
            trace=result.get("trace", []),
        )
