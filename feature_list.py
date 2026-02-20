"""
Feature List —— 结构化功能列表管理

基于 Anthropic 文章的设计：
- 功能列表用 JSON 格式存储
- 每个功能有明确的步骤和 passes 状态
- 只能通过标记 passes: true 来标记完成
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from config import OUTPUT_DIR


@dataclass
class Feature:
    """单个功能"""
    id: str
    category: str = "functional"
    description: str = ""
    steps: list[str] = field(default_factory=list)
    passes: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Feature":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class FeatureList:
    """功能列表管理器"""

    def __init__(self, work_dir: Optional[str] = None):
        self.work_dir = Path(work_dir) if work_dir else OUTPUT_DIR
        self.file_path = self.work_dir / "feature_list.json"
        self.features: dict[str, Feature] = {}
        self._load()

    def _load(self):
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("features", []):
                        f = Feature.from_dict(item)
                        self.features[f.id] = f
            except Exception:
                self.features = {}

    def _save(self):
        self.work_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "features": [f.to_dict() for f in self.features.values()]
        }
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _next_id(self) -> str:
        if self.features:
            nums = [int(fid.split("-")[1]) for fid in self.features if fid.startswith("F-")]
            return f"F-{max(nums) + 1:03d}" if nums else "F-001"
        return "F-001"

    def add(self, description: str, steps: list[str] = None,
            category: str = "functional") -> Feature:
        """添加新功能"""
        fid = self._next_id()
        f = Feature(
            id=fid,
            category=category,
            description=description,
            steps=steps or [],
            passes=False,
        )
        self.features[fid] = f
        self._save()
        return f

    def mark_pass(self, feature_id: str, notes: str = "") -> bool:
        """标记功能通过测试"""
        f = self.features.get(feature_id)
        if f:
            f.passes = True
            f.notes = notes
            self._save()
            return True
        return False

    def get_next_pending(self) -> Optional[Feature]:
        """获取下一个待处理的功能"""
        for f in self.features.values():
            if not f.passes:
                return f
        return None

    def has_pending(self) -> bool:
        return any(not f.passes for f in self.features.values())

    def get_progress(self) -> tuple[int, int]:
        """返回 (已完成, 总数)"""
        total = len(self.features)
        done = sum(1 for f in self.features.values() if f.passes)
        return done, total

    def format_status(self) -> str:
        """格式化状态，用于展示"""
        if not self.features:
            return "功能列表为空"

        done, total = self.get_progress()
        lines = [f"**功能进度**: {done}/{total} 完成\n---"]

        for f in self.features.values():
            icon = "✅" if f.passes else "⏳"
            lines.append(f"{icon} **{f.id}**: {f.description}")
            if f.passes and f.notes:
                lines.append(f"   _{f.notes}_")

        return "\n".join(lines)

    def format_for_prompt(self) -> str:
        """格式化给 LLM 用的提示"""
        if not self.features:
            return ""

        lines = ["# 功能列表\n"]
        for f in self.features.values():
            status = "✅ PASS" if f.passes else "⏳ 待完成"
            lines.append(f"## {f.id}: {f.description} [{status}]")
            if f.steps:
                lines.append("测试步骤:")
                for i, step in enumerate(f.steps, 1):
                    lines.append(f"  {i}. {step}")
            lines.append("")

        return "\n".join(lines)


def create_from_requirement(requirement: str, work_dir: Optional[str] = None) -> FeatureList:
    """
    从需求文本创建初始功能列表（简化版）
    实际场景中由 Arch酱 通过 LLM 生成
    """
    fl = FeatureList(work_dir)

    # 简单解析：按行分割需求
    lines = [l.strip() for l in requirement.split("\n") if l.strip()]

    for i, line in enumerate(lines[:20], 1):  # 最多 20 个功能
        if line.startswith("- ") or line.startswith("* "):
            line = line[2:]
        if len(line) > 5:
            fl.add(
                description=line,
                steps=[f"验证: {line}"],
            )

    return fl
