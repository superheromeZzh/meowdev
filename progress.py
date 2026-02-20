"""
Progress —— 进度记录管理

简单的 Markdown 格式进度文件，替代复杂的 SQLite 记忆系统。
遵循 Anthropic 文章的设计：每个 Coding Agent 会话结束写进度记录。
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from config import OUTPUT_DIR


class Progress:
    """进度记录管理器"""

    def __init__(self, work_dir: Optional[str] = None):
        self.work_dir = Path(work_dir) if work_dir else OUTPUT_DIR
        self.file_path = self.work_dir / "progress.md"

    def _read(self) -> str:
        if self.file_path.exists():
            return self.file_path.read_text(encoding="utf-8")
        return ""

    def _write(self, content: str):
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(content, encoding="utf-8")

    def append(self, content: str, author: str = "System"):
        """追加进度记录"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n## {timestamp} - {author}\n{content}\n"

        existing = self._read()
        if not existing.startswith("# "):
            existing = "# MeowDev 进度记录\n---" + existing

        # 插入到 --- 之后
        if "---\n" in existing:
            parts = existing.split("---\n", 1)
            new_content = parts[0] + "---\n" + entry + parts[1]
        else:
            new_content = existing + entry

        self._write(new_content)

    def log_feature_done(self, feature_id: str, description: str, cat_name: str):
        """记录功能完成"""
        self.append(
            f"- ✅ **{feature_id}** 完成: {description}\n  _by {cat_name}_",
            cat_name
        )

    def log_review(self, feature_id: str, result: str, cat_name: str):
        """记录 Review 结果"""
        status = "✅ PASS" if "PASS" in result.upper() else "🔄 需修改"
        self.append(
            f"- {status} **{feature_id}** Review\n  {result[:200]}",
            cat_name
        )

    def log_error(self, error: str, cat_name: str = "System"):
        """记录错误"""
        self.append(f"- ❌ 错误: {error}", cat_name)

    def get_recent(self, lines: int = 50) -> str:
        """获取最近的进度记录"""
        content = self._read()
        if not content:
            return ""

        all_lines = content.split("\n")
        return "\n".join(all_lines[-lines:])

    def get_context_for_prompt(self, max_entries: int = 10) -> str:
        """获取给 LLM 的上下文"""
        content = self._read()
        if not content:
            return "（暂无进度记录）"

        # 按条目分割（## 开头）
        entries = content.split("\n## ")
        recent = entries[:max_entries + 1]  # +1 因为第一个是标题

        return "## " + "\n## ".join(recent[1:]) if len(recent) > 1 else "（暂无进度记录）"

    def clear(self):
        """清空进度"""
        self._write("# MeowDev 进度记录\n---\n")
