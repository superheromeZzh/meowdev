"""
MeowDev 群聊界面 —— Chainlit 主入口
"""

import asyncio
import random
import sys
from pathlib import Path

import chainlit as cl

sys.path.insert(0, str(Path(__file__).parent))

from cats import arch, stack, pixel, ALL_CATS, CatAgent
from memory import add_message, get_recent_messages, init_db
from config import MAX_WORK_ROUNDS
from taskboard import (
    TaskBoard, parse_task_actions, parse_user_task_cmd, strip_task_markers,
)
from team import MeowDevTeam, Phase
import git_ops

# 固定 session_id，热重载后对话历史不丢失
SESSION_ID = "meowdev"


def cat_msg(cat: CatAgent, content: str) -> cl.Message:
    return cl.Message(
        content=content,
        author=cat.cat_id,
        metadata={"avatarName": cat.cat_id},
    )


# ── TaskList 侧边栏同步 ──────────────────────────────────

_STATUS_MAP = {
    "pending": cl.TaskStatus.READY,
    "doing":   cl.TaskStatus.RUNNING,
    "done":    cl.TaskStatus.DONE,
}


async def _sync_task_list(board: TaskBoard):
    try:
        task_list = cl.user_session.get("cl_task_list")
        if not task_list:
            return
        task_list.tasks.clear()
        for t in board.tasks.values():
            owner_tag = f" ({t.owner})" if t.owner else ""
            task_list.tasks.append(
                cl.Task(
                    title=f"{t.id}: {t.title}{owner_tag}",
                    status=_STATUS_MAP.get(t.status, cl.TaskStatus.READY),
                )
            )
        task_list.status = "工作中..." if board.has_pending_work() else "空闲"
        await task_list.send()
    except Exception:
        pass


# ── 生命周期 ─────────────────────────────────────────────

@cl.on_chat_start
async def on_start():
    init_db()
    cl.user_session.set("session_id", SESSION_ID)
    cl.user_session.set("should_stop", False)

    board = TaskBoard()
    cl.user_session.set("task_board", board)

    task_list = cl.TaskList()
    task_list.status = "空闲"
    cl.user_session.set("cl_task_list", task_list)
    await task_list.send()

    # 检查是否有历史对话（热重载恢复）
    recent = get_recent_messages(SESSION_ID, limit=10)

    if recent:
        lines = []
        for m in recent[-8:]:
            c = m["content"]
            if len(c) > 100:
                c = c[:100] + "..."
            lines.append(f"**{m['role']}**：{c}")
        recap = "\n\n".join(lines)

        if board.has_pending_work():
            await _sync_task_list(board)
            await cl.Message(
                content=f"**💬 对话已恢复**\n\n{recap}\n\n---\n"
                        f"**📋 未完成任务**\n{board.format_status()}\n\n"
                        f"发消息让猫猫们继续~",
            ).send()
        else:
            await cl.Message(content=f"**💬 对话已恢复**\n\n{recap}").send()
    else:
        await cl.Message(
            content=(
                "**三只猫猫已上线** 🐱🐱🐱\n\n"
                "直接说话，猫猫们会自主讨论和干活。\n"
                "你随时可以发言，不影响他们工作。\n\n"
                "任务管理：`加任务：xxx` | `删除 T-001` | `T-001 给 Stack喵`\n"
                "`/stop` 暂停 | `/team 需求` 开发协作 | `/merge` 合并 PR"
            ),
        ).send()
        cat = random.choice(ALL_CATS)
        greetings = {
            "arch": "...来了。有什么事说。（推了推单片眼镜）",
            "stack": "嗨！有什么需要帮忙的喵！随时找我！",
            "pixel": "大家好呀~ ✨ 今天也要元气满满喵 ♪",
        }
        await cat_msg(cat, greetings[cat.cat_id]).send()
        add_message(cat.name, greetings[cat.cat_id], SESSION_ID)


@cl.on_stop
async def on_stop():
    cl.user_session.set("should_stop", True)


# ── 消息处理 ─────────────────────────────────────────────

@cl.on_message
async def on_message(message: cl.Message):
    text = message.content.strip()
    board: TaskBoard = cl.user_session.get("task_board") or TaskBoard()

    if text == "/stop":
        cl.user_session.set("should_stop", True)
        await cl.Message(content="*猫猫们暂停工作了~ 发消息可以继续 🐾*").send()
        return
    if text == "/tasks":
        status = board.format_status()
        await cl.Message(
            content=f"**📋 任务看板**\n\n{status}" if status else "任务看板为空~"
        ).send()
        return
    if text.startswith("/history"):
        await _show_history()
        return
    if text.startswith("/team"):
        req = text[5:].strip()
        if req:
            await _run_team_mode(req)
        else:
            await cl.Message(content="用法：`/team 帮我做一个 TODO 管理助手`").send()
        return
    if text.startswith("/merge"):
        await _handle_merge()
        return

    cmd = parse_user_task_cmd(text)
    if cmd:
        result = _exec_user_task_cmd(cmd, board)
        await cl.Message(content=result).send()
        await _sync_task_list(board)
        _ensure_work_loop(board)
        return

    add_message("用户", text, SESSION_ID)
    cl.user_session.set("should_stop", False)

    loop_task = cl.user_session.get("work_loop_task")
    if loop_task and not loop_task.done():
        return

    for cat in _pick_responders(text):
        await _cat_respond(cat, board)

    _ensure_work_loop(board)


def _exec_user_task_cmd(cmd: dict, board: TaskBoard) -> str:
    if cmd["type"] == "create":
        t = board.add(cmd["title"])
        return f"已创建任务 **{t.id}: {t.title}**"
    elif cmd["type"] == "remove":
        tid = cmd["task_id"]
        return f"已删除任务 **{tid}**" if board.remove(tid) else f"找不到任务 {tid}"
    elif cmd["type"] == "reassign":
        tid, owner = cmd["task_id"], cmd["owner"]
        if board.reassign(tid, owner):
            return f"已将 **{tid}** 指派给 **{owner}**"
        return f"无法指派 {tid}（不存在或已完成）"
    return ""


# ── 后台工作循环 ─────────────────────────────────────────

def _ensure_work_loop(board: TaskBoard):
    if not board.has_pending_work():
        return
    loop_task = cl.user_session.get("work_loop_task")
    if loop_task and not loop_task.done():
        return
    task = asyncio.create_task(_work_loop(board))
    cl.user_session.set("work_loop_task", task)


async def _work_loop(board: TaskBoard):
    try:
        await _sync_task_list(board)
        idle_streak = 0

        for _ in range(MAX_WORK_ROUNDS):
            if cl.user_session.get("should_stop"):
                break
            if not board.has_pending_work():
                break

            round_active = False
            for cat in ALL_CATS:
                if cl.user_session.get("should_stop"):
                    break
                if not board.has_pending_work():
                    break
                resp = await _cat_respond(cat, board)
                if resp:
                    round_active = True

            idle_streak = 0 if round_active else idle_streak + 1
            if idle_streak >= 2:
                break
            await asyncio.sleep(0.1)

        await _sync_task_list(board)
        status = board.format_status()
        if cl.user_session.get("should_stop"):
            await cl.Message(content=f"⏸️ *猫猫们暂停了~*\n\n{status}").send()
        elif board.has_pending_work():
            await cl.Message(content=f"⚠️ *达到安全轮数上限*\n\n{status}").send()
        else:
            await cl.Message(content=f"✅ *所有任务已完成~*\n\n{status}").send()
    except Exception as e:
        try:
            await cl.Message(content=f"⚠️ *工作循环异常: {e}*").send()
        except Exception:
            pass


# ── 猫猫发言 ─────────────────────────────────────────────

async def _cat_respond(cat: CatAgent, board: TaskBoard) -> str | None:
    board_text = board.format_status()
    msg = cat_msg(cat, "")
    await msg.send()

    full = ""
    try:
        async for chunk in cat.chat_stream_in_group(
            SESSION_ID, task_board_text=board_text
        ):
            full += chunk
            await msg.stream_token(chunk)
    except Exception:
        pass

    if not full.strip():
        try:
            full = await cat.chat_in_group(
                SESSION_ID, task_board_text=board_text
            )
        except Exception as e:
            full = f"（{cat.name}出了点状况: {e}）"

    actions = parse_task_actions(full)
    action_log = _apply_actions(actions, board, cat.name)
    is_idle = any(a["type"] == "idle" for a in actions)

    if action_log:
        await _sync_task_list(board)

    clean, skip = cat.process_response(full)
    if clean:
        clean = strip_task_markers(clean)

    if skip or is_idle or not clean.strip():
        msg.content = ""
        await msg.update()
        return None

    msg.content = clean
    await msg.update()
    add_message(cat.name, clean, SESSION_ID)
    await asyncio.sleep(0.3)
    return clean


def _apply_actions(actions: list[dict], board: TaskBoard,
                   cat_name: str) -> str:
    parts = []
    for a in actions:
        if a["type"] == "create":
            t = board.add(a["title"])
            parts.append(f"新建 {t.id}")
        elif a["type"] == "claim":
            if board.claim(a["task_id"], cat_name):
                parts.append(f"认领 {a['task_id']}")
        elif a["type"] == "complete":
            if board.complete(a["task_id"]):
                parts.append(f"完成 {a['task_id']}")
    return " | ".join(parts)


def _pick_responders(text: str) -> list[CatAgent]:
    lo = text.lower()
    if any(k in lo for k in ["arch", "arch酱"]):
        return [arch]
    if any(k in lo for k in ["stack", "stack喵"]):
        return [stack]
    if any(k in lo for k in ["pixel", "pixel咪"]):
        return [pixel]
    cats = list(ALL_CATS)
    random.shuffle(cats)
    return cats


# ── /history ─────────────────────────────────────────────

async def _show_history():
    msgs = get_recent_messages(SESSION_ID, limit=50)
    if not msgs:
        await cl.Message(content="还没有聊天记录喵~").send()
        return
    lines = ["**📜 聊天记录**\n---"]
    for m in msgs:
        r, c = m["role"], m["content"]
        if len(c) > 200:
            c = c[:200] + "..."
        lines.append(f"**{r}**：{c}")
    await cl.Message(content="\n\n".join(lines)).send()


# ── /team ────────────────────────────────────────────────

async def _run_team_mode(requirement: str):
    add_message("用户", f"[启动团队协作] {requirement}", SESSION_ID)
    await cl.Message(content=f"**团队协作启动** 🚀\n\n需求：{requirement}\n---").send()

    team = MeowDevTeam()

    async def on_cat_speak(cat: CatAgent, phase: Phase, task: str) -> str:
        add_message("system", f"[{cat.name}的任务] {task}", SESSION_ID)
        msg = cat_msg(cat, "")
        await msg.send()
        full = ""
        async for chunk in cat.chat_stream_in_group(SESSION_ID):
            full += chunk
            await msg.stream_token(chunk)
        if not full.strip():
            full = await cat.chat_in_group(SESSION_ID)
        clean, _ = cat.process_response(full)
        result = clean or full
        msg.content = result
        await msg.update()
        add_message(cat.name, result, SESSION_ID)
        return result

    async def on_system(phase: Phase, content: str):
        await cl.Message(content=content).send()

    session = await team.run(
        requirement=requirement,
        session_id=SESSION_ID,
        on_cat_speak=on_cat_speak,
        on_system=on_system,
    )

    if session.pr_url:
        cl.user_session.set("pr_number", session.pr_number)
        cl.user_session.set("work_dir", session.work_dir)
        await cl.Message(
            content=f"**✅ Review 完成！** 🔗 PR: {session.pr_url}\n\n输入 `/merge` 确认合并。"
        ).send()
    else:
        from utils import format_file_tree
        tree = format_file_tree(session.work_dir)
        await cl.Message(content=f"**✅ 协作完成！**\n\n```\n{tree}\n```").send()


# ── /merge ───────────────────────────────────────────────

async def _handle_merge():
    pr = cl.user_session.get("pr_number")
    wd = cl.user_session.get("work_dir")
    if not pr:
        await cl.Message(content="没有待合并的 PR 喵~").send()
        return
    await cl.Message(content=f"**正在合并 PR #{pr}...**").send()
    try:
        result = await git_ops.merge_pr(pr, wd)
        await git_ops.switch_to_main(wd)
        cl.user_session.set("pr_number", None)
        await cl.Message(content=f"**PR #{pr} 已合并** ✅\n\n{result}").send()
    except Exception as e:
        await cl.Message(content=f"**合并失败** ❌\n\n{e}").send()


@cl.author_rename
def rename_author(orig: str) -> str:
    return {"arch": "Arch酱", "stack": "Stack喵", "pixel": "Pixel咪"}.get(orig, orig)
