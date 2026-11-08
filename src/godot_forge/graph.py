from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from godot_forge.config import Settings
from godot_forge.models import GameModel
from godot_forge.nodes import ForgeNodes
from godot_forge.retrieval import GodotKnowledgeBase
from godot_forge.state import ForgeState
from godot_forge.workspace import GodotRunner, WorkspaceManager


def build_graph(
    settings: Settings,
    model: GameModel,
    knowledge_base: GodotKnowledgeBase,
    workspace: WorkspaceManager,
    runner: GodotRunner,
    checkpointer: BaseCheckpointSaver,
):
    nodes = ForgeNodes(settings, model, knowledge_base, workspace, runner)
    model_retry = RetryPolicy(max_attempts=3)

    builder = StateGraph(ForgeState)
    builder.add_node("design", nodes.design, retry_policy=model_retry)
    builder.add_node("plan", nodes.plan, retry_policy=model_retry)
    builder.add_node("retrieve", nodes.retrieve)
    builder.add_node("develop", nodes.develop, retry_policy=model_retry)
    builder.add_node("integrate", nodes.integrate)
    builder.add_node("review", nodes.review)
    builder.add_node("approval", nodes.approval)
    builder.add_node("apply", nodes.apply)
    builder.add_node("verify", nodes.verify)
    builder.add_node("repair", nodes.repair, retry_policy=model_retry)
    builder.add_node("respond", nodes.respond)

    builder.add_edge(START, "design")
    builder.add_edge("design", "plan")
    builder.add_edge("plan", "retrieve")
    builder.add_conditional_edges("retrieve", nodes.fan_out)
    builder.add_edge("develop", "integrate")
    builder.add_edge("integrate", "review")
    builder.add_conditional_edges(
        "review",
        nodes.route_after_review,
        {
            "repair": "repair",
            "approval": "approval",
            "apply": "apply",
            "respond": "respond",
        },
    )
    builder.add_conditional_edges(
        "approval",
        nodes.route_after_approval,
        {"apply": "apply", "respond": "respond"},
    )
    builder.add_conditional_edges(
        "apply",
        nodes.route_after_apply,
        {"verify": "verify", "respond": "respond"},
    )
    builder.add_conditional_edges(
        "verify",
        nodes.route_after_verify,
        {"repair": "repair", "respond": "respond"},
    )
    builder.add_edge("repair", "review")
    builder.add_edge("respond", END)
    return builder.compile(checkpointer=checkpointer)
