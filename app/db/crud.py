"""
CRUD işlemleri – Personnel, Tools, Parts, Work Packages.
"""

import json
from typing import Any
from .database import get_connection


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row else {}


# ---- Users ----


def list_users() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY id"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_user(id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (id,),
        ).fetchone()
        return _row_to_dict(row) if row else None


def create_user(data: dict[str, Any]) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, name, role, email, phone, device_type, personnel_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["id"],
                data["name"],
                data.get("role", "technician"),
                data.get("email"),
                data.get("phone"),
                data.get("device_type"),
                data.get("personnel_id"),
            ),
        )
    return get_user(data["id"]) or data


def update_user(id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE users SET
                name = COALESCE(?, name),
                role = COALESCE(?, role),
                email = COALESCE(?, email),
                phone = COALESCE(?, phone),
                device_type = COALESCE(?, device_type),
                personnel_id = COALESCE(?, personnel_id)
            WHERE id = ?
            """,
            (
                data.get("name"),
                data.get("role"),
                data.get("email"),
                data.get("phone"),
                data.get("device_type"),
                data.get("personnel_id"),
                id,
            ),
        )
    return get_user(id)


def delete_user(id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (id,))
        return cur.rowcount > 0


# ---- Personnel ----

def list_personnel() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM personnel ORDER BY id").fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "role": r["role"],
                "ratings": json.loads(r["ratings"]) if r["ratings"] else [],
                "specializations": json.loads(r["specializations"]) if r["specializations"] else [],
                "shift": r["shift"],
                "availability": r["availability"],
            }
            for r in rows
        ]


def get_personnel(id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM personnel WHERE id = ?", (id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "role": row["role"],
            "ratings": json.loads(row["ratings"]) if row["ratings"] else [],
            "specializations": json.loads(row["specializations"]) if row["specializations"] else [],
            "shift": row["shift"],
            "availability": row["availability"],
        }


def create_personnel(data: dict[str, Any]) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO personnel (id, name, role, ratings, specializations, shift, availability) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                data["id"],
                data["name"],
                data["role"],
                json.dumps(data.get("ratings", [])),
                json.dumps(data.get("specializations", [])),
                data.get("shift", "day"),
                data.get("availability", "available"),
            ),
        )
    return get_personnel(data["id"]) or data


def update_personnel(id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE personnel SET
                name = COALESCE(?, name),
                role = COALESCE(?, role),
                ratings = COALESCE(?, ratings),
                specializations = COALESCE(?, specializations),
                shift = COALESCE(?, shift),
                availability = COALESCE(?, availability)
            WHERE id = ?""",
            (
                data.get("name"),
                data.get("role"),
                json.dumps(data["ratings"]) if "ratings" in data else None,
                json.dumps(data["specializations"]) if "specializations" in data else None,
                data.get("shift"),
                data.get("availability"),
                id,
            ),
        )
    return get_personnel(id)


def delete_personnel(id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM personnel WHERE id = ?", (id,))
        return cur.rowcount > 0


# ---- Tools ----

def list_tools() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM tools ORDER BY id").fetchall()
        return [_row_to_dict(r) for r in rows]


def get_tool(id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tools WHERE id = ?", (id,)).fetchone()
        return _row_to_dict(row) if row else None


def create_tool(data: dict[str, Any]) -> dict[str, Any]:
    status = data.get("status", "available")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO tools (id, name, category, location, calibration_due, status) VALUES (?, ?, ?, ?, ?, ?)",
            (data["id"], data["name"], data["category"], data["location"], data["calibration_due"], status),
        )
    return get_tool(data["id"]) or data


def update_tool(id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE tools SET
                name = COALESCE(?, name),
                category = COALESCE(?, category),
                location = COALESCE(?, location),
                calibration_due = COALESCE(?, calibration_due),
                status = COALESCE(?, status)
            WHERE id = ?""",
            (data.get("name"), data.get("category"), data.get("location"), data.get("calibration_due"), data.get("status"), id),
        )
    return get_tool(id)


def delete_tool(id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM tools WHERE id = ?", (id,))
        return cur.rowcount > 0


# ---- Parts ----

def list_parts() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM parts ORDER BY id").fetchall()
        return [_row_to_dict(r) for r in rows]


def get_part(id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM parts WHERE id = ?", (id,)).fetchone()
        return _row_to_dict(row) if row else None


def create_part(data: dict[str, Any]) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO parts (id, part_no, name, ata_chapter, stock_level, location, lead_time_days) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                data["id"],
                data["part_no"],
                data["name"],
                data["ata_chapter"],
                data.get("stock_level", 0),
                data["location"],
                data["lead_time_days"],
            ),
        )
    return get_part(data["id"]) or data


def update_part(id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE parts SET
                part_no = COALESCE(?, part_no),
                name = COALESCE(?, name),
                ata_chapter = COALESCE(?, ata_chapter),
                stock_level = COALESCE(?, stock_level),
                location = COALESCE(?, location),
                lead_time_days = COALESCE(?, lead_time_days)
            WHERE id = ?""",
            (
                data.get("part_no"),
                data.get("name"),
                data.get("ata_chapter"),
                data.get("stock_level"),
                data.get("location"),
                data.get("lead_time_days"),
                id,
            ),
        )
    return get_part(id)


def delete_part(id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM parts WHERE id = ?", (id,))
        return cur.rowcount > 0


# ---- Work Packages ----

def list_work_packages(status_filter: str | None = None) -> list[dict[str, Any]]:
    """status_filter: pending, in_progress, approved (work_packages) veya todo, in_progress, done (sprint)"""
    with get_connection() as conn:
        if status_filter:
            status_map = {"todo": "pending", "done": "approved"}
            wp_status = status_map.get(status_filter, status_filter)
            rows = conn.execute("SELECT * FROM work_packages WHERE status = ? ORDER BY id", (wp_status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM work_packages ORDER BY id").fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "aircraft": r["aircraft"],
                "ata": r["ata"],
                "status": r["status"],
                "assigned_to": r["assigned_to"],
                "due_date": r["due_date"],
            }
            for r in rows
        ]


def get_work_package(id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM work_packages WHERE id = ?", (id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "aircraft": row["aircraft"],
            "ata": row["ata"],
            "status": row["status"],
            "assigned_to": row["assigned_to"],
            "due_date": row["due_date"],
        }


def create_work_package(data: dict[str, Any]) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO work_packages (id, title, aircraft, ata, status, assigned_to, due_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                data["id"],
                data["title"],
                data["aircraft"],
                data["ata"],
                data.get("status", "pending"),
                data.get("assigned_to"),
                data["due_date"],
            ),
        )
    return get_work_package(data["id"]) or data


def update_work_package(id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE work_packages SET
                title = COALESCE(?, title),
                aircraft = COALESCE(?, aircraft),
                ata = COALESCE(?, ata),
                status = COALESCE(?, status),
                assigned_to = ?,
                due_date = COALESCE(?, due_date)
            WHERE id = ?""",
            (
                data.get("title"),
                data.get("aircraft"),
                data.get("ata"),
                data.get("status"),
                data.get("assigned_to"),
                data.get("due_date"),
                id,
            ),
        )
    return get_work_package(id)


def delete_work_package(id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM work_packages WHERE id = ?", (id,))
        return cur.rowcount > 0
