"""
CatAgent 类 —— 每只猫猫的大脑

核心能力：
- 群聊感知：看到完整对话历史 + 其他猫猫发言
- 记忆系统：跨会话记住用户偏好
- 任务看板：通过共享任务列表协调工作
- 额度降级：Stack喵额度耗尽时，Arch酱 CLI 临时代劳
"""

import asyncio
import re
from pathlib import Path
from typing import AsyncIterator, Optional

from config import CAT_CONFIGS, CLI_TIMEOUT, FALLBACK_CLI, QUOTA_ERROR_KEYWORDS
from memory import (
    add_cat_memory,
    format_cat_memory_context,
    format_chat_context,
    format_user_profile_context,
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
    """从回复中提取 [记住：xxx] 标记"""
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

        fallback = FALLBACK_CLI.get(cat_id)
        self.fallback_cli_cmd = fallback["cli_cmd"] if fallback else None
        self.fallback_helper = fallback["helper_name"] if fallback else None
        self._using_fallback = False

        prompt_file = cfg["prompt_file"]
        if Path(prompt_file).exists():
            self.personality = Path(prompt_file).read_text(encoding="utf-8")
        else:
            self.personality = f"你是{self.name}，一只{self.breed}。"

    # ── Prompt 构建 ────────────────────────────────────

    def _build_group_prompt(self, session_id: str = "default",
                            task_board_text: str = "") -> str:
        """构建群聊 prompt = 性格 + 记忆 + 用户画像 + 对话历史 + 任务看板"""
        parts = [self.personality]

        memory_ctx = format_cat_memory_context(self.cat_id)
        if memory_ctx:
            parts.append(f"\n\n【你的记忆】\n{memory_ctx}")

        profile_ctx = format_user_profile_context()
        if profile_ctx:
            parts.append(f"\n\n【{profile_ctx}】")

        chat_ctx = format_chat_context(session_id)
        if chat_ctx:
            parts.append(f"\n\n【最近的群聊记录】\n{chat_ctx}")

        if task_board_text:
            parts.append(f"\n\n【任务看板】\n{task_board_text}")

        parts.append(
            "\n\n请基于以上对话上下文回复。不要重复别人说过的内容。\n\n"
            "你可以在回复中使用任务指令来协调团队工作：\n"
            "- [新任务：标题] — 拆解出一个待办任务\n"
            "- [认领：T-xxx] — 认领一个待办任务，然后开始工作\n"
            "- [完成：T-xxx] — 你完成了某个任务\n"
            "- [空闲] — 当前没有需要你做的事了\n"
            "普通聊天直接回复即可，只在有具体工作要推进时使用任务指令。\n\n"
            "重要：绝对不要让用户手动执行命令或操作。"
            "遇到问题自己解决，解决不了就叫其他猫猫帮忙。"
        )

        return "\n".join(parts)

    # ── 输出清洗 ───────────────────────────────────────

    def _clean_output(self, raw: str) -> str:
        if self.cat_id == "stack":
            return _clean_codex_output(raw)
        return raw.strip()

    def _is_quota_error(self, output: str) -> bool:
        if not output:
            return False
        return any(kw in output.lower() for kw in QUOTA_ERROR_KEYWORDS)

    def process_response(self, response: str) -> tuple[str, bool]:
        """处理回复：提取记忆、判断是否跳过。返回 (文本, 是否跳过)。"""
        if not response:
            return "", True
        if "[跳过]" in response or response.strip() == "跳过":
            return "", True
        clean_text, memories = _extract_memories(response)
        for mem in memories:
            add_cat_memory(self.cat_id, mem.strip(), importance=2)
        return clean_text, False

    # ── CLI 调用 ───────────────────────────────────────

    async def _call_cli(self, cmd: list, prompt: str,
                        cwd: Optional[str] = None) -> tuple[str, bool]:
        """执行 CLI，返回 (输出, 是否出错)。"""
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
                return stderr.decode("utf-8").strip()[:500], True
            return output or "", False
        except asyncio.TimeoutError:
            return f"（{self.name}想了太久，超时了喵...）", True
        except FileNotFoundError:
            return f"（找不到 {cmd[0]} 命令喵...）", True
        except Exception as e:
            return f"（{self.name}出了点状况：{e}）", True

    async def _call_with_fallback(self, prompt: str,
                                  cwd: Optional[str] = None) -> str:
        """调用主 CLI，额度耗尽时自动降级到备用 CLI。"""
        output, err = await self._call_cli(self.cli_cmd, prompt, cwd)

        if err and self._is_quota_error(output) and self.fallback_cli_cmd:
            self._using_fallback = True
            fb_prompt = (
                f"你正在临时帮助 {self.name}（{self.role}）。"
                f"请保持 {self.name} 的说话风格。\n\n" + prompt
            )
            output, err = await self._call_cli(self.fallback_cli_cmd, fb_prompt, cwd)
            if output and not err:
                output = f"*（{self.fallback_helper}临时帮 {self.name} 回答~）*\n\n{output}"
            self._using_fallback = False

        return output

    # ── 群聊调用（非流式 / 流式）─────────────────────

    async def chat_in_group(self, session_id: str = "default",
                            cwd: Optional[str] = None,
                            task_board_text: str = "") -> str:
        prompt = self._build_group_prompt(session_id, task_board_text)
        return await self._call_with_fallback(prompt, cwd)

    async def chat_stream_in_group(self, session_id: str = "default",
                                    cwd: Optional[str] = None,
                                    task_board_text: str = "") -> AsyncIterator[str]:
        prompt = self._build_group_prompt(session_id, task_board_text)
        cmd = list(self.cli_cmd)
        collected = ""
        stream_failed = False

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
                raw = ""
                while True:
                    try:
                        line = await asyncio.wait_for(
                            process.stdout.readline(), timeout=CLI_TIMEOUT)
                    except asyncio.TimeoutError:
                        break
                    if not line:
                        break
                    raw += line.decode("utf-8")
                await process.wait()
                cleaned = self._clean_output(raw)
                if cleaned:
                    collected = cleaned
                    yield cleaned
                else:
                    err = (await process.stderr.read()).decode("utf-8")
                    if self._is_quota_error(raw + err):
                        stream_failed = True
            else:
                while True:
                    try:
                        line = await asyncio.wait_for(
                            process.stdout.readline(), timeout=CLI_TIMEOUT)
                    except asyncio.TimeoutError:
                        stream_failed = True
                        break
                    if not line:
                        break
                    decoded = line.decode("utf-8")
                    collected += decoded
                    yield decoded
                await process.wait()
                if process.returncode != 0 and not collected.strip():
                    err = (await process.stderr.read()).decode("utf-8")
                    if self._is_quota_error(err):
                        stream_failed = True

        except FileNotFoundError:
            yield f"（找不到 {self.cli_cmd[0]} 命令喵...）\n"
            return
        except Exception as e:
            yield f"（{self.name}出了状况：{e}）\n"
            return

        if stream_failed and self.fallback_cli_cmd:
            self._using_fallback = True
            fb_prompt = (
                f"你正在临时帮助 {self.name}（{self.role}）。"
                f"请保持 {self.name} 的说话风格。\n\n" + prompt
            )
            output, _ = await self._call_cli(self.fallback_cli_cmd, fb_prompt, cwd)
            self._using_fallback = False
            if output:
                yield f"*（{self.fallback_helper}临时帮 {self.name} 回答~）*\n\n{output}"

    def __repr__(self):
        return f"CatAgent({self.name} | {self.breed})"


# ── 实例化 ────────────────────────────────────────────

arch = CatAgent("arch")
stack = CatAgent("stack")
pixel = CatAgent("pixel")

ALL_CATS = [arch, stack, pixel]
CAT_MAP = {c.cat_id: c for c in ALL_CATS}
