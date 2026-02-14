"""
Sprint planning & backlog helpers.

work_packages (SQLite) ile birleşik – Sprint Planning, Scrum Dashboard ve İş Paketleri
aynı veri kaynağını kullanır.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import List, Literal, Optional
import uuid

from app.db import crud


BacklogType = Literal["product", "sprint"]
BacklogStatus = Literal["todo", "in_progress", "done"]

# work_packages status <-> backlog status
WP_TO_BACKLOG = {"pending": "todo", "in_progress": "in_progress", "approved": "done"}
BACKLOG_TO_WP = {"todo": "pending", "in_progress": "in_progress", "done": "approved"}


@dataclass
class BacklogItem:
    id: str
    type: BacklogType
    title: str
    description: str
    status: BacklogStatus = "todo"
    sprint: Optional[str] = None
    priority: Optional[int] = None
    estimate_hours: Optional[float] = None
    owner: Optional[str] = None

    @staticmethod
    def from_dict(data: dict) -> "BacklogItem":
        return BacklogItem(
            id=data.get("id", str(uuid.uuid4())),
            type=data.get("type", "product"),
            title=data.get("title", ""),
            description=data.get("description", ""),
            status=data.get("status", "todo"),
            sprint=data.get("sprint"),
            priority=data.get("priority"),
            estimate_hours=data.get("estimate_hours"),
            owner=data.get("owner"),
        )

    @staticmethod
    def from_work_package(wp: dict) -> "BacklogItem":
        status = wp.get("status", "pending")
        return BacklogItem(
            id=wp.get("id", ""),
            type="sprint",
            title=wp.get("title", ""),
            description=wp.get("ata", "") or "",
            status=WP_TO_BACKLOG.get(status, "todo"),
            sprint=wp.get("aircraft"),
            priority=None,
            estimate_hours=None,
            owner=wp.get("assigned_to"),
        )


def _wp_from_item(item: BacklogItem) -> dict:
    due = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    return {
        "id": item.id or str(uuid.uuid4()),
        "title": item.title,
        "aircraft": item.sprint or "A320",
        "ata": item.description or "27",
        "status": BACKLOG_TO_WP.get(item.status, "pending"),
        "assigned_to": item.owner,
        "due_date": due,
    }


def add_items(new_items: List[BacklogItem]) -> List[dict]:
    """Yeni öğeleri work_packages'e ekler."""
    created = []
    for item in new_items:
        if not item.id:
            item.id = str(uuid.uuid4())
        wp_data = _wp_from_item(item)
        created.append(crud.create_work_package(wp_data))
    return created


def update_item_status(item_id: str, status: BacklogStatus) -> Optional[dict]:
    """work_packages'te durum günceller."""
    wp_status = BACKLOG_TO_WP.get(status, "pending")
    return crud.update_work_package(item_id, {"status": wp_status})


def _normalize_token(s: str) -> str:
    """Türkçe ekleri kısmen temizler: controlünü -> control."""
    s = s.lower().strip()
    for suffix in ("ünü", "ı", "ü", "u", "i", "ı", "yi", "yi", "de", "dan", "den"):
        if len(s) > len(suffix) + 2 and s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    return s


def find_item_by_title(title_keywords: str) -> Optional[BacklogItem]:
    """
    Başlıkta anahtar kelime(ler) geçen ilk item'ı döner.
    Kullanıcı 'aileron hinge bracket control' veya 'aileron hinge bracket controlünü' dediğinde eşleşir.
    """
    if not title_keywords or not title_keywords.strip():
        return None
    kw = title_keywords.strip().lower()
    tokens = [t for t in kw.split() if len(t) > 1]
    rows = crud.list_work_packages()
    for r in rows:
        t = (r.get("title") or "").lower()
        if kw in t:
            return BacklogItem.from_work_package(r)
        if tokens and all(
            pt in t or _normalize_token(pt) in t
            for pt in tokens
        ):
            return BacklogItem.from_work_package(r)
    return None


def list_items(
    type: Optional[BacklogType] = None,
    sprint: Optional[str] = None,
    status: Optional[BacklogStatus] = None,
) -> List[BacklogItem]:
    """work_packages'ten filtreleyerek listeler."""
    wp_status = BACKLOG_TO_WP.get(status) if status else None
    rows = crud.list_work_packages(status_filter=wp_status)
    items = [BacklogItem.from_work_package(r) for r in rows]
    if sprint:
        items = [i for i in items if i.sprint == sprint]
    if type:
        items = [i for i in items if i.type == type]
    return items
