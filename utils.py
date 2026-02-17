"""
工具函数
"""

import os


def list_output_files(output_dir: str) -> list[str]:
    files = []
    for root, _, filenames in os.walk(output_dir):
        for f in filenames:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, output_dir)
            files.append(rel)
    return sorted(files)


def format_file_tree(output_dir: str) -> str:
    files = list_output_files(output_dir)
    if not files:
        return "（还没有文件喵）"
    lines = ["📁 output/"]
    for f in files:
        depth = f.count(os.sep)
        indent = "  " * (depth + 1)
        name = os.path.basename(f)
        icon = "📄" if "." in name else "📁"
        lines.append(f"{indent}{icon} {f}")
    return "\n".join(lines)
