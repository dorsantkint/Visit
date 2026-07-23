"""Cache SQLite des descriptions déjà générées : un même (poi, langue, durée) n'est
rédigé par le LLM qu'une seule fois, quel que soit le nombre de visites générées."""
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "cache.db"


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS descriptions (
            osm_id TEXT NOT NULL,
            language TEXT NOT NULL,
            duration_min REAL NOT NULL,
            text TEXT NOT NULL,
            PRIMARY KEY (osm_id, language, duration_min)
        )
        """
    )
    conn.commit()
    conn.close()


def get_cached(osm_id: str, language: str, duration_min: float) -> Optional[str]:
    init_db()  # idempotent (CREATE TABLE IF NOT EXISTS) : garantit que la table existe
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT text FROM descriptions WHERE osm_id = ? AND language = ? AND duration_min = ?",
        (osm_id, language, duration_min),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def save_cache(osm_id: str, language: str, duration_min: float, text: str) -> None:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO descriptions (osm_id, language, duration_min, text) VALUES (?, ?, ?, ?)",
        (osm_id, language, duration_min, text),
    )
    conn.commit()
    conn.close()
