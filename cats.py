"""
CatAgent 类 —— 每只猫猫的大脑

核心改进：
- 群聊感知：每只猫猫都能看到完整的对话历史
- 记忆系统：猫猫记得用户的偏好和过往对话
- 自动提取 [记住：xxx] 标记存入记忆
"""

import asyncio
import re
from pathlib import Path
from typing import AsyncIterator, Optional

from config import CAT_CONFIGS, CLI_TIMEOUT
from memory import (
    add_cat_memory,
    format_cat_memory_context,
    format_chat_context,
    format_user_profile_context,
    set_user_info,
)


def _clean_codex_output(raw: str) -> str:
    """清洗 codex exec 输出，去除元数据头尾"""
    lines = raw.split("\n")
    codex_idx = -1
    for i, line in enumerate(lines):
        if line.strip() == "codex":
            codex_idx = i
    if codex_idx >= 0:
        result_lines = []
        for line in lines[codex_idx + 1:]:
            if line.strip().startswith("tokens used"):
                break
            result_lines.append(line)
        cleaned = "\n".join(result_lines).strip()
        if cleaned:
            return cleaned
    # fallback
    in_body = False
    header_passed = 0
    result_lines = []
    for line in lines:
        if line.strip() == "--------":
            header_passed += 1
            if header_passed >= 2:
                in_body = True
            continue
        if in_body:
            if line.strip().startswith("tokens used"):
                break
            if line.strip() in ("user", "") or line.strip().startswith("mcp startup"):
                continue
            if line.strip().startswith("thinking"):
                continue
            result_lines.append(line)
    cleaned = "\n".join(result_lines).strip()
    return cleaned if cleaned else raw.strip()


def _extract_memories(text: str) -> tuple[str, list[str]]:
    """从回复中提取 [记住：xxx] 标记，返回（清理后文本, 记忆列表）"""
    memories = re.findall(r'\[记住[：:]\s*(.+?)\]', text)
    clean_text = re.sub(r'\s*\[记住[：:]\s*.+?\]', '', text).strip()
    return clean_text, memories


class CatAgent:
    """一只猫猫 Agent，封装 CLI 调用 + 记忆 + 群聊上下文"""

    def __init__(self, cat_id: str):
        cfg = CAT_CONFIGS[cat_id]
        self.cat_id = cat_id
        self.name = cfg["name"]
        self.breed = cfg["breed"]
        self.role = cfg["role"]
        self.avatar = cfg["avatar"]
        self.description = cfg["description"]
        self.cli_cmd = cfg["cli_cmd"]
        self.cli_cmd_full_auto = cfg.get("cli_cmd_full_auto")

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
            "\n\n请基于以上对话上下文，自然地回复。"
            "如果觉得这个话题不太需要你参与，可以简短回应甚至不回复（回复 [跳过] 即可）。"
            "不要重复别人说过的内容。"
        )

        return "\n".join(parts)

    def _clean_output(self, raw: str) -> str:
        """根据猫猫类型清洗输出"""
        if self.cat_id == "stack":
            return _clean_codex_output(raw)
        return raw.strip()

    def process_response(self, response: str) -> tuple[str, bool]:
        """
        处理猫猫回复：提取记忆、判断是否跳过
        返回：(清理后文本, 是否应跳过)
        """
        if not response:
            return "", True

        # 检查是否跳过
        if "[跳过]" in response or response.strip() == "跳过":
            return "", True

        # 提取记忆
        clean_text, memories = _extract_memories(response)
        for mem in memories:
            add_cat_memory(self.cat_id, mem.strip(), importance=2)

        return clean_text, False

    # ── 异步调用（主要方式）────────────────────────────

    async def chat_in_group(self, session_id: str = "default",
                            cwd: Optional[str] = None) -> str:
        """群聊模式：基于完整上下文生成回复"""
        prompt = self._build_group_prompt(session_id)
        cmd = list(self.cli_cmd)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
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
                                    cwd: Optional[str] = None) -> AsyncIterator[str]:
        """群聊模式的流式输出版本"""
        prompt = self._build_group_prompt(session_id)
        cmd = list(self.cli_cmd)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            process.stdin.write(prompt.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()

            if self.cat_id == "stack":
                raw_output = ""
                while True:
                    try:
                        line = await asyncio.wait_for(
                            process.stdout.readline(), timeout=CLI_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        break
                    if not line:
                        break
                    raw_output += line.decode("utf-8")
                await process.wait()
                cleaned = self._clean_output(raw_output)
                if cleaned:
                    yield cleaned
            else:
                while True:
                    try:
                        line = await asyncio.wait_for(
                            process.stdout.readline(), timeout=CLI_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        yield f"\n（{self.name}想了太久喵...）\n"
                        break
                    if not line:
                        break
                    yield line.decode("utf-8")

                await process.wait()

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
