"""
任务看板 — SQLite 持久化，热重载不丢任务
"""

import re
import sqlite3
import time
from dataclasses import dataclass, field

from config import BASE_DIR

DB_PATH = BASE_DIR / "meowdev.db"


@dataclass
class Task:
    id: str
    title: str
    status: str = "pending"   # pending / doing / done
    owner: str = ""
    created_at: float = field(default_factory=time.time)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_table():
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            owner TEXT DEFAULT '',
            created_at REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_ensure_table()


class TaskBoard:
    """共享任务看板，SQLite 持久化。热重载后自动恢复。"""

    def __init__(self):
        self.tasks: dict[str, Task] = {}
        self._load()

    def _load(self):
        conn = _conn()
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at"
        ).fetchall()
        for r in rows:
            self.tasks[r["id"]] = Task(
                id=r["id"], title=r["title"], status=r["status"],
                owner=r["owner"] or "", created_at=r["created_at"],
            )
        conn.close()

    def _next_id(self) -> str:
        if self.tasks:
            nums = [int(tid.split("-")[1]) for tid in self.tasks]
            return f"T-{max(nums) + 1:03d}"
        return "T-001"

    def _save(self, task: Task):
        conn = _conn()
        conn.execute(
            "UPDATE tasks SET status=?, owner=? WHERE id=?",
            (task.status, task.owner, task.id),
        )
        conn.commit()
        conn.close()

    def add(self, title: str) -> Task:
        tid = self._next_id()
        t = Task(id=tid, title=title)
        self.tasks[tid] = t
        conn = _conn()
        conn.execute(
            "INSERT OR REPLACE INTO tasks (id, title, status, owner, created_at) "
            "VALUES (?,?,?,?,?)",
            (t.id, t.title, t.status, t.owner, t.created_at),
        )
        conn.commit()
        conn.close()
        return t

    def claim(self, task_id: str, owner: str) -> bool:
        task = self.tasks.get(task_id)
        if task and task.status == "pending":
            task.status = "doing"
            task.owner = owner
            self._save(task)
            return True
        return False

    def complete(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if task and task.status == "doing":
            task.status = "done"
            self._save(task)
            return True
        return False

    def remove(self, task_id: str) -> bool:
        if task_id in self.tasks:
            del self.tasks[task_id]
            conn = _conn()
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            conn.close()
            return True
        return False

    def reassign(self, task_id: str, new_owner: str) -> bool:
        task = self.tasks.get(task_id)
        if task and task.status in ("pending", "doing"):
            task.owner = new_owner
            task.status = "doing"
            self._save(task)
            return True
        return False

    def has_pending_work(self) -> bool:
        return any(t.status in ("pending", "doing") for t in self.tasks.values())

    def clear_done(self):
        done_ids = [tid for tid, t in self.tasks.items() if t.status == "done"]
        for tid in done_ids:
            del self.tasks[tid]
        if done_ids:
            conn = _conn()
            conn.executemany(
                "DELETE FROM tasks WHERE id = ?",
                [(tid,) for tid in done_ids],
            )
            conn.commit()
            conn.close()

    def format_status(self) -> str:
        if not self.tasks:
            return ""
        icons = {"pending": "⏳", "doing": "🔄", "done": "✅"}
        lines = []
        for t in self.tasks.values():
            owner_tag = f" → {t.owner}" if t.owner else ""
            lines.append(f"{icons.get(t.status, '❓')} {t.id}: {t.title}{owner_tag}")
        return "\n".join(lines)


# ── 解析函数 ─────────────────────────────────────────────

def parse_task_actions(text: str) -> list[dict]:
    """解析猫猫回复中的 [新任务：...] [认领：T-xxx] [完成：T-xxx] [空闲]"""
    actions: list[dict] = []
    for m in re.finditer(r'\[新任务[：:]\s*(.+?)\]', text):
        actions.append({"type": "create", "title": m.group(1).strip()})
    for m in re.finditer(r'\[认领[：:]\s*(T-\d+)\]', text):
        actions.append({"type": "claim", "task_id": m.group(1)})
    for m in re.finditer(r'\[完成[：:]\s*(T-\d+)\]', text):
        actions.append({"type": "complete", "task_id": m.group(1)})
    if re.search(r'\[空闲\]', text):
        actions.append({"type": "idle"})
    return actions


def parse_user_task_cmd(text: str) -> dict | None:
    """解析用户的任务管理指令。"""
    m = re.match(r'(?:加|新建|添加|创建)任务[：:]\s*(.+)', text)
    if m:
        return {"type": "create", "title": m.group(1).strip()}
    m = re.match(r'(?:删除|取消|移除)\s*(T-\d+)', text)
    if m:
        return {"type": "remove", "task_id": m.group(1)}
    m = re.search(r'(?:把\s*)?(T-\d+)\s*(?:给|指派给|分配给)\s*(\S+)', text)
    if m:
        return {"type": "reassign", "task_id": m.group(1), "owner": m.group(2)}
    return None


def strip_task_markers(text: str) -> str:
    """移除任务指令标记"""
    text = re.sub(r'\s*\[新任务[：:].+?\]', '', text)
    text = re.sub(r'\s*\[认领[：:]\s*T-\d+\]', '', text)
    text = re.sub(r'\s*\[完成[：:]\s*T-\d+\]', '', text)
    text = re.sub(r'\s*\[空闲\]', '', text)
    return text.strip()
