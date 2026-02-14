"""
Efficiency analytics for AeroTech Agentic Hub.

Bu modül, tamamlanan bakım iş paketleri üzerinden metrikler hesaplar:
- Ortalama tamamlama süresi
- İlk geçiş başarı oranı
- Saatlik throughput
- Aylık tamamlanan iş paketleri
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import json


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "app" / "data" if (BASE_DIR / "app" / "data").exists() else BASE_DIR / "data"
COMPLETED_PATH = DATA_DIR / "completed_work_packages.json"


@dataclass
class CompletedWorkPackage:
    id: str
    work_package_id: str
    sprint_id: Optional[str]
    started_at: str          # ISO datetime string
    completed_at: str        # ISO datetime string
    first_pass_success: bool
    rework_count: int = 0
    planned_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None
    assigned_personnel_count: Optional[int] = None
    criticality: Optional[str] = None  # örn. "high", "medium", "low"

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "CompletedWorkPackage":
        return CompletedWorkPackage(
            id=data["id"],
            work_package_id=data.get("work_package_id", ""),
            sprint_id=data.get("sprint_id"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            first_pass_success=bool(data.get("first_pass_success", False)),
            rework_count=int(data.get("rework_count", 0)),
            planned_minutes=data.get("planned_minutes"),
            actual_minutes=data.get("actual_minutes"),
            assigned_personnel_count=data.get("assigned_personnel_count"),
            criticality=data.get("criticality"),
        )


def _ensure_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not COMPLETED_PATH.exists():
        COMPLETED_PATH.write_text("[]", encoding="utf-8")


def list_completed() -> List[CompletedWorkPackage]:
    _ensure_file()
    raw = json.loads(COMPLETED_PATH.read_text(encoding="utf-8"))
    return [CompletedWorkPackage.from_dict(item) for item in raw]


def add_completed(item: CompletedWorkPackage) -> None:
    items = list_completed()
    items.append(item)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COMPLETED_PATH.write_text(
        json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def compute_efficiency_summary() -> Dict[str, Any]:
    items = list_completed()
    if not items:
        return {
            "avg_completion_days": None,
            "first_pass_rate": None,
            "throughput_per_day": None,
            "total_completed": 0,
            "monthly_completed": [],
        }

    def _parse(dt: str) -> datetime:
        return datetime.fromisoformat(dt)

    durations_days: List[float] = []
    fps_count = 0
    first_started: Optional[datetime] = None
    last_completed: Optional[datetime] = None
    monthly: Dict[str, int] = {}

    for i in items:
        try:
            s = _parse(i.started_at)
            c = _parse(i.completed_at)
        except Exception:
            continue

        dur = (c - s).total_seconds() / 86400.0
        durations_days.append(dur)

        if i.first_pass_success:
            fps_count += 1

        if first_started is None or s < first_started:
            first_started = s
        if last_completed is None or c > last_completed:
            last_completed = c

        ym = c.strftime("%Y-%m")
        monthly[ym] = monthly.get(ym, 0) + 1

    avg_completion_days = sum(durations_days) / len(durations_days) if durations_days else None
    first_pass_rate = fps_count / len(items) if items else None

    if first_started and last_completed and last_completed > first_started:
        total_days = (last_completed - first_started).total_seconds() / 86400.0
        throughput_per_day = len(items) / total_days if total_days > 0 else None
    else:
        throughput_per_day = None

    monthly_list = [
        {"month": k, "completed": v}
        for k, v in sorted(monthly.items())
    ]

    return {
        "avg_completion_days": avg_completion_days,
        "first_pass_rate": first_pass_rate,
        "throughput_per_day": throughput_per_day,
        "total_completed": len(items),
        "monthly_completed": monthly_list,
    }

