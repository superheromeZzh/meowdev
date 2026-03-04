"""
Chainlit Data Layer 实现

将 Chainlit 的 Thread 概念映射到现有的 sessions 表，
复用 memory.py 中的数据库结构。
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List, Optional

from chainlit.data.base import BaseDataLayer
from chainlit.types import Feedback, PaginatedResponse, Pagination, ThreadDict, ThreadFilter

if TYPE_CHECKING:
    from chainlit.element import Element, ElementDict
    from chainlit.step import StepDict
    from chainlit.user import PersistedUser, User

from memory import (
    _get_conn,
    update_session as db_update_session,
    delete_session as db_delete_session,
)


async def cleanup_cat_processes(thread_id: str):
    """清理指定 thread 对应的所有猫猫进程"""
    # 延迟导入避免循环依赖
    from cats import ALL_CATS
    for cat in ALL_CATS:
        await cat.cleanup(thread_id)

_executor = ThreadPoolExecutor(max_workers=4)

DEFAULT_USER_ID = "default_user"
DEFAULT_USER_IDENTIFIER = "MeowDev User"

CAT_NAME_TO_ID = {
    "Arch酱": "arch",
    "Stack喵": "stack",
    "Pixel咪": "pixel",
    "arch": "arch",
    "stack": "stack",
    "pixel": "pixel",
}


class MeowDevDataLayer(BaseDataLayer):
    """
    MeowDev 自定义 Data Layer

    将 Chainlit 的 Thread 映射到 sessions 表，
    将 Step 映射到 chat_history 表。
    """

    def __init__(self):
        self._loop = None

    def _run_sync(self, func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(_executor, lambda: func(*args, **kwargs))

    # ═══════════════════════════════════════════════════════════════════════
    # 用户管理
    # ═══════════════════════════════════════════════════════════════════════

    async def get_user(self, identifier: str) -> Optional["PersistedUser"]:
        from chainlit.user import PersistedUser
        return PersistedUser(
            id=DEFAULT_USER_ID,
            identifier=identifier or DEFAULT_USER_IDENTIFIER,
            createdAt="2024-01-01T00:00:00+00:00",
        )

    async def create_user(self, user: "User") -> Optional["PersistedUser"]:
        return await self.get_user(user.identifier)

    # ═══════════════════════════════════════════════════════════════════════
    # Thread（会话）管理
    # ═══════════════════════════════════════════════════════════════════════

    async def get_thread(self, thread_id: str) -> Optional[ThreadDict]:
        def _get():
            conn = _get_conn()
            try:
                session = conn.execute(
                    "SELECT id, name, created_at, updated_at FROM sessions WHERE id = ?",
                    (thread_id,),
                ).fetchone()

                if not session:
                    return None

                rows = conn.execute(
                    "SELECT id, role, content, timestamp FROM chat_history "
                    "WHERE session_id = ? ORDER BY timestamp ASC",
                    (thread_id,),
                ).fetchall()

                steps = []
                for row in rows:
                    created_at = datetime.fromtimestamp(row["timestamp"], timezone.utc).isoformat()
                    role = row["role"]

                    if role in ("用户", "user"):
                        msg_type = "user_message"
                        author = "user"
                    elif role == "system":
                        msg_type = "system_message"
                        author = "system"
                    else:
                        msg_type = "assistant_message"
                        author = CAT_NAME_TO_ID.get(role, role)

                    metadata = {}
                    avatar_name = CAT_NAME_TO_ID.get(role)
                    if avatar_name:
                        metadata["avatarName"] = avatar_name

                    steps.append({
                        "id": str(row["id"]),
                        "threadId": thread_id,
                        "name": author,
                        "type": msg_type,
                        "output": row["content"],
                        "input": "",
                        "createdAt": created_at,
                        "start": created_at,
                        "end": created_at,
                        "parentId": None,
                        "metadata": metadata,
                        "streaming": False,
                        "waitForAnswer": False,
                        "isError": False,
                        "generation": None,
                        "showInput": None,
                        "defaultOpen": None,
                        "language": None,
                        "command": None,
                        "tags": None,
                        "feedback": None,
                    })

                return {
                    "id": session["id"],
                    "createdAt": datetime.fromtimestamp(session["created_at"], timezone.utc).isoformat(),
                    "name": session["name"] or "对话",
                    "userId": DEFAULT_USER_ID,
                    "userIdentifier": DEFAULT_USER_IDENTIFIER,
                    "tags": [],
                    "metadata": {},
                    "steps": steps,
                    "elements": [],
                }
            finally:
                conn.close()

        return await self._run_sync(_get)

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ):
        def _update():
            if name:
                db_update_session(thread_id, name=name)

        await self._run_sync(_update)

    async def delete_thread(self, thread_id: str):
        # 先清理对应的猫猫进程
        await cleanup_cat_processes(thread_id)
        # 再删除数据库记录
        await self._run_sync(db_delete_session, thread_id)
        print(f"[MeowDev] 删除 thread {thread_id}，已清理对应进程")

    async def list_threads(
        self, pagination: Pagination, filters: ThreadFilter
    ) -> PaginatedResponse[ThreadDict]:
        def _list():
            limit = pagination.first or 20
            cursor = pagination.cursor

            conn = _get_conn()
            try:
                if cursor:
                    try:
                        cursor_ts = float(cursor)
                    except (ValueError, TypeError):
                        cursor_ts = 0
                    rows = conn.execute(
                        "SELECT id, name, created_at, updated_at, message_count, is_archived "
                        "FROM sessions WHERE is_archived = 0 AND message_count > 0 AND updated_at < ? "
                        "ORDER BY updated_at DESC LIMIT ?",
                        (cursor_ts, limit + 1),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, name, created_at, updated_at, message_count, is_archived "
                        "FROM sessions WHERE is_archived = 0 AND message_count > 0 "
                        "ORDER BY updated_at DESC LIMIT ?",
                        (limit + 1,),
                    ).fetchall()

                has_next = len(rows) > limit
                if has_next:
                    rows = rows[:limit]

                threads = []
                end_cursor = None

                for row in rows:
                    end_cursor = str(row["updated_at"])
                    threads.append({
                        "id": row["id"],
                        "createdAt": datetime.fromtimestamp(row["created_at"], timezone.utc).isoformat(),
                        "name": row["name"] or "对话",
                        "userId": DEFAULT_USER_ID,
                        "userIdentifier": DEFAULT_USER_IDENTIFIER,
                        "tags": [],
                        "metadata": {"message_count": row["message_count"]},
                        "steps": [],
                        "elements": [],
                    })

                return PaginatedResponse(
                    pageInfo={
                        "hasNextPage": has_next,
                        "startCursor": None,
                        "endCursor": end_cursor if has_next else None,
                    },
                    data=threads,
                )
            finally:
                conn.close()

        return await self._run_sync(_list)

    async def get_thread_author(self, thread_id: str) -> str:
        return DEFAULT_USER_IDENTIFIER

    # ═══════════════════════════════════════════════════════════════════════
    # Step（消息）管理
    # ═══════════════════════════════════════════════════════════════════════

    async def create_step(self, step_dict: "StepDict"):
        pass

    async def update_step(self, step_dict: "StepDict"):
        pass

    async def delete_step(self, step_id: str):
        def _delete():
            conn = _get_conn()
            try:
                conn.execute("DELETE FROM chat_history WHERE id = ?", (int(step_id),))
                conn.commit()
            except (ValueError, TypeError):
                pass
            finally:
                conn.close()

        await self._run_sync(_delete)

    # ═══════════════════════════════════════════════════════════════════════
    # Element（文件）管理
    # ═══════════════════════════════════════════════════════════════════════

    async def create_element(self, element: "Element"):
        pass

    async def get_element(
        self, thread_id: str, element_id: str
    ) -> Optional["ElementDict"]:
        return None

    async def delete_element(self, element_id: str, thread_id: Optional[str] = None):
        pass

    # ═══════════════════════════════════════════════════════════════════════
    # Feedback 管理
    # ═══════════════════════════════════════════════════════════════════════

    async def get_favorite_steps(self, user_id: str) -> List["StepDict"]:
        return []

    async def delete_feedback(self, feedback_id: str) -> bool:
        return True

    async def upsert_feedback(self, feedback: Feedback) -> str:
        return feedback.id or "feedback_0"

    # ═══════════════════════════════════════════════════════════════════════
    # 其他
    # ═══════════════════════════════════════════════════════════════════════

    async def build_debug_url(self) -> str:
        return ""

    async def close(self) -> None:
        pass


data_layer = MeowDevDataLayer()
