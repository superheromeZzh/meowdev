"""
任务看板 — 猫猫团队的共享任务列表

灵感来源：Claude Code Agent Teams 的共享 Task List。
猫猫们通过任务看板协调工作：创建 → 认领 → 执行 → 完成。
任务看板是猫猫们自主管理的，Python 层只做解析和状态更新。
"""

import re
import time
from dataclasses import dataclass, field
from typing import Optional

_counter = 0


@dataclass
class Task:
    id: str
    title: str
    status: str = "pending"   # pending / doing / done
    owner: str = ""
    created_at: float = field(default_factory=time.time)


class TaskBoard:
    """共享任务看板，猫猫通过回复中的指令操作。"""

    def __init__(self):
        self.tasks: dict[str, Task] = {}

    def add(self, title: str) -> Task:
        global _counter
        _counter += 1
        tid = f"T-{_counter:03d}"
        task = Task(id=tid, title=title)
        self.tasks[tid] = task
        return task

    def claim(self, task_id: str, owner: str) -> bool:
        task = self.tasks.get(task_id)
        if task and task.status == "pending":
            task.status = "doing"
            task.owner = owner
            return True
        return False

    def complete(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if task and task.status == "doing":
            task.status = "done"
            return True
        return False

    def remove(self, task_id: str) -> bool:
        if task_id in self.tasks:
            del self.tasks[task_id]
            return True
        return False

    def reassign(self, task_id: str, new_owner: str) -> bool:
        task = self.tasks.get(task_id)
        if task and task.status in ("pending", "doing"):
            task.owner = new_owner
            task.status = "doing"
            return True
        return False

    def has_pending_work(self) -> bool:
        return any(t.status in ("pending", "doing") for t in self.tasks.values())

    def format_status(self) -> str:
        if not self.tasks:
            return ""
        icons = {"pending": "⏳", "doing": "🔄", "done": "✅"}
        lines = []
        for t in self.tasks.values():
            owner_tag = f" → {t.owner}" if t.owner else ""
            lines.append(f"{icons.get(t.status, '❓')} {t.id}: {t.title}{owner_tag}")
        return "\n".join(lines)


# ── 从猫猫回复中解析任务指令 ─────────────────────────────

def parse_task_actions(text: str) -> list[dict]:
    """解析回复里的 [新任务：...] [认领：T-xxx] [完成：T-xxx] [空闲]"""
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
    """解析用户的任务管理指令，返回操作 dict 或 None（非任务指令）。

    支持：
      加任务：xxx / 新建任务：xxx / 添加任务：xxx
      删除 T-001 / 取消 T-001 / 移除 T-001
      T-001 给 Stack喵 / 把 T-001 指派给 Arch酱
    """
    # 创建
    m = re.match(r'(?:加|新建|添加|创建)任务[：:]\s*(.+)', text)
    if m:
        return {"type": "create", "title": m.group(1).strip()}

    # 删除
    m = re.match(r'(?:删除|取消|移除)\s*(T-\d+)', text)
    if m:
        return {"type": "remove", "task_id": m.group(1)}

    # 指派
    m = re.search(r'(?:把\s*)?(T-\d+)\s*(?:给|指派给|分配给)\s*(\S+)', text)
    if m:
        return {"type": "reassign", "task_id": m.group(1), "owner": m.group(2)}

    return None


def strip_task_markers(text: str) -> str:
    """从显示文本中移除任务指令标记"""
    text = re.sub(r'\s*\[新任务[：:].+?\]', '', text)
    text = re.sub(r'\s*\[认领[：:]\s*T-\d+\]', '', text)
    text = re.sub(r'\s*\[完成[：:]\s*T-\d+\]', '', text)
    text = re.sub(r'\s*\[空闲\]', '', text)
    return text.strip()
