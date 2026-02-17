"""
MeowDev 群聊界面 —— Chainlit 主入口

核心设计：
- 群聊模式：用户发消息后，猫猫们都能看到并回应
- 每只猫猫看到完整对话历史 + 其他猫猫的发言
- 记忆持久化：跨会话记住用户偏好
- /team 命令启动团队协作（含 GitHub PR 流程）
- /merge 命令合并 PR
"""

import asyncio
import random
import sys
import uuid
from pathlib import Path

import chainlit as cl

sys.path.insert(0, str(Path(__file__).parent))

from cats import arch, stack, pixel, ALL_CATS, CatAgent
from memory import add_message, init_db
from config import AVATARS_DIR
from team import MeowDevTeam, Phase
import git_ops


def cat_msg(cat: CatAgent, content: str) -> cl.Message:
    """创建猫猫消息，确保头像和显示名都正确。

    关键：metadata.avatarName 决定头像文件匹配（英文 ID），
    author 经过 @cl.author_rename 后变成中文显示名。
    """
    return cl.Message(
        content=content,
        author=cat.cat_id,
        metadata={"avatarName": cat.cat_id},
    )


# ── 欢迎 ─────────────────────────────────────────────────

@cl.on_chat_start
async def on_start():
    """聊天开始"""
    init_db()

    session_id = str(uuid.uuid4())[:8]
    cl.user_session.set("session_id", session_id)

    await cl.Message(
        content=(
            "**三只猫猫已上线** 🐱🐱🐱\n\n"
            "直接说话就好，大家都能听到。\n"
            "输入 `/team 需求描述` 启动开发协作（含 GitHub PR）。\n"
            "输入 `/merge` 合并待审 PR。"
        ),
    ).send()

    greeters = random.sample(ALL_CATS, k=random.randint(1, 2))
    for cat_agent in greeters:
        greetings = {
            "arch": "...来了。有什么事说。（推了推单片眼镜）",
            "stack": "嗨！有什么需要帮忙的喵！随时找我！",
            "pixel": "大家好呀~ ✨ 今天也要元气满满喵 ♪",
        }
        await cat_msg(cat_agent, greetings[cat_agent.cat_id]).send()
        add_message(cat_agent.name, greetings[cat_agent.cat_id], session_id)


# ── 消息处理 ─────────────────────────────────────────────

@cl.on_message
async def on_message(message: cl.Message):
    """用户发消息 → 记录 → 猫猫们各自决定是否回应"""
    session_id = cl.user_session.get("session_id", "default")
    text = message.content.strip()

    if text.startswith("/team"):
        requirement = text[5:].strip()
        if requirement:
            await run_team_mode(requirement, session_id)
        else:
            await cl.Message(
                content="在 `/team` 后面写上需求喵~ 例如：`/team 帮我做一个 TODO 管理助手`",
            ).send()
        return

    if text.startswith("/merge"):
        await handle_merge(session_id)
        return

    add_message("用户", text, session_id)

    responding_cats = _decide_responders(text)

    for cat_agent in responding_cats:
        msg = cat_msg(cat_agent, f"*{cat_agent.name} 正在输入...*")
        await msg.send()

        full_response = ""
        async for chunk in cat_agent.chat_stream_in_group(session_id):
            if not full_response:
                msg.content = ""
                await msg.update()
            full_response += chunk
            await msg.stream_token(chunk)

        if not full_response.strip():
            full_response = await cat_agent.chat_in_group(session_id)
            msg.content = full_response
            await msg.update()

        clean_text, should_skip = cat_agent.process_response(full_response)

        if should_skip or not clean_text.strip():
            msg.content = ""
            await msg.update()
            continue

        msg.content = clean_text
        await msg.update()

        add_message(cat_agent.name, clean_text, session_id)

        await asyncio.sleep(0.3)


def _decide_responders(text: str) -> list[CatAgent]:
    """决定哪些猫猫应该回应这条消息。"""
    text_lower = text.lower()

    if any(k in text_lower for k in ["arch", "arch酱"]):
        others = [c for c in ALL_CATS if c.cat_id != "arch"]
        return [arch] + random.sample(others, k=random.randint(0, 1))
    if any(k in text_lower for k in ["stack", "stack喵"]):
        others = [c for c in ALL_CATS if c.cat_id != "stack"]
        return [stack] + random.sample(others, k=random.randint(0, 1))
    if any(k in text_lower for k in ["pixel", "pixel咪"]):
        others = [c for c in ALL_CATS if c.cat_id != "pixel"]
        return [pixel] + random.sample(others, k=random.randint(0, 1))

    tech_keywords = ["代码", "bug", "报错", "api", "接口", "数据库", "部署", "git",
                     "python", "javascript", "react", "函数", "算法", "架构", "开发"]
    if any(k in text_lower for k in tech_keywords):
        cats = [arch, stack]
        if random.random() > 0.5:
            cats.append(pixel)
        return cats

    design_keywords = ["设计", "配色", "颜色", "ui", "ux", "界面", "好看", "丑",
                       "风格", "字体", "排版", "logo", "图标", "美"]
    if any(k in text_lower for k in design_keywords):
        cats = [pixel]
        if random.random() > 0.4:
            cats.append(stack)
        if random.random() > 0.6:
            cats.append(arch)
        return cats

    cats = list(ALL_CATS)
    random.shuffle(cats)
    return cats[:random.randint(2, 3)]


# ── 团队协作模式 ─────────────────────────────────────────

async def run_team_mode(requirement: str, session_id: str):
    """团队开发协作模式（通过 MeowDevTeam 编排，含 GitHub PR 流程）"""
    add_message("用户", f"[启动团队协作] {requirement}", session_id)

    await cl.Message(
        content=f"**团队协作启动** 🚀\n\n需求：{requirement}\n\n---",
    ).send()

    team = MeowDevTeam()

    async def on_cat_speak(cat: CatAgent, phase: Phase, task: str) -> str:
        """回调：猫猫发言（含流式输出），返回回复文本"""
        return await _cat_speak(cat, session_id, task)

    async def on_system(phase: Phase, content: str):
        """回调：系统消息展示"""
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
            content=(
                f"**✅ Review 完成！**\n\n"
                f"🔗 PR: {session.pr_url}\n\n"
                f"输入 `/merge` 确认合并到 main 分支。"
            ),
        ).send()
    else:
        from utils import format_file_tree
        file_tree = format_file_tree(session.work_dir)
        await cl.Message(
            content=f"**✅ 协作完成！**\n\n```\n{file_tree}\n```\n\n*猫猫们辛苦了 🐾*",
        ).send()


async def _cat_speak(ca: CatAgent, session_id: str, task: str) -> str:
    """让一只猫猫在群聊中发言，返回回复文本。"""
    add_message("system", f"[{ca.name}的任务] {task}", session_id)

    msg = cat_msg(ca, f"*{ca.name} 正在输入...*")
    await msg.send()

    full_response = ""
    async for chunk in ca.chat_stream_in_group(session_id):
        if not full_response:
            msg.content = ""
            await msg.update()
        full_response += chunk
        await msg.stream_token(chunk)

    if not full_response.strip():
        full_response = await ca.chat_in_group(session_id)
        msg.content = full_response
        await msg.update()

    clean_text, _ = ca.process_response(full_response)
    if clean_text:
        msg.content = clean_text
        await msg.update()
        add_message(ca.name, clean_text, session_id)
    else:
        msg.content = full_response
        await msg.update()
        add_message(ca.name, full_response, session_id)

    return clean_text or full_response


# ── /merge 命令 ──────────────────────────────────────────

async def handle_merge(session_id: str):
    """处理 /merge 命令：合并当前待审 PR"""
    pr_number = cl.user_session.get("pr_number")
    work_dir = cl.user_session.get("work_dir")

    if not pr_number:
        await cl.Message(
            content="没有待合并的 PR 喵~ 先用 `/team` 启动一次开发协作吧。",
        ).send()
        return

    await cl.Message(content=f"**正在合并 PR #{pr_number}...**").send()

    try:
        result = await git_ops.merge_pr(pr_number, work_dir)
        await git_ops.switch_to_main(work_dir)
        cl.user_session.set("pr_number", None)

        await cl.Message(
            content=f"**PR #{pr_number} 已合并到 main** ✅\n\n{result}",
        ).send()

        celebrations = {
            "arch": "...嗯，合并了。代码质量还行。（微微点头）",
            "stack": "耶！合并成功喵！！又完成一个需求！🎉🎉🎉",
            "pixel": "太好了呀~ 大家辛苦了！成品好好看 ✨",
        }
        celebrator = random.choice(ALL_CATS)
        await cat_msg(celebrator, celebrations[celebrator.cat_id]).send()
        add_message(celebrator.name, celebrations[celebrator.cat_id], session_id)

    except Exception as e:
        await cl.Message(content=f"**合并失败** ❌\n\n{e}").send()


# ── Chainlit 配置 ────────────────────────────────────────

@cl.author_rename
def rename_author(orig_author: str) -> str:
    """author ID → 显示名"""
    rename_map = {
        "arch": "Arch酱",
        "stack": "Stack喵",
        "pixel": "Pixel咪",
    }
    return rename_map.get(orig_author, orig_author)
