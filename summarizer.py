"""
摘要生成模块

功能：
- 从对话历史生成结构化摘要
- 支持冷启动场景
"""

import json
from typing import Optional

from memory import get_recent_messages, update_session_summary


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


def generate_summary(messages: list[dict], llm_func) -> Optional[dict]:
    """
    从对话历史生成结构化摘要

    Args:
        messages: 消息列表，每条包含 role, content, timestamp
        llm_func: 调用 LLM 的函数，接受 prompt 字符串，返回响应字符串

    Returns:
        {
            "summary": "对话的整体摘要...",
            "key_goals": ["目标1", "目标2"],
            "key_decisions": ["决策1", "决策2"]
        }
        或 None（如果生成失败）
    """
    if not messages:
        return None

    # 格式化对话历史
    chat_text = "\n".join(
        f"{m['role']}：{m['content']}"
        for m in messages
    )

    prompt = SUMMARY_PROMPT.format(chat_history=chat_text)

    try:
        response = llm_func(prompt)
        if not response:
            return None

        # 尝试解析 JSON
        # 处理可能的 markdown 代码块
        response = response.strip()
        if response.startswith("```"):
            # 移除代码块标记
            lines = response.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            response = "\n".join(lines)

        result = json.loads(response)

        # 验证必要字段
        if "summary" not in result:
            return None

        # 确保列表字段存在
        result.setdefault("key_goals", [])
        result.setdefault("key_decisions", [])

        return result

    except json.JSONDecodeError:
        # JSON 解析失败，尝试提取有用信息
        return {
            "summary": response[:500] if response else "摘要生成失败",
            "key_goals": [],
            "key_decisions": [],
        }
    except Exception as e:
        print(f"[Summarizer] 生成摘要时出错: {e}")
        return None


async def generate_summary_async(messages: list[dict], llm_func_async) -> Optional[dict]:
    """
    异步版本的摘要生成

    Args:
        messages: 消息列表
        llm_func_async: 异步 LLM 调用函数

    Returns:
        摘要字典或 None
    """
    if not messages:
        return None

    chat_text = "\n".join(
        f"{m['role']}：{m['content']}"
        for m in messages
    )

    prompt = SUMMARY_PROMPT.format(chat_history=chat_text)

    try:
        response = await llm_func_async(prompt)
        if not response:
            return None

        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            response = "\n".join(lines)

        result = json.loads(response)

        if "summary" not in result:
            return None

        result.setdefault("key_goals", [])
        result.setdefault("key_decisions", [])

        return result

    except json.JSONDecodeError:
        return {
            "summary": response[:500] if response else "摘要生成失败",
            "key_goals": [],
            "key_decisions": [],
        }
    except Exception as e:
        print(f"[Summarizer] 异步生成摘要时出错: {e}")
        return None


def update_summary_for_session(session_id: str, llm_func, message_limit: int = 50) -> bool:
    """
    更新指定会话的摘要

    Args:
        session_id: 会话ID
        llm_func: LLM 调用函数
        message_limit: 用于生成摘要的最大消息数

    Returns:
        是否成功更新
    """
    messages = get_recent_messages(session_id, limit=message_limit)
    if not messages:
        return False

    summary = generate_summary(messages, llm_func)
    if not summary:
        return False

    update_session_summary(
        session_id,
        summary["summary"],
        summary["key_goals"],
        summary["key_decisions"],
    )
    return True


async def update_summary_for_session_async(session_id: str, llm_func_async, message_limit: int = 50) -> bool:
    """
    异步更新指定会话的摘要

    Args:
        session_id: 会话ID
        llm_func_async: 异步 LLM 调用函数
        message_limit: 用于生成摘要的最大消息数

    Returns:
        是否成功更新
    """
    messages = get_recent_messages(session_id, limit=message_limit)
    if not messages:
        return False

    summary = await generate_summary_async(messages, llm_func_async)
    if not summary:
        return False

    update_session_summary(
        session_id,
        summary["summary"],
        summary["key_goals"],
        summary["key_decisions"],
    )
    return True
