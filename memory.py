"""
记忆系统 —— SQLite 实现

包含：
- 对话历史（chat_history）
- 猫猫个性化记忆（cat_memories）
- 用户画像（user_profile）

查看记忆的方式：
1. 命令行查看 SQLite：
   sqlite3 meowdev.db "SELECT * FROM cat_memories WHERE cat_id='arch';"
   sqlite3 meowdev.db "SELECT * FROM user_profile;"
   sqlite3 meowdev.db "SELECT * FROM chat_history ORDER BY timestamp DESC LIMIT 20;"

2. Python 查看：
   import sqlite3
   conn = sqlite3.connect('meowdev.db')
   for row in conn.execute("SELECT * FROM cat_memories"): print(row)
"""

import sqlite3
import time
import uuid
from datetime import datetime
from typing import Optional

from config import BASE_DIR

DB_PATH = BASE_DIR / "meowdev.db"
MAX_RECENT_MESSAGES = 30


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_conn()

    # 对话历史表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            timestamp   REAL NOT NULL,
            session_id  TEXT DEFAULT 'default'
        )
    """)

    # 猫猫记忆表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cat_memories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            cat_id      TEXT NOT NULL,
            memory      TEXT NOT NULL,
            importance  INTEGER DEFAULT 1,
            timestamp   REAL NOT NULL
        )
    """)

    # 用户画像表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_profile (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            updated_at  REAL NOT NULL
        )
    """)

    # 猫猫使用统计表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cat_usage (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            cat_id                  TEXT NOT NULL,
            input_tokens            INTEGER DEFAULT 0,
            output_tokens           INTEGER DEFAULT 0,
            cache_read_tokens       INTEGER DEFAULT 0,
            cache_creation_tokens   INTEGER DEFAULT 0,
            cost_usd                REAL DEFAULT 0,
            hour_slot               TEXT,
            date_slot               TEXT,
            timestamp               REAL NOT NULL
        )
    """)

    # 会话表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id            TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            created_at    REAL NOT NULL,
            updated_at    REAL NOT NULL,
            message_count INTEGER DEFAULT 0,
            is_archived   INTEGER DEFAULT 0
        )
    """)

    # 创建索引
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_history_session
        ON chat_history(session_id, timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_cat_memories_cat
        ON cat_memories(cat_id, importance DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_cat_usage_cat
        ON cat_usage(cat_id, timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_cat_usage_hour
        ON cat_usage(hour_slot)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_cat_usage_date
        ON cat_usage(date_slot)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_updated
        ON sessions(updated_at DESC)
    """)

    # 迁移旧的 "meowdev" 数据到新系统
    _migrate_legacy_session(conn)

    # 清理幽灵 session：没有用户消息的 session（由 on_chat_start 误创建的）
    phantom_ids = [r["id"] for r in conn.execute("""
        SELECT s.id FROM sessions s
        WHERE s.message_count <= 1
        AND s.id NOT IN (
            SELECT DISTINCT session_id FROM chat_history
            WHERE role IN ('用户', 'user')
        )
    """).fetchall()]
    if phantom_ids:
        ph = ",".join("?" * len(phantom_ids))
        conn.execute(f"DELETE FROM chat_history WHERE session_id IN ({ph})", phantom_ids)
        conn.execute(f"DELETE FROM sessions WHERE id IN ({ph})", phantom_ids)
        conn.commit()
        print(f"[MeowDev] 清理了 {len(phantom_ids)} 个空会话")

    conn.close()


def _migrate_legacy_session(conn):
    """迁移旧的 "meowdev" 数据到新系统"""
    # 检查是否存在旧的 meowdev 数据
    row = conn.execute(
        "SELECT COUNT(*) as count FROM chat_history WHERE session_id = 'meowdev'"
    ).fetchone()

    if row and row["count"] > 0:
        # 检查是否已有对应的 session 记录
        existing = conn.execute(
            "SELECT id FROM sessions WHERE id = 'meowdev'"
        ).fetchone()

        if not existing:
            # 获取最早消息的时间作为创建时间
            first_msg = conn.execute(
                "SELECT MIN(timestamp) as ts FROM chat_history WHERE session_id = 'meowdev'"
            ).fetchone()
            created_at = first_msg["ts"] if first_msg and first_msg["ts"] else time.time()

            # 获取最新消息的时间作为更新时间
            last_msg = conn.execute(
                "SELECT MAX(timestamp) as ts FROM chat_history WHERE session_id = 'meowdev'"
            ).fetchone()
            updated_at = last_msg["ts"] if last_msg and last_msg["ts"] else time.time()

            # 创建 session 记录
            conn.execute("""
                INSERT INTO sessions (id, name, created_at, updated_at, message_count)
                VALUES (?, ?, ?, ?, ?)
            """, ("meowdev", "历史对话", created_at, updated_at, row["count"]))
            conn.commit()  # 必须提交事务！
            print(f"[MeowDev] 已迁移 {row['count']} 条历史消息到会话 'meowdev'")


# ═══════════════════════════════════════════════════════════════════════
# 会话管理
# ═══════════════════════════════════════════════════════════════════════

def create_session(name: str = "新对话", session_id: str = None) -> str:
    """创建新会话，返回 session_id

    Args:
        name: 会话名称
        session_id: 可选的会话ID，如果不提供则自动生成
    """
    if not session_id:
        session_id = str(uuid.uuid4())[:8]  # 使用短 UUID
    now = time.time()
    conn = _get_conn()
    conn.execute(
        "INSERT INTO sessions (id, name, created_at, updated_at, message_count) VALUES (?, ?, ?, ?, 0)",
        (session_id, name, now, now),
    )
    conn.commit()
    conn.close()
    return session_id


def get_session(session_id: str) -> Optional[dict]:
    """获取会话元数据"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, name, created_at, updated_at, message_count, is_archived FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    conn.close()
    if row:
        return {
            "id": row["id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "message_count": row["message_count"],
            "is_archived": row["is_archived"],
        }
    return None


def update_session(session_id: str, name: str = None):
    """更新会话名称"""
    conn = _get_conn()
    if name:
        conn.execute(
            "UPDATE sessions SET name = ?, updated_at = ? WHERE id = ?",
            (name, time.time(), session_id),
        )
        conn.commit()
    conn.close()


def list_sessions(limit: int = 50) -> list[dict]:
    """获取会话列表，按更新时间倒序"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, name, created_at, updated_at, message_count, is_archived "
        "FROM sessions WHERE is_archived = 0 ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "message_count": r["message_count"],
            "is_archived": r["is_archived"],
        }
        for r in rows
    ]


def delete_session(session_id: str):
    """删除会话及其消息"""
    conn = _get_conn()
    conn.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 对话历史
# ═══════════════════════════════════════════════════════════════════════

def add_message(role: str, content: str, session_id: str = "default"):
    conn = _get_conn()
    now = time.time()
    conn.execute(
        "INSERT INTO chat_history (role, content, timestamp, session_id) VALUES (?, ?, ?, ?)",
        (role, content, now, session_id),
    )
    # 更新会话的 updated_at 和 message_count
    conn.execute(
        "UPDATE sessions SET updated_at = ?, message_count = message_count + 1 WHERE id = ?",
        (now, session_id),
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
    return [{"role": r["role"], "content": r["content"], "timestamp": r["timestamp"]} for r in reversed(rows)]


def get_messages_paginated(session_id: str = "default",
                           offset: int = 0,
                           limit: int = 20) -> list[dict]:
    """分页获取历史消息（按时间倒序，返回时正序显示）"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT role, content, timestamp FROM chat_history "
        "WHERE session_id = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        (session_id, limit, offset),
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"], "timestamp": r["timestamp"]} for r in reversed(rows)]


def get_message_count(session_id: str = "default") -> int:
    """获取消息总数"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as count FROM chat_history WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    conn.close()
    return row["count"] if row else 0


def format_chat_context(session_id: str = "default") -> str:
    """格式化对话历史，给 LLM 用"""
    messages = get_recent_messages(session_id)
    if not messages:
        return ""
    return "\n".join(f"{m['role']}：{m['content']}" for m in messages)


def clear_session(session_id: str = "default"):
    """清空会话历史"""
    conn = _get_conn()
    conn.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 猫猫记忆
# ═══════════════════════════════════════════════════════════════════════

def add_cat_memory(cat_id: str, memory: str, importance: int = 1):
    """添加猫猫记忆

    Args:
        cat_id: 猫猫ID (arch/stack/pixel)
        memory: 记忆内容
        importance: 重要性 (1=普通, 2=重要, 3=非常重要)
    """
    conn = _get_conn()
    conn.execute(
        "INSERT INTO cat_memories (cat_id, memory, importance, timestamp) VALUES (?, ?, ?, ?)",
        (cat_id, memory, importance, time.time()),
    )
    conn.commit()
    conn.close()


def get_cat_memories(cat_id: str, limit: int = 20) -> list[dict]:
    """获取猫猫的记忆列表"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT memory, importance, timestamp FROM cat_memories "
        "WHERE cat_id = ? ORDER BY importance DESC, timestamp DESC LIMIT ?",
        (cat_id, limit),
    ).fetchall()
    conn.close()
    return [{"memory": r["memory"], "importance": r["importance"]} for r in rows]


def format_cat_memory_context(cat_id: str, limit: int = 10) -> str:
    """格式化猫猫记忆，给 LLM 用"""
    memories = get_cat_memories(cat_id, limit)
    if not memories:
        return ""

    lines = []
    for m in memories:
        prefix = "★" if m["importance"] >= 2 else "•"
        lines.append(f"{prefix} {m['memory']}")

    return "\n".join(lines)


def clear_cat_memories(cat_id: Optional[str] = None):
    """清空猫猫记忆，不传 cat_id 则清空所有"""
    conn = _get_conn()
    if cat_id:
        conn.execute("DELETE FROM cat_memories WHERE cat_id = ?", (cat_id,))
    else:
        conn.execute("DELETE FROM cat_memories")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 用户画像
# ═══════════════════════════════════════════════════════════════════════

def set_user_info(key: str, value: str):
    """设置用户信息

    Args:
        key: 信息类型 (如 name, preference, project 等)
        value: 信息内容
    """
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO user_profile (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, time.time()),
    )
    conn.commit()
    conn.close()


def get_user_info(key: str) -> Optional[str]:
    """获取用户信息"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT value FROM user_profile WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else None


def get_all_user_info() -> dict:
    """获取所有用户信息"""
    conn = _get_conn()
    rows = conn.execute("SELECT key, value FROM user_profile").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def format_user_profile_context() -> str:
    """格式化用户画像，给 LLM 用"""
    profile = get_all_user_info()
    if not profile:
        return ""

    lines = ["用户画像"]
    for key, value in profile.items():
        lines.append(f"- {key}: {value}")

    return "\n".join(lines)


def clear_user_profile():
    """清空用户画像"""
    conn = _get_conn()
    conn.execute("DELETE FROM user_profile")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════
# 猫猫使用统计
# ═══════════════════════════════════════════════════════════════════════

def add_cat_usage(cat_id: str, usage_data: dict):
    """记录猫猫使用统计

    Args:
        cat_id: 猫猫ID (arch/stack/pixel)
        usage_data: 包含 token 和费用信息的字典
    """
    now = time.time()
    dt = datetime.fromtimestamp(now)
    hour_slot = dt.strftime("%Y-%m-%d-%H")
    date_slot = dt.strftime("%Y-%m-%d")

    conn = _get_conn()
    conn.execute("""
        INSERT INTO cat_usage
        (cat_id, input_tokens, output_tokens,
         cache_read_tokens, cache_creation_tokens, cost_usd,
         hour_slot, date_slot, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cat_id,
        usage_data.get("inputTokens", 0),
        usage_data.get("outputTokens", 0),
        usage_data.get("cacheReadInputTokens", 0),
        usage_data.get("cacheCreationInputTokens", 0),
        usage_data.get("costUSD", 0),
        hour_slot, date_slot, now
    ))
    conn.commit()
    conn.close()


def get_cat_stats(cat_id: str, range_type: str = "day") -> dict:
    """获取单只猫猫的统计

    Args:
        cat_id: 猫猫ID (arch/stack/pixel)
        range_type: 时间范围 (day/week/month)
    """
    conn = _get_conn()

    # 根据时间范围计算时间戳
    now = time.time()
    if range_type == "day":
        start_ts = now - 24 * 60 * 60
    elif range_type == "week":
        start_ts = now - 7 * 24 * 60 * 60
    else:  # month
        start_ts = now - 30 * 24 * 60 * 60

    row = conn.execute("""
        SELECT
            COALESCE(SUM(input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as cache_read_tokens,
            COALESCE(SUM(cache_creation_tokens), 0) as cache_creation_tokens,
            COALESCE(SUM(cost_usd), 0) as cost_usd,
            COUNT(*) as call_count
        FROM cat_usage WHERE cat_id = ? AND timestamp >= ?
    """, (cat_id, start_ts)).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_all_cats_stats(range_type: str = "day") -> dict:
    """获取所有猫猫的统计

    Args:
        range_type: 时间范围 (day/week/month)
    """
    return {cat_id: get_cat_stats(cat_id, range_type) for cat_id in ["arch", "stack", "pixel"]}


def get_trend(range_type: str = "day") -> list:
    """获取统计趋势

    Args:
        range_type: 时间范围
            - day: 返回当天按小时 (最多24个时间点)
            - week: 返回7天按天
            - month: 返回30天按天

    Returns:
        list of dict: 每个时间点的各猫猫统计数据
    """
    conn = _get_conn()
    now = time.time()

    if range_type == "day":
        # 当天按小时
        date_str = datetime.now().strftime("%Y-%m-%d")
        rows = conn.execute("""
            SELECT hour_slot, cat_id,
                   SUM(input_tokens) as input_tokens,
                   SUM(output_tokens) as output_tokens,
                   SUM(cost_usd) as cost_usd
            FROM cat_usage
            WHERE date_slot = ?
            GROUP BY hour_slot, cat_id
            ORDER BY hour_slot
        """, (date_str,)).fetchall()
    elif range_type == "week":
        # 7天按天
        start_ts = now - 7 * 24 * 60 * 60
        rows = conn.execute("""
            SELECT date_slot as time_slot, cat_id,
                   SUM(input_tokens) as input_tokens,
                   SUM(output_tokens) as output_tokens,
                   SUM(cost_usd) as cost_usd
            FROM cat_usage
            WHERE timestamp >= ?
            GROUP BY date_slot, cat_id
            ORDER BY date_slot
        """, (start_ts,)).fetchall()
    else:  # month
        # 30天按天
        start_ts = now - 30 * 24 * 60 * 60
        rows = conn.execute("""
            SELECT date_slot as time_slot, cat_id,
                   SUM(input_tokens) as input_tokens,
                   SUM(output_tokens) as output_tokens,
                   SUM(cost_usd) as cost_usd
            FROM cat_usage
            WHERE timestamp >= ?
            GROUP BY date_slot, cat_id
            ORDER BY date_slot
        """, (start_ts,)).fetchall()

    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════
# 调试工具
# ═══════════════════════════════════════════════════════════════════════

def print_all_memories():
    """打印所有记忆（调试用）"""
    conn = _get_conn()

    print("\n=== 猫猫记忆 ===")
    rows = conn.execute(
        "SELECT cat_id, memory, importance FROM cat_memories ORDER BY cat_id, importance DESC"
    ).fetchall()
    if rows:
        for r in rows:
            print(f"  [{r['cat_id']}] ({r['importance']}) {r['memory']}")
    else:
        print("  (空)")

    print("\n=== 用户画像 ===")
    rows = conn.execute("SELECT key, value FROM user_profile").fetchall()
    if rows:
        for r in rows:
            print(f"  {r['key']}: {r['value']}")
    else:
        print("  (空)")

    print("\n=== 最近对话 ===")
    rows = conn.execute(
        "SELECT role, content FROM chat_history ORDER BY timestamp DESC LIMIT 10"
    ).fetchall()
    if rows:
        for r in reversed(rows):
            content = r['content'][:50] + "..." if len(r['content']) > 50 else r['content']
            print(f"  {r['role']}: {content}")
    else:
        print("  (空)")

    conn.close()


# 初始化数据库
init_db()


if __name__ == "__main__":
    # 测试
    print_all_memories()
