"""
Sprint yaşam döngüsü yönetimi – başlatma, bitirme.
"""

from pathlib import Path
from datetime import datetime, timedelta
import json
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "app" / "data"
SPRINT_FILE = DATA_DIR / "active_sprint.json"


def _load() -> dict[str, Any]:
    if not SPRINT_FILE.exists():
        return {}
    try:
        return json.loads(SPRINT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SPRINT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_sprint_state() -> dict[str, Any]:
    """Aktif sprint durumunu döner."""
    data = _load()
    if not data:
        return {
            "status": "none",
            "name": None,
            "goal": None,
            "started_at": None,
            "ended_at": None,
            "days_remaining": 0,
            "duration_days": 14,
        }
    # days_remaining hesapla (end_date ile bugün arasındaki gün sayısı)
    if data.get("status") == "active" and data.get("end_date"):
        try:
            end_str = data["end_date"].replace("Z", "")[:10]
            end_dt = datetime.fromisoformat(end_str).date()
            today = datetime.now().date()
            delta = (end_dt - today).days
            data["days_remaining"] = max(0, delta)
        except Exception:
            data["days_remaining"] = data.get("duration_days", 14)
    else:
        data["days_remaining"] = 0
    return data


def start_sprint(
    name: str | None = None,
    goal: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    duration_days: int = 14,
) -> dict[str, Any]:
    """Yeni sprint başlatır."""
    now = datetime.now()

    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "")[:10])
        except Exception:
            start_dt = now
    else:
        start_dt = now

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "")[:10])
        except Exception:
            end_dt = start_dt + timedelta(days=duration_days)
    else:
        end_dt = start_dt + timedelta(days=duration_days)

    if not name:
        name = f"Bakım Sprint {start_dt.strftime('%y-%m')}"

    data = {
        "id": f"sprint-{start_dt.strftime('%Y%m%d%H%M')}",
        "name": name,
        "goal": goal or "",
        "status": "active",
        "started_at": start_dt.isoformat(),
        "ended_at": None,
        "end_date": end_dt.isoformat(),
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "duration_days": max(1, (end_dt - start_dt).days),
    }
    _save(data)
    return get_sprint_state()


def end_sprint() -> dict[str, Any]:
    """Aktif sprinti bitirir."""
    data = _load()
    if not data or data.get("status") != "active":
        return get_sprint_state()
    now = datetime.now()
    data["status"] = "completed"
    data["ended_at"] = now.isoformat()
    _save(data)
    return get_sprint_state()
