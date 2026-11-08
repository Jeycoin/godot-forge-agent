import json
import logging
from pathlib import Path

import jieba
from pydantic import BaseModel
from rank_bm25 import BM25Okapi

from godot_forge.schemas import DocumentHit

jieba.setLogLevel(logging.WARNING)


class GodotDocument(BaseModel):
    document_id: str
    title: str
    topic: str
    content: str


def tokenize(text: str) -> list[str]:
    return [token.strip().lower() for token in jieba.lcut(text) if token.strip()]


class GodotKnowledgeBase:
    def __init__(self, documents: list[GodotDocument]) -> None:
        self.documents = documents
        self._bm25 = BM25Okapi([tokenize(document.content) for document in documents])

    @classmethod
    def from_path(cls, path: Path) -> "GodotKnowledgeBase":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls([GodotDocument.model_validate(item) for item in raw])

    def search(self, query: str, top_k: int = 3) -> list[DocumentHit]:
        scores = self._bm25.get_scores(tokenize(query))
        indices = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
        hits = []
        for index in indices[:top_k]:
            if scores[index] <= 0:
                continue
            document = self.documents[index]
            hits.append(
                DocumentHit(
                    document_id=document.document_id,
                    title=document.title,
                    topic=document.topic,
                    content=document.content,
                    score=round(float(scores[index]), 4),
                )
            )
        return hits
