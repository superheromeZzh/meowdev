"""
MeowDev 群聊界面 —— Chainlit 主入口

设计理念（参考 Claude Code Agent Teams）：
- 猫猫通过共享任务看板协调工作：创建 → 认领 → 执行 → 完成
- 有任务就干完，没任务就休息，用户随时可以中断
- 猫猫自己决定该干嘛，Python 层只做消息传递和任务看板解析
- 任务看板通过 cl.TaskList 常驻侧边栏，不中断对话
- 用户可以自然语言管理任务（加任务、删除、指派）
"""

import asyncio
import random
import sys
import uuid
from pathlib import Path

import chainlit as cl

sys.path.insert(0, str(Path(__file__).parent))

from cats import arch, stack, pixel, ALL_CATS, CatAgent
from memory import add_message, get_recent_messages, init_db
from config import AVATARS_DIR, MAX_WORK_ROUNDS
from taskboard import (
    TaskBoard, parse_task_actions, parse_user_task_cmd, strip_task_markers,
)
from team import MeowDevTeam, Phase
import git_ops


def cat_msg(cat: CatAgent, content: str) -> cl.Message:
    return cl.Message(
        content=content,
        author=cat.cat_id,
        metadata={"avatarName": cat.cat_id},
    )


# ── TaskList 同步（常驻侧边栏）────────────────────────────

_STATUS_MAP = {
    "pending": cl.TaskStatus.READY,
    "doing":   cl.TaskStatus.RUNNING,
    "done":    cl.TaskStatus.DONE,
}


async def _sync_task_list(board: TaskBoard):
    """将 TaskBoard 状态同步到 Chainlit TaskList 侧边栏。"""
    task_list: cl.TaskList = cl.user_session.get("cl_task_list")
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


# ── 生命周期 ─────────────────────────────────────────────

@cl.on_chat_start
async def on_start():
    init_db()
    session_id = str(uuid.uuid4())[:8]
    cl.user_session.set("session_id", session_id)
    cl.user_session.set("task_board", TaskBoard())
    cl.user_session.set("should_stop", False)

    # 创建常驻 TaskList
    task_list = cl.TaskList()
    task_list.status = "空闲"
    cl.user_session.set("cl_task_list", task_list)
    await task_list.send()

    await cl.Message(
        content=(
            "**三只猫猫已上线** 🐱🐱🐱\n\n"
            "直接说话，猫猫们会自主讨论、拆任务、干活，直到做完为止。\n\n"
            "任务看板在侧边栏实时显示。你也可以直接管理任务：\n"
            "- `加任务：xxx` — 手动添加任务\n"
            "- `删除 T-001` — 删除任务\n"
            "- `T-001 给 Stack喵` — 指派任务\n\n"
            "| 命令 | 说明 |\n"
            "|------|------|\n"
            "| `/stop` | 让猫猫们暂停工作 |\n"
            "| `/team 需求` | 启动开发协作（含 Git PR） |\n"
            "| `/merge` | 合并待审 PR |\n"
        ),
    ).send()

    cat = random.choice(ALL_CATS)
    greetings = {
        "arch": "...来了。有什么事说。（推了推单片眼镜）",
        "stack": "嗨！有什么需要帮忙的喵！随时找我！",
        "pixel": "大家好呀~ ✨ 今天也要元气满满喵 ♪",
    }
    await cat_msg(cat, greetings[cat.cat_id]).send()
    add_message(cat.name, greetings[cat.cat_id], session_id)


@cl.on_stop
async def on_stop():
    cl.user_session.set("should_stop", True)


# ── 消息处理 ─────────────────────────────────────────────

@cl.on_message
async def on_message(message: cl.Message):
    session_id = cl.user_session.get("session_id", "default")
    text = message.content.strip()

    # ── 命令路由 ──
    if text == "/stop":
        cl.user_session.set("should_stop", True)
        await cl.Message(content="*猫猫们暂停工作了~ 发消息可以继续 🐾*").send()
        return
    if text == "/tasks":
        board: TaskBoard = cl.user_session.get("task_board") or TaskBoard()
        status = board.format_status()
        await cl.Message(
            content=f"**📋 任务看板**\n\n{status}" if status else "任务看板为空~"
        ).send()
        return
    if text.startswith("/history"):
        await _show_history(session_id)
        return
    if text.startswith("/team"):
        req = text[5:].strip()
        if req:
            await _run_team_mode(req, session_id)
        else:
            await cl.Message(content="用法：`/team 帮我做一个 TODO 管理助手`").send()
        return
    if text.startswith("/merge"):
        await _handle_merge(session_id)
        return

    board: TaskBoard = cl.user_session.get("task_board") or TaskBoard()
    cl.user_session.set("task_board", board)

    # ── 用户任务管理指令（在路由到猫猫之前解析）──
    cmd = parse_user_task_cmd(text)
    if cmd:
        result = _exec_user_task_cmd(cmd, board)
        await cl.Message(content=result).send()
        await _sync_task_list(board)
        # 如果用户加了新任务，让猫猫们继续工作
        if board.has_pending_work():
            add_message("用户", text, session_id)
            cl.user_session.set("should_stop", False)
            await _work_loop(session_id, board)
        return

    # ── 正常消息 → 猫猫回应 + 工作循环 ──
    add_message("用户", text, session_id)
    cl.user_session.set("should_stop", False)

    for cat in _pick_responders(text):
        await _cat_respond(cat, session_id, board)

    if board.has_pending_work():
        await _work_loop(session_id, board)


def _exec_user_task_cmd(cmd: dict, board: TaskBoard) -> str:
    """执行用户任务管理指令，返回结果消息。"""
    if cmd["type"] == "create":
        t = board.add(cmd["title"])
        return f"已创建任务 **{t.id}: {t.title}**"
    elif cmd["type"] == "remove":
        tid = cmd["task_id"]
        if board.remove(tid):
            return f"已删除任务 **{tid}**"
        return f"找不到任务 {tid}"
    elif cmd["type"] == "reassign":
        tid, owner = cmd["task_id"], cmd["owner"]
        if board.reassign(tid, owner):
            return f"已将 **{tid}** 指派给 **{owner}**"
        return f"无法指派 {tid}（不存在或已完成）"
    return ""


# ── 核心：持续工作循环 ───────────────────────────────────

async def _work_loop(session_id: str, board: TaskBoard):
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

            resp = await _cat_respond(cat, session_id, board)
            if resp:
                round_active = True

        if round_active:
            idle_streak = 0
        else:
            idle_streak += 1
            if idle_streak >= 2:
                break

        await asyncio.sleep(0.1)

    # 最终同步
    await _sync_task_list(board)

    status = board.format_status()
    if cl.user_session.get("should_stop"):
        await cl.Message(content=f"⏸️ *猫猫们暂停了~*\n\n{status}").send()
    elif board.has_pending_work():
        await cl.Message(content=f"⚠️ *达到安全轮数上限*\n\n{status}").send()
    else:
        await cl.Message(content=f"✅ *所有任务已完成~*\n\n{status}").send()


# ── 猫猫发言（统一入口）─────────────────────────────────

async def _cat_respond(cat: CatAgent, session_id: str,
                       board: TaskBoard) -> str | None:
    board_text = board.format_status()

    async with cl.Step(name=cat.name, type="llm", show_input=False) as step:
        msg = cat_msg(cat, "")
        await msg.send()

        full = ""
        async for chunk in cat.chat_stream_in_group(
            session_id, task_board_text=board_text
        ):
            if not full:
                msg.content = ""
                await msg.update()
            full += chunk
            await msg.stream_token(chunk)

        if not full.strip():
            full = await cat.chat_in_group(
                session_id, task_board_text=board_text
            )
            msg.content = full
            await msg.update()

        actions = parse_task_actions(full)
        action_log = _apply_actions(actions, board, cat.name)
        is_idle = any(a["type"] == "idle" for a in actions)

        # 任务看板有变动就同步侧边栏
        if action_log:
            await _sync_task_list(board)

        clean, skip = cat.process_response(full)
        if clean:
            clean = strip_task_markers(clean)

        if skip or is_idle or not clean.strip():
            msg.content = ""
            await msg.update()
            step.output = action_log or "空闲"
            return None

        msg.content = clean
        await msg.update()
        add_message(cat.name, clean, session_id)
        step.output = action_log or "已回复"

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


# ── 选谁先回应 ──────────────────────────────────────────

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

async def _show_history(session_id: str):
    msgs = get_recent_messages(session_id, limit=50)
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

async def _run_team_mode(requirement: str, session_id: str):
    add_message("用户", f"[启动团队协作] {requirement}", session_id)
    await cl.Message(content=f"**团队协作启动** 🚀\n\n需求：{requirement}\n---").send()

    team = MeowDevTeam()

    async def on_cat_speak(cat: CatAgent, phase: Phase, task: str) -> str:
        add_message("system", f"[{cat.name}的任务] {task}", session_id)
        async with cl.Step(
            name=f"📌 {phase.value} | {cat.name}", type="llm", show_input=False
        ) as step:
            msg = cat_msg(cat, f"*{cat.name} 正在工作...*")
            await msg.send()
            full = ""
            async for chunk in cat.chat_stream_in_group(session_id):
                if not full:
                    msg.content = ""
                    await msg.update()
                full += chunk
                await msg.stream_token(chunk)
            if not full.strip():
                full = await cat.chat_in_group(session_id)
                msg.content = full
                await msg.update()
            clean, _ = cat.process_response(full)
            result = clean or full
            msg.content = result
            await msg.update()
            add_message(cat.name, result, session_id)
            step.output = "完成"
        return result

    async def on_system(phase: Phase, content: str):
        await cl.Message(content=content).send()

    session = await team.run(
        requirement=requirement,
        session_id=session_id,
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

async def _handle_merge(session_id: str):
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
        cat = random.choice(ALL_CATS)
        cheers = {"arch": "...嗯，合了。（微微点头）", "stack": "耶！🎉🎉🎉", "pixel": "太好了 ✨"}
        await cat_msg(cat, cheers[cat.cat_id]).send()
    except Exception as e:
        await cl.Message(content=f"**合并失败** ❌\n\n{e}").send()


# ── Chainlit 配置 ────────────────────────────────────────

@cl.author_rename
def rename_author(orig: str) -> str:
    return {"arch": "Arch酱", "stack": "Stack喵", "pixel": "Pixel咪"}.get(orig, orig)
