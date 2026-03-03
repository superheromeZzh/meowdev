"""
CatAgent 类 —— 每只猫猫的大脑

核心改进：
- 群聊感知：每只猫猫都能看到完整的对话历史
- 记忆系统：猫猫记得用户的偏好和过往对话
- 自动提取 [记住：xxx] 标记存入记忆
- 工具调用：猫猫可以使用 Claude Code 的工具（Read, Write, Edit, Bash 等）

Phase 1 升级：
- 持久化交互式会话：每只猫猫维护独立的持久进程
- 实时流式输出：支持 stdin/stdout 双向通信
- Session 管理：通过 --session-id 绑定会话上下文
"""

import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

from config import CAT_CONFIGS, CLI_TIMEOUT


# ── 交互式 CLI 配置 ──────────────────────────────────────

CLAUDE_CLI_PATH = os.getenv("CLAUDE_CLI_PATH", "claude")

# 交互式模式的基础 flags
INTERACTIVE_FLAGS = [
    "--output-format", "stream-json",
    "--verbose",
    "--dangerously-skip-permissions",
]


# ── 工具名称中文映射 ──────────────────────────────────────

TOOL_NAMES_CN = {
    "Read": "读取文件",
    "Write": "写入文件",
    "Edit": "编辑文件",
    "Bash": "执行命令",
    "Glob": "搜索文件",
    "Grep": "搜索内容",
    "WebSearch": "搜索网络",
    "WebFetch": "获取网页",
    "Task": "启动子任务",
}

# ── 工具图标映射 ──────────────────────────────────────

TOOL_ICONS = {
    "Read": "📖",
    "Write": "✏️",
    "Edit": "🔧",
    "Bash": "💻",
    "Glob": "🔍",
    "Grep": "🔎",
    "WebSearch": "🌐",
    "WebFetch": "📄",
    "Task": "🚀",
}


def _get_subprocess_env() -> dict:
    """获取 subprocess 环境变量，清除 CLAUDECODE 避免嵌套会话检测"""
    env = os.environ.copy()
    # 显式设为空字符串，确保子进程不会继承父进程的 CLAUDECODE
    env["CLAUDECODE"] = ""
    # 同时清除可能相关的其他变量
    env.pop("CLAUDE_CODE_SESSION", None)
    env.pop("ANTHROPIC_API_KEY", None)  # 让子进程用自己的配置
    # 增加 Node.js 流处理的缓冲区大小
    env["NODE_OPTIONS"] = "--max-old-space-size=4096"
    return env


def _parse_stream_json_line(line: str) -> Optional[dict]:
    """解析单行 JSON，失败返回 None"""
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _extract_tool_info(data: dict) -> Optional[tuple[str, str]]:
    """
    从 JSON 消息中提取工具信息
    返回 (工具名称, 工具描述) 或 None
    """
    msg_type = data.get("type")

    if msg_type == "assistant":
        message = data.get("message", {})
        content = message.get("content", [])
        if isinstance(content, list):
            for item in content:
                if item.get("type") == "tool_use":
                    tool_name = item.get("name", "未知工具")
                    tool_input = item.get("input", {})
                    # 构建简短描述
                    desc = ""
                    if tool_name == "Read":
                        desc = tool_input.get("file_path", "")[:50]
                    elif tool_name == "Write":
                        desc = tool_input.get("file_path", "")[:50]
                    elif tool_name == "Edit":
                        desc = tool_input.get("file_path", "")[:50]
                    elif tool_name == "Bash":
                        desc = tool_input.get("command", "")[:50]
                    elif tool_name == "Glob":
                        desc = tool_input.get("pattern", "")
                    elif tool_name == "Grep":
                        desc = tool_input.get("pattern", "")
                    return tool_name, desc

    return None


def _extract_tool_details(data: dict) -> Optional[dict]:
    """
    从 JSON 消息中提取完整工具信息
    返回 {"name": "Read", "input": {...}, "id": "xxx"} 或 None
    """
    if data.get("type") != "assistant":
        return None

    message = data.get("message", {})
    content = message.get("content", [])

    for item in content:
        if item.get("type") == "tool_use":
            return {
                "name": item.get("name"),
                "input": item.get("input", {}),
                "id": item.get("id"),
            }
    return None


def _extract_text_content(data: dict) -> Optional[str]:
    """从 assistant 消息中提取文本内容"""
    if data.get("type") != "assistant":
        return None

    message = data.get("message", {})
    content = message.get("content", [])

    for item in content:
        if item.get("type") == "text":
            return item.get("text", "")
    return None


def _extract_final_result(data: dict) -> Optional[str]:
    """
    从 result 类型消息中提取最终文本
    """
    if data.get("type") != "result":
        return None

    result = data.get("result", "")
    if isinstance(result, str):
        return result

    # result 可能是内容块列表
    if isinstance(result, list):
        texts = []
        for item in result:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts)

    return None


def extract_model_usage(data: dict) -> dict:
    """从 result 消息的 modelUsage 字段提取统计（合并所有模型）

    Args:
        data: stream-json 输出中的 JSON 对象

    Returns:
        包含 token 和费用信息的字典，如果不是 result 消息则返回空字典
    """
    if data.get("type") != "result":
        return {}

    model_usage = data.get("modelUsage", {})
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_creation = 0
    total_cost = 0

    for model_name, usage in model_usage.items():
        total_input += usage.get("inputTokens", 0)
        total_output += usage.get("outputTokens", 0)
        total_cache_read += usage.get("cacheReadInputTokens", 0)
        total_cache_creation += usage.get("cacheCreationInputTokens", 0)
        total_cost += usage.get("costUSD", 0)

    return {
        "inputTokens": total_input,
        "outputTokens": total_output,
        "cacheReadInputTokens": total_cache_read,
        "cacheCreationInputTokens": total_cache_creation,
        "costUSD": total_cost,
    }


def _parse_stream_json_output(raw: str) -> str:
    """
    解析完整的 stream-json 输出，提取最终结果文本
    """
    lines = raw.split("\n")
    final_text = ""

    for line in lines:
        data = _parse_stream_json_line(line)
        if not data:
            continue

        result = _extract_final_result(data)
        if result:
            final_text = result

    return final_text


from memory import (
    add_cat_memory,
    format_cat_memory_context,
    format_chat_context,
    format_user_profile_context,
    set_user_info,
)


def _extract_memories(text: str) -> tuple[str, list[str]]:
    """从回复中提取 [记住：xxx] 标记，返回（清理后文本, 记忆列表）"""
    memories = re.findall(r'\[记住[：:]\s*(.+?)\]', text)
    clean_text = re.sub(r'\s*\[记住[：:]\s*.+?\]', '', text).strip()
    return clean_text, memories


class CatAgent:
    """一只猫猫 Agent，封装 CLI 调用 + 记忆 + 群聊上下文

    Phase 1 升级：支持持久化交互式会话
    - 每只猫猫维护独立的持久进程（stdin/stdout PIPE）
    - 通过 session_id 绑定会话上下文
    - 支持实时流式输出
    """

    def __init__(self, cat_id: str):
        cfg = CAT_CONFIGS[cat_id]
        self.cat_id = cat_id
        self.name = cfg["name"]
        self.breed = cfg["breed"]
        self.role = cfg["role"]
        self.avatar = cfg["avatar"]
        self.description = cfg["description"]
        self.cli_cmd = cfg["cli_cmd"]
        self.last_usage_data: dict = {}  # 存储最后一次请求的使用统计

        # Phase 1: 持久化进程管理
        self.process: Optional[asyncio.subprocess.Process] = None
        self.session_id: str = f"meow-{cat_id}-{uuid.uuid4().hex[:8]}"
        self._is_interactive: bool = False  # 是否使用交互式模式
        self._lock = asyncio.Lock()  # 进程操作锁，防止并发问题

        prompt_file = cfg["prompt_file"]
        if Path(prompt_file).exists():
            self.personality = Path(prompt_file).read_text(encoding="utf-8")
        else:
            self.personality = f"你是{self.name}，一只{self.breed}。"

    def _build_group_prompt(self, session_id: str = "default") -> str:
        """构建群聊 prompt = 性格 + 记忆 + 用户画像 + 最近对话"""
        parts = [self.personality]

        # 猫猫记忆
        memory_ctx = format_cat_memory_context(self.cat_id)
        if memory_ctx:
            parts.append(f"\n\n【你的记忆】\n{memory_ctx}")

        # 用户画像
        profile_ctx = format_user_profile_context()
        if profile_ctx:
            parts.append(f"\n\n【{profile_ctx}】")

        # 最近对话历史
        chat_ctx = format_chat_context(session_id)
        if chat_ctx:
            parts.append(f"\n\n【最近的群聊记录】\n{chat_ctx}")

        parts.append(
            "\n\n【群聊回应规则】\n"
            "你在一个活跃的群聊中。\n\n"
            "- 有想法就直接回复\n"
            "- 不想参与这个话题 → 回复 [跳过]\n"
            "- 想听某只猫的看法 → 加 [问:stack] 或 [问:arch] 或 [问:pixel]\n"
            "- **觉得这个话题值得深入讨论** → 回复末尾加 [讨论]，其他猫猫会继续回应\n"
            "- 用户透露个人信息（名字、偏好等） → 加 [用户：key: value]\n"
        )

        return "\n".join(parts)

    def _clean_output(self, raw: str) -> str:
        """根据猫猫类型清洗输出（支持 stream-json 格式）"""
        # 检查是否有流处理错误（大文件/大响应）
        if "chunk is longer than limit" in raw:
            return f"（{self.name}处理的内容太大了喵，换个文件或者让我分批处理试试？）"

        # 首先尝试解析 stream-json 格式
        json_result = _parse_stream_json_output(raw)
        if json_result:
            return json_result.strip()

        return raw.strip()

    # ── Phase 1: 持久化交互式会话 ────────────────────────────

    async def _start_cli_process(self, cwd: Optional[str] = None) -> asyncio.subprocess.Process:
        """
        启动持久化 CLI 进程（如果尚未启动）
        返回进程对象
        """
        async with self._lock:
            if self.process and self.process.returncode is None:
                return self.process

            # 构建命令：使用 session-id 保持会话连续性
            cmd = [CLAUDE_CLI_PATH, "-p", *INTERACTIVE_FLAGS]

            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=_get_subprocess_env(),
            )
            # 增大缓冲区支持大文件
            if self.process.stdout:
                self.process.stdout._limit = 10 * 1024 * 1024  # 10MB

            self._is_interactive = True
            return self.process

    async def send_message(self, message: str, cwd: Optional[str] = None) -> AsyncIterator[str]:
        """
        交互式发送消息并实时流式读取响应

        Args:
            message: 用户消息/提示词
            cwd: 工作目录

        Yields:
            流式输出的文本片段
        """
        process = await self._start_cli_process(cwd)

        # 发送消息到 stdin（一次性模式：写入后关闭 stdin）
        # 注意：Claude Code CLI 的 -p 模式是单次交互，需要每次发送完整 prompt
        process.stdin.write(message.encode("utf-8"))
        process.stdin.close()

        accumulated_text = ""
        seen_tool_ids = set()
        final_result = ""

        async for line in process.stdout:
            line_str = line.decode("utf-8")

            data = _parse_stream_json_line(line_str)
            if not data:
                continue

            # 1. 提取并显示工具调用
            tool = _extract_tool_details(data)
            if tool:
                tool_id = tool.get("id")
                if tool_id and tool_id not in seen_tool_ids:
                    seen_tool_ids.add(tool_id)
                    yield self._format_tool_call(tool)

            # 2. 提取文本内容（增量）
            text = _extract_text_content(data)
            if text and text != accumulated_text:
                if text.startswith(accumulated_text):
                    new_text = text[len(accumulated_text):]
                    accumulated_text = text
                    if new_text:
                        yield new_text
                else:
                    accumulated_text = text
                    yield text

            # 3. 提取 result 类型的最终结果（兜底）
            result_text = _extract_final_result(data)
            if result_text:
                final_result = result_text

            # 4. 提取 modelUsage 统计数据
            usage = extract_model_usage(data)
            if usage:
                self.last_usage_data = usage

        # 如果没有从 assistant 消息获取到文本，使用 result 作为兜底
        if not accumulated_text and final_result:
            yield final_result
        elif not accumulated_text and not final_result:
            yield "（猫猫处理完了，但没有输出文本喵...）"

        # 进程结束，重置状态
        self._is_interactive = False
        self.process = None

    async def cleanup(self):
        """
        清理资源：终止进程、归档会话
        在会话结束或 handover 时调用
        """
        async with self._lock:
            if self.process and self.process.returncode is None:
                try:
                    self.process.terminate()
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
                except Exception:
                    pass
            self.process = None
            self._is_interactive = False

    def _format_tool_call(self, tool: dict) -> str:
        """格式化工具调用为友好显示"""
        name = tool.get("name", "未知工具")
        icon = TOOL_ICONS.get(name, "⚙️")
        input_data = tool.get("input", {})

        # 根据工具类型提取关键信息
        if name == "Read":
            path = input_data.get("file_path", "?")
            # 简化路径显示
            if len(path) > 50:
                path = "..." + path[-47:]
            return f"\n*{icon} 读取: {path}*\n"
        elif name == "Write":
            path = input_data.get("file_path", "?")
            if len(path) > 50:
                path = "..." + path[-47:]
            return f"\n*{icon} 写入: {path}*\n"
        elif name == "Edit":
            path = input_data.get("file_path", "?")
            if len(path) > 50:
                path = "..." + path[-47:]
            return f"\n*{icon} 编辑: {path}*\n"
        elif name == "Bash":
            cmd = input_data.get("command", "?")
            if len(cmd) > 60:
                cmd = cmd[:57] + "..."
            return f"\n*{icon} 执行: {cmd}*\n"
        elif name == "Glob":
            pattern = input_data.get("pattern", "?")
            return f"\n*{icon} 搜索文件: {pattern}*\n"
        elif name == "Grep":
            pattern = input_data.get("pattern", "?")
            return f"\n*{icon} 搜索内容: {pattern}*\n"
        elif name == "WebSearch":
            query = input_data.get("query", "?")
            if len(query) > 40:
                query = query[:37] + "..."
            return f"\n*{icon} 搜索网络: {query}*\n"
        elif name == "WebFetch":
            url = input_data.get("url", "?")
            if len(url) > 50:
                url = url[:47] + "..."
            return f"\n*{icon} 获取网页: {url}*\n"
        elif name == "Task":
            desc = input_data.get("description", "?")
            if len(desc) > 40:
                desc = desc[:37] + "..."
            return f"\n*{icon} 子任务: {desc}*\n"
        else:
            return f"\n*{icon} {name}*\n"

    def process_response(self, response: str) -> tuple[str, bool, list[str]]:
        """
        处理猫猫回复：提取记忆、提取用户信息、判断是否跳过、解析下一轮目标
        返回：(清理后文本, 是否应跳过, 下一轮目标列表)
        下一轮目标可能是 ["continue"] 或 ["stack", "arch"] 等
        """
        if not response:
            return "", True, []

        # 检查是否跳过
        if "[跳过]" in response or response.strip() == "跳过":
            return "", True, []

        # 提取下一轮目标标记
        next_targets = []
        for cat_id in ["arch", "stack", "pixel"]:
            if f"[问:{cat_id}]" in response.lower():
                next_targets.append(cat_id)

        # 清理标记和提取记忆
        clean_text = re.sub(r'\[讨论\]|\[问:\w+\]', '', response).strip()
        clean_text, memories = _extract_memories(clean_text)
        for mem in memories:
            add_cat_memory(self.cat_id, mem.strip(), importance=2)

        # 提取用户信息
        user_info = re.findall(r'\[用户[：:]\s*(\w+)[：:]\s*(.+?)\]', clean_text)
        for key, value in user_info:
            set_user_info(key.strip(), value.strip())

        # 清理用户信息标记
        clean_text = re.sub(r'\[用户[：:]\s*\w+[：:]\s*.+?\]', '', clean_text).strip()

        return clean_text, False, next_targets

    # ── 异步调用（主要方式）────────────────────────────

    async def chat_in_group(self, session_id: str = "default",
                            cwd: Optional[str] = None,
                            use_interactive: bool = True) -> str:
        """
        群聊模式：基于完整上下文生成回复

        Phase 1 升级：
        - use_interactive=True: 使用新的交互式模式
        - use_interactive=False: 使用原有的单次调用模式
        """
        prompt = self._build_group_prompt(session_id)

        # 更新 session_id 用于会话管理
        if session_id != "default":
            self.session_id = f"meow-{self.cat_id}-{session_id[:16]}"

        if use_interactive:
            # Phase 1: 使用新的交互式模式
            full = ""
            try:
                async for chunk in self.send_message(prompt, cwd):
                    full += chunk
                return full
            except FileNotFoundError:
                return f"（找不到 {CLAUDE_CLI_PATH} 命令，{self.name}的大脑还没装好喵...）"
            except Exception as e:
                return f"（{self.name}出了点状况喵：{e}）"

        # 原有的单次调用模式（fallback）
        cmd = list(self.cli_cmd)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=_get_subprocess_env(),
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=prompt.encode("utf-8")),
                timeout=CLI_TIMEOUT,
            )
            output = self._clean_output(stdout.decode("utf-8"))
            if not output and process.returncode != 0:
                err = stderr.decode("utf-8").strip()
                return f"（{self.name}遇到了一点问题喵...）\n{err[:300]}"
            return output if output else ""
        except asyncio.TimeoutError:
            return f"（{self.name}想了太久，超时了喵...）"
        except FileNotFoundError:
            return f"（找不到 {self.cli_cmd[0]} 命令，{self.name}的大脑还没装好喵...）"
        except Exception as e:
            return f"（{self.name}出了点状况喵：{e}）"

    async def chat_stream_in_group(self, session_id: str = "default",
                                    cwd: Optional[str] = None,
                                    use_interactive: bool = True) -> AsyncIterator[str]:
        """
        群聊模式的流式输出版本
        支持 stream-json 格式，显示工具调用进度和流式文本

        Phase 1 升级：
        - use_interactive=True: 使用新的交互式模式（支持 --resume 会话恢复）
        - use_interactive=False: 使用原有的单次调用模式
        """
        prompt = self._build_group_prompt(session_id)

        # 更新 session_id 用于会话管理
        if session_id != "default":
            # 为每个 Chainlit session 创建独立的 CLI session
            self.session_id = f"meow-{self.cat_id}-{session_id[:16]}"

        if use_interactive:
            # Phase 1: 使用新的交互式模式
            try:
                async for chunk in self.send_message(prompt, cwd):
                    yield chunk
                return
            except FileNotFoundError:
                yield f"（找不到 {CLAUDE_CLI_PATH} 命令喵...）\n"
                return
            except Exception as e:
                yield f"（{self.name}出了状况：{e}）\n"
                return

        # 原有的单次调用模式（fallback）
        try:
            process = await asyncio.create_subprocess_exec(
                *self.cli_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=_get_subprocess_env(),
            )

            process.stdout._limit = 10 * 1024 * 1024  # 10MB，支持大文件
            process.stdin.write(prompt.encode("utf-8"))
            process.stdin.close()

            accumulated_text = ""
            seen_tool_ids = set()
            final_result = ""  # 用于存储 result 类型的最终结果

            async for line in process.stdout:
                line_str = line.decode("utf-8")

                data = _parse_stream_json_line(line_str)
                if not data:
                    continue

                # 1. 提取并显示工具调用
                tool = _extract_tool_details(data)
                if tool:
                    tool_id = tool.get("id")
                    if tool_id and tool_id not in seen_tool_ids:
                        seen_tool_ids.add(tool_id)
                        yield self._format_tool_call(tool)

                # 2. 提取文本内容（如果有的话）
                text = _extract_text_content(data)
                if text and text != accumulated_text:
                    # 只 yield 新增的部分
                    if text.startswith(accumulated_text):
                        new_text = text[len(accumulated_text):]
                        accumulated_text = text
                        if new_text:
                            yield new_text
                    else:
                        # 文本完全不同，直接替换
                        accumulated_text = text
                        yield text

                # 3. 提取 result 类型的最终结果（兜底）
                result_text = _extract_final_result(data)
                if result_text:
                    final_result = result_text

                # 4. 提取 modelUsage 统计数据
                usage = extract_model_usage(data)
                if usage:
                    self.last_usage_data = usage

            # 4. 如果没有从 assistant 消息获取到文本，使用 result 作为兜底
            if not accumulated_text and final_result:
                yield final_result
            elif not accumulated_text and not final_result:
                yield "（猫猫处理完了，但没有输出文本喵...）"

        except FileNotFoundError:
            yield f"（找不到 {self.cli_cmd[0]} 命令喵...）\n"
        except Exception as e:
            yield f"（{self.name}出了状况：{e}）\n"

    def __repr__(self):
        return f"CatAgent({self.name} | {self.breed})"


# ── 实例化三只猫猫 ──────────────────────────────────────

arch = CatAgent("arch")
stack = CatAgent("stack")
pixel = CatAgent("pixel")

ALL_CATS = [arch, stack, pixel]
CAT_MAP = {c.cat_id: c for c in ALL_CATS}
