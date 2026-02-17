"""
记忆系统 —— 让猫猫们记住你

三层记忆：
1. 对话历史（chat_history）—— 群聊中所有人的发言记录
2. 猫猫记忆（cat_memories）—— 每只猫猫对用户的个性化记忆
3. 用户画像（user_profile）—— 跨猫猫共享的用户信息
"""

import sqlite3
import time
from typing import Optional

from config import BASE_DIR

DB_PATH = BASE_DIR / "meowdev.db"

MAX_RECENT_MESSAGES = 30
MAX_CAT_MEMORIES = 50


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            timestamp   REAL NOT NULL,
            session_id  TEXT DEFAULT 'default'
        );

        CREATE TABLE IF NOT EXISTS cat_memories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            cat_id      TEXT NOT NULL,
            memory      TEXT NOT NULL,
            importance  INTEGER DEFAULT 1,
            timestamp   REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_profile (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            updated_at  REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_history_session ON chat_history(session_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_memories_cat ON cat_memories(cat_id, importance DESC);
    """)
    conn.close()


# ── 对话历史 ─────────────────────────────────────────────

def add_message(role: str, content: str, session_id: str = "default"):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO chat_history (role, content, timestamp, session_id) VALUES (?, ?, ?, ?)",
        (role, content, time.time(), session_id),
    )
    conn.commit()
    conn.close()


def get_recent_messages(session_id: str = "default",
                        limit: int = MAX_RECENT_MESSAGES) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT role, content, timestamp FROM chat_history "
        "WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# ── 猫猫记忆 ─────────────────────────────────────────────

def add_cat_memory(cat_id: str, memory: str, importance: int = 1):
    conn = _get_conn()
    existing = conn.execute(
        "SELECT id FROM cat_memories WHERE cat_id = ? AND memory = ?",
        (cat_id, memory),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE cat_memories SET importance = MIN(importance + 1, 5), timestamp = ? WHERE id = ?",
            (time.time(), existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO cat_memories (cat_id, memory, importance, timestamp) VALUES (?, ?, ?, ?)",
            (cat_id, memory, importance, time.time()),
        )
    conn.execute(
        "DELETE FROM cat_memories WHERE cat_id = ? AND id NOT IN "
        "(SELECT id FROM cat_memories WHERE cat_id = ? ORDER BY importance DESC, timestamp DESC LIMIT ?)",
        (cat_id, cat_id, MAX_CAT_MEMORIES),
    )
    conn.commit()
    conn.close()


def get_cat_memories(cat_id: str, limit: int = 10) -> list[str]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT memory FROM cat_memories WHERE cat_id = ? ORDER BY importance DESC, timestamp DESC LIMIT ?",
        (cat_id, limit),
    ).fetchall()
    conn.close()
    return [r["memory"] for r in rows]


# ── 用户画像 ─────────────────────────────────────────────

def set_user_info(key: str, value: str):
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO user_profile (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, time.time()),
    )
    conn.commit()
    conn.close()


def get_user_info(key: str) -> Optional[str]:
    conn = _get_conn()
    row = conn.execute("SELECT value FROM user_profile WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


def get_all_user_info() -> dict[str, str]:
    conn = _get_conn()
    rows = conn.execute("SELECT key, value FROM user_profile").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# ── 格式化（给 LLM 用）─────────────────────────────────

def format_chat_context(session_id: str = "default") -> str:
    messages = get_recent_messages(session_id)
    if not messages:
        return ""
    return "\n".join(f"{m['role']}：{m['content']}" for m in messages)


def format_cat_memory_context(cat_id: str) -> str:
    memories = get_cat_memories(cat_id)
    if not memories:
        return ""
    return "你记得关于用户的这些事：\n" + "\n".join(f"- {m}" for m in memories)


def format_user_profile_context() -> str:
    info = get_all_user_info()
    if not info:
        return ""
    return "用户信息：\n" + "\n".join(f"- {k}: {v}" for k, v in info.items())


init_db()
