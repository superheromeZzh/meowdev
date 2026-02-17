"""
MeowDev 配置文件
三只猫猫的 CLI 命令模板 & 项目设置
"""

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent

# Prompt 文件目录
PROMPTS_DIR = BASE_DIR / "prompts"

# 猫猫生成代码的输出目录
OUTPUT_DIR = BASE_DIR / "output"

# 头像目录
AVATARS_DIR = BASE_DIR / "public" / "avatars"

# ── 三只猫猫的 CLI 配置 ──────────────────────────────────
#
# prompt 通过 stdin 传入，避免命令行过长或特殊字符转义问题
# cli_cmd:  基础命令 + 参数（不含 prompt）
# cli_cmd_full_auto:  codex 全自动模式（可直接写文件）
#

CAT_CONFIGS = {
    "arch": {
        "name": "Arch酱",
        "breed": "波斯猫",
        "role": "首席架构师",
        "avatar": "arch.png",
        "prompt_file": PROMPTS_DIR / "arch.txt",
        # Claude Code CLI: -p 模式下无 prompt 参数时自动从 stdin 读取
        "cli_cmd": ["claude", "-p", "--output-format", "text", "--no-session-persistence"],
        "description": "高冷严谨的架构师，负责需求分析和代码审查",
    },
    "stack": {
        "name": "Stack喵",
        "breed": "橘猫",
        "role": "全栈工程师",
        "avatar": "stack.png",
        "prompt_file": PROMPTS_DIR / "stack.txt",
        # Codex CLI: prompt 通过 stdin 传入（- 表示从 stdin 读取）
        "cli_cmd": ["codex", "exec", "--skip-git-repo-check", "-"],
        # 全自动模式（可直接写文件）
        "cli_cmd_full_auto": ["codex", "exec", "--skip-git-repo-check", "--full-auto", "-"],
        "description": "热情话痨的全栈工程师，负责代码实现",
    },
    "pixel": {
        "name": "Pixel咪",
        "breed": "三花猫",
        "role": "UI/UX 设计师",
        "avatar": "pixel.png",
        "prompt_file": PROMPTS_DIR / "pixel.txt",
        # Kimi CLI: --print 非交互, --final-message-only 只输出最终回复
        "cli_cmd": ["kimi", "--print", "--final-message-only"],
        "description": "文艺感性的设计师，负责 UI 设计和视觉审查",
    },
}

# ── 协作流程配置 ──────────────────────────────────────────

# Review 最大循环次数
MAX_REVIEW_ROUNDS = 3

# CLI 调用超时（秒） -- claude + GLM-5 较慢，给足时间
CLI_TIMEOUT = 600

# 流式输出刷新间隔（秒）
STREAM_INTERVAL = 0.1

# ── Git / GitHub 配置 ────────────────────────────────────

GIT_MAIN_BRANCH = "main"
PR_AUTO_MERGE = False        # 是否跳过用户确认自动合并
BRANCH_PREFIX = "feat/"      # feature 分支前缀
