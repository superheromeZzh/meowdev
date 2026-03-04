"""
MeowDev 群聊界面 —— Chainlit 主入口（简化版）

基于 Anthropic 文章的设计理念：
- 增量进展：每次只处理一个 feature
- 结构化进度：feature_list.json + progress.md

使用 Chainlit 原生的 Data Layer 实现会话管理。
"""

import asyncio
import random
import sys
from pathlib import Path

import chainlit as cl
from chainlit.context import context
from chainlit.server import app as fastapi_app
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent))

from cats import arch, stack, pixel, ALL_CATS, CAT_MAP, CatAgent
from data_layer import data_layer
from memory import (
    add_message,
    get_all_cats_stats,
    get_messages_paginated,
    get_message_count,
    get_trend,
    init_db,
    add_cat_usage,
    create_session,
    get_session,
    update_cat_last_spoke,
    get_recent_messages,
    update_session_summary,
)
from team import MeowDevTeam, Phase
from feature_list import FeatureList
from progress import Progress


# ── Data Layer 配置 ──────────────────────────────────────────────────────────────

@cl.data_layer
def get_data_layer():
    return data_layer


@cl.header_auth_callback
async def header_auth_callback(headers: dict):
    """提供默认用户，使 Chainlit 原生 Thread 侧边栏和会话恢复正常工作"""
    from chainlit.user import PersistedUser

    return PersistedUser(
        id="default_user",
        identifier="MeowDev User",
        createdAt="2024-01-01T00:00:00+00:00",
        metadata={"role": "user"}
    )


# ── 内置 API 接口（插入到 Chainlit catch-all 之前）─────────────────────────

from starlette.routing import Route
from starlette.responses import JSONResponse as StarletteJSONResponse

async def _api_stats(request):
    range_val = request.query_params.get("range", "day")
    stats = get_all_cats_stats(range_val)
    trend = get_trend(range_val)
    return StarletteJSONResponse({"stats": stats, "trend": trend, "range": range_val})

_existing = [r for r in fastapi_app.routes if getattr(r, 'path', '') == '/api/stats']
if not _existing:
    fastapi_app.routes.insert(0, Route("/api/stats", _api_stats, methods=["GET"]))


def cat_msg(cat: CatAgent, content: str) -> cl.Message:
    return cl.Message(
        content=content,
        author=cat.cat_id,
        metadata={"avatarName": cat.cat_id},
    )

@cl.on_chat_start
async def on_start():
    """新聊天开始 - 不在 DB 创建 session，等用户发第一条消息再创建"""
    init_db()

    thread_id = context.session.thread_id
    cl.user_session.set("session_id", thread_id)
    cl.user_session.set("should_stop", False)
    cl.user_session.set("session_created", False)

    print(f"[MeowDev] on_chat_start（不创建 DB session），thread_id: {thread_id}")

    await cl.Message(
        content=(
            "**三只猫猫已上线**\n\n"
            "直接说话，猫猫们会自主讨论和干活。\n\n"
            "命令：\n"
            "- `/team 需求` — 启动团队协作\n"
            "- `/status` — 查看功能进度\n"
            "- `/usage` — 查看猫猫使用统计\n"
            "- `/history [页码]` — 查看历史消息\n"
            "- `/stop` — 暂停工作"
        ),
    ).send()


@cl.on_chat_resume
async def on_chat_resume(thread: dict):
    """恢复聊天 - Chainlit 会传递 Thread 信息"""
    init_db()

    thread_id = thread.get("id") or context.session.thread_id

    cl.user_session.set("session_id", thread_id)
    cl.user_session.set("should_stop", False)
    cl.user_session.set("session_created", bool(get_session(thread_id)))

    print(f"[MeowDev] 恢复聊天，会话 ID: {thread_id}")


@cl.on_stop
async def on_stop():
    cl.user_session.set("should_stop", True)
    # Phase 2: 只清理当前 session 的进程，不影响其他 session
    session_id = cl.user_session.get("session_id")
    if session_id:
        for cat in ALL_CATS:
            await cat.cleanup(session_id)


def _ensure_session(session_id: str):
    """确保 DB 中存在 session 记录（lazy creation）"""
    if not cl.user_session.get("session_created"):
        if not get_session(session_id):
            create_session("新对话", session_id=session_id)
        cl.user_session.set("session_created", True)


@cl.on_message
async def on_message(message: cl.Message):
    text = message.content.strip()
    session_id = cl.user_session.get("session_id") or "meowdev"

    _ensure_session(session_id)

    if text == "/stop":
        cl.user_session.set("should_stop", True)
        await cl.Message(content="*猫猫们暂停了~*").send()
        return

    if text == "/status":
        await _show_status()
        return

    if text == "/usage":
        await _show_usage()
        return

    if text.startswith("/history"):
        # 解析页码
        parts = text.split()
        page = int(parts[1]) if len(parts) > 1 else 1
        await _show_history(page, session_id)
        return

    if text.startswith("/team"):
        req = text[5:].strip()
        if req:
            await _run_team(req, session_id)
        else:
            await cl.Message(content="用法：`/team 帮我做一个 TODO 管理助手`").send()
        return

    # 普通聊天
    add_message("用户", text, session_id)
    cl.user_session.set("should_stop", False)

    responders = _pick_responders(text)
    round_count = 0
    max_rounds = 100

    while responders and round_count < max_rounds:
        round_count += 1
        next_round = []

        for cat in responders:
            if cl.user_session.get("should_stop"):
                break

            result = await _cat_respond(cat, session_id)
            if result:
                clean_text, skip, targets = result

                # 只有 [问:xxx] 才触发下一轮
                for t in targets:
                    if t in CAT_MAP and CAT_MAP[t] not in next_round:
                        next_round.append(CAT_MAP[t])

        responders = next_round

    # 摘要更新触发：每 20 条消息检查一次
    message_count = get_message_count(session_id)
    if message_count > 0 and message_count % 20 == 0:
        asyncio.create_task(_update_summary_background(session_id))


async def _cat_respond(cat: CatAgent, session_id: str) -> tuple[str, bool, list[str]] | None:
    """猫猫回复 - 带实时流式输出，返回 (清理后文本, 是否跳过, 下一轮目标列表)"""
    # 清空上次的使用数据
    cat.last_usage_data = {}

    # 显示"正在思考"状态
    msg = cat_msg(cat, f"_{cat.name} 正在思考..._")
    await msg.send()

    full = ""
    first_chunk = True

    try:
        async for chunk in cat.chat_stream_in_group(session_id):
            if first_chunk:
                msg.content = ""
                first_chunk = False

            full += chunk
            msg.content = full
            await msg.update()

        if not full.strip():
            full = await cat.chat_in_group(session_id)

    except Exception as e:
        msg.content = f"（{cat.name}出了点状况: {e}）"
        await msg.update()
        return None

    # 记录使用统计
    if cat.last_usage_data:
        add_cat_usage(cat.cat_id, cat.last_usage_data)

    # 更新发言时间戳（增量历史优化）
    update_cat_last_spoke(cat.cat_id, session_id)

    clean, skip, targets = cat.process_response(full)

    if skip or not clean.strip():
        msg.content = ""
        await msg.update()
        return None

    msg.content = clean
    await msg.update()
    add_message(cat.name, clean, session_id)
    return (clean, skip, targets)


# 用户点名猫猫加入相关猫猫，否则全部猫猫随机打乱
def _pick_responders(text: str) -> list[CatAgent]:
    lo = text.lower()
    cats = []
    if "arch" in lo or "arch酱" in lo:
        cats.append(arch)
    if "stack" in lo or "stack喵" in lo:
        cats.append(stack)
    if "pixel" in lo or "pixel咪" in lo:
        cats.append(pixel)
    if cats: return cats
    cats = list(ALL_CATS)
    # random.shuffle(cats)
    return cats


async def _show_history(page: int = 1, session_id: str = "meowdev", page_size: int = 20):
    """显示历史消息（分页）"""
    total = get_message_count(session_id)
    total_pages = (total + page_size - 1) // page_size

    if total == 0:
        await cl.Message(content="**📜 历史消息**\n\n暂无历史消息").send()
        return

    # 确保页码在有效范围内
    page = max(1, min(page, total_pages))

    offset = (page - 1) * page_size
    messages = get_messages_paginated(session_id, offset, page_size)

    if not messages:
        await cl.Message(content="没有更多历史消息了").send()
        return

    # 构建历史消息显示
    lines = [f"**📜 历史消息（第 {page}/{total_pages} 页，共 {total} 条）**\n"]

    for m in messages:
        role = m["role"]
        content = m["content"]
        # 截断过长的消息
        if len(content) > 200:
            content = content[:200] + "..."
        lines.append(f"**{role}**：{content}\n")

    # 添加翻页提示
    nav_hints = []
    if page > 1:
        nav_hints.append(f"← `/history {page - 1}` 上一页")
    if page < total_pages:
        nav_hints.append(f"`/history {page + 1}` 下一页 →")

    if nav_hints:
        lines.append("---\n" + " | ".join(nav_hints))

    await cl.Message(content="\n".join(lines)).send()


async def _show_status():
    """显示功能进度"""
    from config import OUTPUT_DIR

    fl = FeatureList(str(OUTPUT_DIR))
    prog = Progress(str(OUTPUT_DIR))

    status = fl.format_status()
    recent = prog.get_recent(20)

    content = f"**📊 项目状态**\n\n{status}\n\n---\n\n**最近进度**\n{recent}"
    await cl.Message(content=content).send()


async def _show_usage():
    """显示猫猫使用统计 - 提示用户打开右侧面板"""
    await cl.Message(
        content="📊 点击右下角的 **统计按钮** 打开用量面板，支持按天/周/月查看详细统计。"
    ).send()


async def _run_team(requirement: str, session_id: str = "meowdev"):
    """运行团队协作"""
    from config import OUTPUT_DIR

    add_message("用户", f"[启动团队协作] {requirement}", session_id)
    await cl.Message(content=f"**团队协作启动**\n\n需求：{requirement}\n---").send()

    team = MeowDevTeam()

    async def on_cat_speak(cat: CatAgent, phase: Phase, task: str) -> str:
        """猫猫发言 - 带实时流式输出"""
        add_message("system", f"[{cat.name}的任务] {task}", session_id)

        # 创建消息并显示"正在思考"状态
        msg = cat_msg(cat, f"_{cat.name} 正在思考..._")
        await msg.send()

        full = ""
        first_chunk = True

        try:
            async for chunk in cat.chat_stream_in_group(session_id):
                if first_chunk:
                    # 收到第一个 chunk，清除"正在思考"
                    msg.content = ""
                    first_chunk = False

                full += chunk
                # 实时更新消息内容
                msg.content = full
                await msg.update()

            # 流式结束后，处理回复
            if not full.strip():
                full = await cat.chat_in_group(session_id)

            clean, _, _ = cat.process_response(full)
            result = clean or full

            # 最终更新
            msg.content = result
            await msg.update()
            add_message(cat.name, result, session_id)
            return result

        except Exception as e:
            msg.content = f"（{cat.name}出错了：{e}）"
            await msg.update()
            return ""

    async def on_system(phase: Phase, content: str):
        await cl.Message(content=content).send()

    session = await team.run(
        requirement=requirement,
        session_id=session_id,
        on_cat_speak=on_cat_speak,
        on_system=on_system,
    )

    # 显示最终状态
    if team.feature_list:
        await cl.Message(content=team.feature_list.format_status()).send()


@cl.author_rename
def rename_author(orig: str) -> str:
    return {"arch": "Arch酱", "stack": "Stack喵", "pixel": "Pixel咪"}.get(orig, orig)


# ── 摘要更新后台任务 ─────────────────────────────────────────────────────────────

SUMMARY_PROMPT = """请分析以下对话历史，生成一份简洁的结构化摘要。

对话历史：
{chat_history}

请以 JSON 格式输出，包含以下字段：
{{
    "summary": "对话的整体摘要（2-3句话概括主要内容和进展）",
    "key_goals": ["用户想要达成的目标1", "目标2"],
    "key_decisions": ["做出的重要决策1", "决策2"]
}}

注意：
- summary 应该简洁但信息丰富
- key_goals 关注用户意图和项目目标
- key_decisions 关注技术选型、方案确定等重要决定
- 如果没有明确的目标或决策，对应数组可以为空
"""


async def _update_summary_background(session_id: str):
    """
    后台更新会话摘要

    使用 Arch 酱来生成摘要（因为她擅长总结）
    """
    import json

    try:
        # 获取消息历史
        messages = get_recent_messages(session_id, limit=50)
        if not messages:
            return

        # 格式化对话历史
        chat_text = "\n".join(
            f"{m['role']}：{m['content']}"
            for m in messages
        )

        prompt = SUMMARY_PROMPT.format(chat_history=chat_text)

        # 使用 Arch 酱来生成摘要（直接发送 prompt，不使用群聊上下文）
        summary_text = ""
        async for chunk in arch.send_message(prompt, session_id):
            summary_text += chunk

        if not summary_text.strip():
            return

        summary_text = summary_text.strip()

        # 尝试解析 JSON
        try:
            # 处理可能的 markdown 代码块
            if summary_text.startswith("```"):
                lines = summary_text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                summary_text = "\n".join(lines)

            parsed = json.loads(summary_text)
            update_session_summary(
                session_id,
                parsed.get("summary", summary_text),
                parsed.get("key_goals", []),
                parsed.get("key_decisions", []),
            )
            print(f"[MeowDev] 已更新会话 {session_id[:8]} 的摘要")
        except json.JSONDecodeError:
            # JSON 解析失败，直接使用文本作为摘要
            update_session_summary(session_id, summary_text[:500], [], [])
            print(f"[MeowDev] 已更新会话 {session_id[:8]} 的摘要（文本模式）")

    except Exception as e:
        print(f"[MeowDev] 更新摘要时出错: {e}")


