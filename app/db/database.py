"""
SQLite veritabanı bağlantısı ve şema.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "aerotech.db"


def get_db_path() -> Path:
    return DB_PATH


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Veritabanı tablolarını oluştur."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,              -- lead, technician, viewer vb.
                email TEXT,
                phone TEXT,
                device_type TEXT,                -- desktop, mobile
                personnel_id TEXT                -- opsiyonel: personnel tablosuna bağlamak için
            );

            CREATE TABLE IF NOT EXISTS personnel (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                ratings TEXT NOT NULL,
                specializations TEXT NOT NULL,
                shift TEXT NOT NULL,
                availability TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tools (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                location TEXT NOT NULL,
                calibration_due TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'available'
            );

            CREATE TABLE IF NOT EXISTS parts (
                id TEXT PRIMARY KEY,
                part_no TEXT NOT NULL,
                name TEXT NOT NULL,
                ata_chapter TEXT NOT NULL,
                stock_level INTEGER NOT NULL DEFAULT 0,
                location TEXT NOT NULL,
                lead_time_days INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS work_packages (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                aircraft TEXT NOT NULL,
                ata TEXT NOT NULL,
                status TEXT NOT NULL,
                assigned_to TEXT,
                due_date TEXT NOT NULL
            );
        """)


def seed_from_json() -> None:
    """JSON dosyalarından veri yükle (tablolar boşsa)."""
    import json

    data_dir = BASE_DIR / "app" / "data"

    with get_connection() as conn:
        # Users
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            path = data_dir / "users.json"
            if path.exists():
                for u in json.loads(path.read_text(encoding="utf-8")):
                    conn.execute(
                        "INSERT OR REPLACE INTO users (id, name, role, email, phone, device_type, personnel_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            u["id"],
                            u["name"],
                            u.get("role", "technician"),
                            u.get("email"),
                            u.get("phone"),
                            u.get("device_type"),
                            u.get("personnel_id"),
                        ),
                    )

        if conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0] == 0:
            path = data_dir / "personnel.json"
            if path.exists():
                for p in json.loads(path.read_text(encoding="utf-8")):
                    conn.execute(
                        "INSERT OR REPLACE INTO personnel (id, name, role, ratings, specializations, shift, availability) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (p["id"], p["name"], p["role"], json.dumps(p["ratings"]), json.dumps(p["specializations"]), p["shift"], p["availability"]),
                    )

        try:
            conn.execute("ALTER TABLE tools ADD COLUMN status TEXT NOT NULL DEFAULT 'available'")
        except Exception:
            pass
        if conn.execute("SELECT COUNT(*) FROM tools").fetchone()[0] == 0:
            path = data_dir / "tools.json"
            if path.exists():
                for t in json.loads(path.read_text(encoding="utf-8")):
                    status = t.get("status", "available")
                    conn.execute(
                        "INSERT OR REPLACE INTO tools (id, name, category, location, calibration_due, status) VALUES (?, ?, ?, ?, ?, ?)",
                        (t["id"], t["name"], t["category"], t["location"], t["calibration_due"], status),
                    )

        if conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0] == 0:
            path = data_dir / "parts.json"
            if path.exists():
                for p in json.loads(path.read_text(encoding="utf-8")):
                    conn.execute(
                        "INSERT OR REPLACE INTO parts (id, part_no, name, ata_chapter, stock_level, location, lead_time_days) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (p["id"], p["part_no"], p["name"], p["ata_chapter"], p["stock_level"], p["location"], p["lead_time_days"]),
                    )

        if conn.execute("SELECT COUNT(*) FROM work_packages").fetchone()[0] == 0:
            path = data_dir / "work_packages.json"
            if path.exists():
                for w in json.loads(path.read_text(encoding="utf-8")):
                    conn.execute(
                        "INSERT OR REPLACE INTO work_packages (id, title, aircraft, ata, status, assigned_to, due_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (w["id"], w["title"], w["aircraft"], w["ata"], w["status"], w.get("assigned_to"), w["due_date"]),
                    )
