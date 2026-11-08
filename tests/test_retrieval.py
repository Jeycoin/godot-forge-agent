from godot_forge.config import Settings
from godot_forge.retrieval import GodotKnowledgeBase


def test_retrieval_finds_headless_validation_protocol() -> None:
    knowledge = GodotKnowledgeBase.from_path(Settings().knowledge_path)

    hits = knowledge.search("Godot 4 headless smoke test 自动验证", top_k=1)

    assert len(hits) == 1
    assert hits[0].document_id == "GODOT-HEADLESS-4"
