"""
工具函数 —— 代码提取、文件操作、验证
"""

import ast
import os
import re
from pathlib import Path
from typing import Optional


def extract_code_blocks(text: str) -> list[dict]:
    """从 LLM 输出中提取代码块"""
    pattern = r"```(\w*)\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    return [{"language": lang or "text", "code": code.strip()} for lang, code in matches]


def validate_python(code: str) -> tuple[bool, Optional[str]]:
    """验证 Python 代码语法"""
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, f"语法错误: 第{e.lineno}行 - {e.msg}"


def save_code_to_file(code: str, filepath: str) -> bool:
    """保存代码到文件，自动创建目录"""
    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code, encoding="utf-8")
        return True
    except Exception as e:
        print(f"保存文件失败: {e}")
        return False


def list_output_files(output_dir: str) -> list[str]:
    """列出输出目录中的所有文件"""
    files = []
    for root, _, filenames in os.walk(output_dir):
        for f in filenames:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, output_dir)
            files.append(rel)
    return sorted(files)


def format_file_tree(output_dir: str) -> str:
    """格式化文件树（用于界面展示）"""
    files = list_output_files(output_dir)
    if not files:
        return "（还没有文件喵）"

    lines = [f"📁 output/"]
    for f in files:
        depth = f.count(os.sep)
        indent = "  " * (depth + 1)
        name = os.path.basename(f)
        icon = "📄" if "." in name else "📁"
        lines.append(f"{indent}{icon} {f}")
    return "\n".join(lines)


def truncate_text(text: str, max_length: int = 2000) -> str:
    """截断过长文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"\n\n... (已截断，共 {len(text)} 字符)"
