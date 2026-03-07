"""
persona_db.py — SQLite-backed storage for persona avatar data.

Manages four tables:
  personas            — named persona records
  persona_models      — VRM model file attached to a persona
  persona_animations  — animation clips attached to a persona
  persona_voices      — designed voice (speaker_id) attached to a persona

All file paths are stored relative to the project root.
"""

import sqlite3
import uuid
import os
from typing import Optional

DB_PATH = "data/personas.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if they don't exist. Call once on server startup."""
    os.makedirs("data", exist_ok=True)
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS personas (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS persona_models (
                id          TEXT PRIMARY KEY,
                persona_id  TEXT NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
                filename    TEXT NOT NULL,
                filepath    TEXT NOT NULL,
                url         TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS persona_animations (
                id          TEXT PRIMARY KEY,
                persona_id  TEXT NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                filename    TEXT NOT NULL,
                filepath    TEXT NOT NULL,
                url         TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS persona_voices (
                id          TEXT PRIMARY KEY,
                persona_id  TEXT NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
                speaker_id  TEXT NOT NULL,
                name        TEXT NOT NULL,
                gender      TEXT DEFAULT '',
                language    TEXT DEFAULT 'English',
                instruct    TEXT DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now'))
            );
        """)


# ── Personas ────────────────────────────────────────────────────────────────

def create_persona(name: str, description: str = "") -> dict:
    pid = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO personas (id, name, description) VALUES (?, ?, ?)",
            (pid, name, description),
        )
    return get_persona(pid)


def list_personas() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM personas ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_persona(persona_id: str) -> Optional[dict]:
    """Return full persona record including model, animations, and voice."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM personas WHERE id = ?", (persona_id,)
        ).fetchone()
        if row is None:
            return None
        persona = dict(row)

        model_row = conn.execute(
            "SELECT * FROM persona_models WHERE persona_id = ? ORDER BY created_at DESC LIMIT 1",
            (persona_id,),
        ).fetchone()
        persona["model"] = dict(model_row) if model_row else None

        anim_rows = conn.execute(
            "SELECT * FROM persona_animations WHERE persona_id = ? ORDER BY created_at ASC",
            (persona_id,),
        ).fetchall()
        persona["animations"] = [dict(r) for r in anim_rows]

        voice_row = conn.execute(
            "SELECT * FROM persona_voices WHERE persona_id = ? ORDER BY created_at DESC LIMIT 1",
            (persona_id,),
        ).fetchone()
        persona["voice"] = dict(voice_row) if voice_row else None

    return persona


def delete_persona(persona_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
    return cur.rowcount > 0


# ── Models ───────────────────────────────────────────────────────────────────

def attach_model(persona_id: str, filename: str, filepath: str, url: str) -> dict:
    """Replace any existing model for this persona."""
    mid = str(uuid.uuid4())
    with _connect() as conn:
        # Remove previous model record (file stays on disk — caller handles cleanup if needed)
        conn.execute("DELETE FROM persona_models WHERE persona_id = ?", (persona_id,))
        conn.execute(
            "INSERT INTO persona_models (id, persona_id, filename, filepath, url) VALUES (?, ?, ?, ?, ?)",
            (mid, persona_id, filename, filepath, url),
        )
    with _connect() as conn:
        row = conn.execute("SELECT * FROM persona_models WHERE id = ?", (mid,)).fetchone()
    return dict(row)


# ── Animations ───────────────────────────────────────────────────────────────

def attach_animation(
    persona_id: str, name: str, filename: str, filepath: str, url: str
) -> dict:
    aid = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO persona_animations (id, persona_id, name, filename, filepath, url) VALUES (?, ?, ?, ?, ?, ?)",
            (aid, persona_id, name, filename, filepath, url),
        )
    with _connect() as conn:
        row = conn.execute("SELECT * FROM persona_animations WHERE id = ?", (aid,)).fetchone()
    return dict(row)


def delete_animation(animation_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM persona_animations WHERE id = ?", (animation_id,))
    return cur.rowcount > 0


# ── Voices ───────────────────────────────────────────────────────────────────

def upsert_voice(
    persona_id: str,
    speaker_id: str,
    name: str,
    gender: str = "",
    language: str = "English",
    instruct: str = "",
) -> dict:
    """Replace existing voice record for this persona."""
    vid = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute("DELETE FROM persona_voices WHERE persona_id = ?", (persona_id,))
        conn.execute(
            """INSERT INTO persona_voices
               (id, persona_id, speaker_id, name, gender, language, instruct)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (vid, persona_id, speaker_id, name, gender, language, instruct),
        )
    with _connect() as conn:
        row = conn.execute("SELECT * FROM persona_voices WHERE id = ?", (vid,)).fetchone()
    return dict(row)


def list_voices() -> list[dict]:
    """Return all designed voices across all personas."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM persona_voices ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]
