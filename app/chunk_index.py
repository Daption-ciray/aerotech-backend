"""
Chunk index for FAA / AMT PDFs.

Embedding tabanlı RAG yerine, LLM tarafından özetlenmiş chunk'lar üzerinden
arama yapabilmek için kullanılır.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional
import json


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "app" / "data" if (BASE_DIR / "app" / "data").exists() else BASE_DIR / "data"
INDEX_PATH = DATA_DIR / "chunk_index.json"


@dataclass
class ChunkRecord:
    id: str
    source: str
    page: Optional[int]
    summary: str
    text: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ChunkRecord":
        return ChunkRecord(
            id=data["id"],
            source=data.get("source", ""),
            page=data.get("page"),
            summary=data.get("summary", ""),
            text=data.get("text", ""),
        )


def load_chunk_index() -> List[ChunkRecord]:
    if not INDEX_PATH.exists():
        return []
    raw = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    chunks = raw.get("chunks", raw)  # hem eski hem yeni formatı destekle
    return [ChunkRecord.from_dict(c) for c in chunks]


def save_chunk_index(chunks: List[ChunkRecord]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "chunks": [
            {
                "id": c.id,
                "source": c.source,
                "page": c.page,
                "summary": c.summary,
                "text": c.text,
            }
            for c in chunks
        ]
    }
    INDEX_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

