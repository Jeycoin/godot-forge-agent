import operator
from typing import Annotated, Any, TypedDict


class ForgeState(TypedDict, total=False):
    run_id: str
    request: str
    spec: dict[str, Any]
    plan: dict[str, Any]
    knowledge: list[dict[str, Any]]
    specialist: str
    artifacts: Annotated[list[dict[str, Any]], operator.add]
    file_changes: list[dict[str, Any]]
    review: dict[str, Any]
    approval_granted: bool
    applied_files: list[str]
    verification: dict[str, Any]
    repair_count: int
    final_response: str
    trace: Annotated[list[dict[str, Any]], operator.add]
