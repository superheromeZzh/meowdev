"""
MeowDev 配置文件（简化版）

- 三只猫猫的 CLI 命令配置
- 项目设置
"""

from pathlib import Path

BASE_DIR = Path(__file__).parent
PROMPTS_DIR = BASE_DIR / "prompts"
OUTPUT_DIR = BASE_DIR / "output"

# ── 三只猫猫的 CLI 配置 ──────────────────────────────────

CAT_CONFIGS = {
    "arch": {
        "name": "Arch酱",
        "breed": "波斯猫",
        "role": "首席架构师",
        "avatar": "arch.png",
        "prompt_file": PROMPTS_DIR / "arch.txt",
        "cli_cmd": [
            "claude", "-p",
            "--verbose",
            "--output-format", "stream-json",
            "--dangerously-skip-permissions",
        ],
        "description": "高冷严谨的架构师，负责需求分析和代码审查",
    },
    "stack": {
        "name": "Stack喵",
        "breed": "橘猫",
        "role": "全栈工程师",
        "avatar": "stack.png",
        "prompt_file": PROMPTS_DIR / "stack.txt",
        "cli_cmd": [
            "claude", "-p",
            "--verbose",
            "--output-format", "stream-json",
            "--dangerously-skip-permissions",
        ],
        "description": "热情话痨的全栈工程师，负责代码实现",
    },
    "pixel": {
        "name": "Pixel咪",
        "breed": "三花猫",
        "role": "UI/UX 设计师",
        "avatar": "pixel.png",
        "prompt_file": PROMPTS_DIR / "pixel.txt",
        "cli_cmd": [
            "claude", "-p",
            "--verbose",
            "--output-format", "stream-json",
            "--dangerously-skip-permissions",
        ],
        "description": "文艺感性的设计师，负责 UI 设计和视觉审查",
    },
}


CLI_TIMEOUT = 600
MAX_REVIEW_ROUNDS = 3
