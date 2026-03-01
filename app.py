"""
MeowDev 群聊界面 —— Chainlit 主入口（简化版）

基于 Anthropic 文章的设计理念：
- 增量进展：每次只处理一个 feature
- 结构化进度：feature_list.json + progress.md
"""

import asyncio
import random
import sys
from pathlib import Path

import chainlit as cl
from chainlit.server import app as fastapi_app
from fastapi.responses import JSONResponse

# ── 内置 API 接口（必须在 chainlit 初始化之前注册）─────────────────────
from memory import get_all_cats_stats, get_trend
from starlette.routing import Route

async def api_stats(request):
    """获取猫猫使用统计 - 内置接口"""
    range_type = request.query_params.get("range", "day")  # day/week/month
    stats = get_all_cats_stats(range_type)
    trend = get_trend(range_type)
    return JSONResponse({"stats": stats, "trend": trend, "range": range_type})

api_route = Route("/api/stats", endpoint=api_stats, methods=["GET"])
fastapi_app.routes.insert(0, api_route)

sys.path.insert(0, str(Path(__file__).parent))

from cats import arch, stack, pixel, ALL_CATS, CAT_MAP, CatAgent
from memory import (
    add_message,
    get_recent_messages,
    get_messages_paginated,
    get_message_count,
    init_db,
    add_cat_usage,
)
from team import MeowDevTeam, Phase
from feature_list import FeatureList
from progress import Progress

SESSION_ID = "meowdev"


def cat_msg(cat: CatAgent, content: str) -> cl.Message:
    return cl.Message(
        content=content,
        author=cat.cat_id,
        metadata={"avatarName": cat.cat_id},
    )

@cl.on_chat_start
async def on_start():
    init_db()
    cl.user_session.set("session_id", SESSION_ID)
    cl.user_session.set("should_stop", False)

    # 加载历史消息（最近100条）
    recent = get_recent_messages(SESSION_ID, limit=100)

    if recent:
        # 显示恢复提示
        total = get_message_count(SESSION_ID)
        await cl.Message(
            content=f"**💬 对话已恢复**（最近{len(recent)}条，共{total}条）\n输入 `/history` 查看更多历史"
        ).send()

        # 以真正的消息气泡形式显示历史
        for m in recent:
            role = m["role"]
            content = m["content"]

            if role == "用户":
                # 用户消息
                await cl.Message(content=content).send()
            elif role in ["Arch酱", "Stack喵", "Pixel咪"]:
                # 猫猫消息 - 使用对应的猫猫头像
                cat = CAT_MAP.get(role.lower().replace("酱", "").replace("喵", "").replace("咪", ""))
                if cat:
                    await cat_msg(cat, content).send()
                else:
                    await cl.Message(content=f"**{role}**：{content}").send()
            elif role not in ["system"]:
                # 其他消息（跳过 system 类型）
                await cl.Message(content=f"**{role}**：{content}").send()
    else:
        # 首次使用，显示欢迎消息
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

        cat = random.choice(ALL_CATS)
        greetings = {
            "arch": "...来了。有什么事说。（推了推单片眼镜）",
            "stack": "嗨！有什么需要帮忙的喵！",
            "pixel": "大家好呀~ 今天也要元气满满喵 ♪",
        }
        await cat_msg(cat, greetings[cat.cat_id]).send()
        add_message(cat.name, greetings[cat.cat_id], SESSION_ID)


@cl.on_stop
async def on_stop():
    cl.user_session.set("should_stop", True)


@cl.on_message
async def on_message(message: cl.Message):
    text = message.content.strip()

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
        await _show_history(page)
        return

    if text.startswith("/team"):
        req = text[5:].strip()
        if req:
            await _run_team(req)
        else:
            await cl.Message(content="用法：`/team 帮我做一个 TODO 管理助手`").send()
        return

    # 普通聊天
    add_message("用户", text, SESSION_ID)
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

            result = await _cat_respond(cat)
            if result:
                clean_text, skip, targets = result

                # 只有 [问:xxx] 才触发下一轮
                for t in targets:
                    if t in CAT_MAP and CAT_MAP[t] not in next_round:
                        next_round.append(CAT_MAP[t])

        responders = next_round
    # while responders and round_count < max_rounds:
    #     round_count += 1
    #     for cat in responders:
    #         if cl.user_session.get("should_stop"):
    #             break

    #         await _cat_respond(cat)

async def _cat_respond(cat: CatAgent) -> tuple[str, bool, list[str]] | None:
    """猫猫回复 - 带实时流式输出，返回 (清理后文本, 是否跳过, 下一轮目标列表)"""
    # 清空上次的使用数据
    cat.last_usage_data = {}

    # 显示"正在思考"状态
    msg = cat_msg(cat, f"_{cat.name} 正在思考..._")
    await msg.send()

    full = ""
    first_chunk = True

    try:
        async for chunk in cat.chat_stream_in_group(SESSION_ID):
            if first_chunk:
                msg.content = ""
                first_chunk = False

            full += chunk
            msg.content = full
            await msg.update()

        if not full.strip():
            full = await cat.chat_in_group(SESSION_ID)

    except Exception as e:
        msg.content = f"（{cat.name}出了点状况: {e}）"
        await msg.update()
        return None

    # 记录使用统计
    if cat.last_usage_data:
        add_cat_usage(cat.cat_id, cat.last_usage_data)

    clean, skip, targets = cat.process_response(full)

    if skip or not clean.strip():
        msg.content = ""
        await msg.update()
        return None

    msg.content = clean
    await msg.update()
    add_message(cat.name, clean, SESSION_ID)
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


async def _show_history(page: int = 1, page_size: int = 20):
    """显示历史消息（分页）"""
    total = get_message_count(SESSION_ID)
    total_pages = (total + page_size - 1) // page_size

    if total == 0:
        await cl.Message(content="**📜 历史消息**\n\n暂无历史消息").send()
        return

    # 确保页码在有效范围内
    page = max(1, min(page, total_pages))

    offset = (page - 1) * page_size
    messages = get_messages_paginated(SESSION_ID, offset, page_size)

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


async def _run_team(requirement: str):
    """运行团队协作"""
    from config import OUTPUT_DIR

    add_message("用户", f"[启动团队协作] {requirement}", SESSION_ID)
    await cl.Message(content=f"**团队协作启动**\n\n需求：{requirement}\n---").send()

    team = MeowDevTeam()

    async def on_cat_speak(cat: CatAgent, phase: Phase, task: str) -> str:
        """猫猫发言 - 带实时流式输出"""
        add_message("system", f"[{cat.name}的任务] {task}", SESSION_ID)

        # 创建消息并显示"正在思考"状态
        msg = cat_msg(cat, f"_{cat.name} 正在思考..._")
        await msg.send()

        full = ""
        first_chunk = True

        try:
            async for chunk in cat.chat_stream_in_group(SESSION_ID):
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
                full = await cat.chat_in_group(SESSION_ID)

            clean, _ = cat.process_response(full)
            result = clean or full

            # 最终更新
            msg.content = result
            await msg.update()
            add_message(cat.name, result, SESSION_ID)
            return result

        except Exception as e:
            msg.content = f"（{cat.name}出错了：{e}）"
            await msg.update()
            return ""

    async def on_system(phase: Phase, content: str):
        await cl.Message(content=content).send()

    session = await team.run(
        requirement=requirement,
        session_id=SESSION_ID,
        on_cat_speak=on_cat_speak,
        on_system=on_system,
    )

    # 显示最终状态
    if team.feature_list:
        await cl.Message(content=team.feature_list.format_status()).send()


@cl.author_rename
def rename_author(orig: str) -> str:
    return {"arch": "Arch酱", "stack": "Stack喵", "pixel": "Pixel咪"}.get(orig, orig)


