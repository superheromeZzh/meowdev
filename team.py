"""
MeowDevTeam —— 猫猫开发团队协作编排（重构版）

基于 Anthropic "Effective harnesses for long-running agents" 设计：

工作流：
1. Initializer 阶段 — 设置环境、创建 feature_list.json
2. Coding 循环 — 每次处理一个 feature，增量进展
3. Review 阶段 — 验证功能，通过才标记 passes: true
4. 完成 — 所有 feature 通过

核心原则：
- 增量进展：一次只做一个 feature
- 保持干净：每个阶段结束提交 git、写进度
- 测试驱动：只有测试通过才标记完成
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable, Optional

from cats import arch, stack, pixel, CatAgent
from config import MAX_REVIEW_ROUNDS, OUTPUT_DIR
from feature_list import FeatureList, Feature
from progress import Progress
from initializer import initialize_project


class Phase(str, Enum):
    """协作阶段"""
    INIT = "初始化"
    ANALYZE = "需求分析"
    FEATURE_LIST = "功能拆解"
    DESIGN = "UI 设计"
    CODE = "编码实现"
    REVIEW = "代码审查"
    TEST = "功能测试"
    DONE = "完成"


@dataclass
class TeamSession:
    """一次协作会话的状态"""
    requirement: str
    session_id: str = "default"
    work_dir: str = ""
    current_phase: Phase = Phase.INIT
    current_feature: Optional[Feature] = None
    review_round: int = 0


# 回调类型
CatSpeakCallback = Callable[[CatAgent, Phase, str], Awaitable[str]]
SystemCallback = Callable[[Phase, str], Awaitable[None]]


class MeowDevTeam:
    """猫猫开发团队 —— 增量进展模式"""

    # 前端相关关键词
    FRONTEND_KEYWORDS = [
        "界面", "ui", "页面", "按钮", "表单", "显示", "样式", "布局",
        "交互", "输入框", "弹窗", "导航", "菜单", "列表", "卡片",
        "颜色", "字体", "动画", "响应式", "移动端", "web",
    ]

    def __init__(self):
        self.arch = arch
        self.stack = stack
        self.pixel = pixel
        self.feature_list: Optional[FeatureList] = None
        self.progress: Optional[Progress] = None

    def _is_frontend_feature(self, description: str) -> bool:
        """判断功能是否涉及前端 UI"""
        desc_lower = description.lower()
        return any(kw in desc_lower for kw in self.FRONTEND_KEYWORDS)

    async def run(
        self,
        requirement: str,
        session_id: str = "default",
        work_dir: Optional[str] = None,
        on_cat_speak: Optional[CatSpeakCallback] = None,
        on_system: Optional[SystemCallback] = None,
    ) -> TeamSession:
        """
        执行完整协作流程（增量进展模式）
        """
        if work_dir is None:
            work_dir = str(OUTPUT_DIR)
        Path(work_dir).mkdir(parents=True, exist_ok=True)

        session = TeamSession(
            requirement=requirement,
            session_id=session_id,
            work_dir=work_dir,
        )

        # 初始化管理器
        self.feature_list = FeatureList(work_dir)
        self.progress = Progress(work_dir)

        async def cat_speak(cat: CatAgent, phase: Phase, task: str) -> str:
            if on_cat_speak:
                return await on_cat_speak(cat, phase, task)
            response = await cat.chat_in_group(session_id, cwd=work_dir)
            clean_text, _ = cat.process_response(response)
            return clean_text or response

        async def sys_msg(phase: Phase, content: str):
            if on_system:
                await on_system(phase, content)
            self.progress.append(content, "System")

        # ════════════════════════════════════════════════════════
        # 阶段 1: 初始化项目
        # ════════════════════════════════════════════════════════
        session.current_phase = Phase.INIT
        await sys_msg(Phase.INIT, "**🚀 项目初始化**\n---")

        init_result = await initialize_project(requirement, work_dir)
        await sys_msg(Phase.INIT, f"✅ 创建了 {len(init_result['files'])} 个文件")

        # ════════════════════════════════════════════════════════
        # 阶段 2: Arch酱 分析需求 + 拆解功能
        # ════════════════════════════════════════════════════════
        session.current_phase = Phase.ANALYZE
        await sys_msg(Phase.ANALYZE, "**📐 需求分析** — Arch酱 主导\n---")

        analysis = await cat_speak(
            self.arch, Phase.ANALYZE,
            f"分析以下需求，给出技术方案和架构设计：\n\n{requirement}"
        )

        # 功能拆解
        session.current_phase = Phase.FEATURE_LIST
        await sys_msg(Phase.FEATURE_LIST, "**📋 功能拆解**\n---")

        feature_prompt = f"""基于需求拆解出 3-8 个具体功能点，每个功能一行，格式：
- 功能描述

需求：{requirement}

直接输出功能列表，不要其他内容。"""
        features_text = await cat_speak(self.arch, Phase.FEATURE_LIST, feature_prompt)

        # 解析并添加功能
        for line in features_text.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                desc = line[2:].strip()
            elif line and not line.startswith("#"):
                desc = line
            else:
                continue
            if len(desc) > 5:
                self.feature_list.add(
                    description=desc,
                    steps=[f"验证: {desc}"],
                )

        done, total = self.feature_list.get_progress()
        await sys_msg(Phase.FEATURE_LIST, f"✅ 拆解出 {total} 个功能")

        # ════════════════════════════════════════════════════════
        # 阶段 3: 增量编码循环（核心！）
        # ════════════════════════════════════════════════════════
        while self.feature_list.has_pending():
            feature = self.feature_list.get_next_pending()
            if not feature:
                break

            session.current_feature = feature
            session.current_phase = Phase.CODE

            await sys_msg(Phase.CODE,
                f"**💻 编码实现** — {feature.id}: {feature.description}\n---")

            # 前端功能：Pixel咪 先给 UI 设计建议
            ui_context = ""
            if self._is_frontend_feature(feature.description):
                ui_design = await cat_speak(
                    self.pixel, Phase.DESIGN,
                    f"为功能「{feature.description}」给出简洁的 UI 设计建议：\n"
                    "1. 布局结构\n"
                    "2. 关键交互\n"
                    "3. 视觉要点\n\n"
                    "2-3 句话即可。"
                )
                ui_context = f"\n\n【Pixel咪 的 UI 建议】\n{ui_design}"

            # Stack喵 编码
            code_prompt = f"""实现功能：{feature.description}{ui_context}

已完成的进度：
{self.progress.get_context_for_prompt(5)}

剩余功能：
{self.feature_list.format_for_prompt()}

要求：
1. 只实现当前这一个功能
2. 实现完成后简要说明做了什么
3. 不要实现其他功能"""
            await cat_speak(self.stack, Phase.CODE, code_prompt)

            # Review 循环
            session.current_phase = Phase.REVIEW
            passed = False

            for round_num in range(1, MAX_REVIEW_ROUNDS + 1):
                session.review_round = round_num

                # Arch酱 代码审查
                review_prompt = f"""审查功能 {feature.id}: {feature.description}

审查要点：
1. 功能是否正确实现
2. 代码质量是否合格
3. 是否有明显的 bug

通过请回复包含 PASS，否则给出修改意见（最多 2 条）。"""

                review = await cat_speak(self.arch, Phase.REVIEW, review_prompt)
                self.progress.log_review(feature.id, review, self.arch.name)

                if "PASS" in review.upper():
                    # Pixel咪 UI 审查（前端相关功能）
                    if self._is_frontend_feature(feature.description):
                        ui_review = await cat_speak(
                            self.pixel, Phase.REVIEW,
                            f"从 UI/UX 角度审查：{feature.description}\n\n"
                            "关注点：交互是否友好、视觉是否美观。\n"
                            "通过请回复 PASS，否则给出建议。"
                        )
                        if "PASS" not in ui_review.upper():
                            await cat_speak(
                                self.stack, Phase.CODE,
                                f"根据 Pixel咪 的 UI 审查意见修改：\n{ui_review}"
                            )
                    passed = True
                    break

                # Stack喵 修改
                session.current_phase = Phase.CODE
                await cat_speak(
                    self.stack, Phase.CODE,
                    f"根据审查意见修改：\n{review}"
                )

            # 标记功能状态
            if passed:
                self.feature_list.mark_pass(feature.id, f"Review 通过 ({session.review_round} 轮)")
                self.progress.log_feature_done(feature.id, feature.description, self.stack.name)

                done, total = self.feature_list.get_progress()
                await sys_msg(Phase.REVIEW,
                    f"✅ **{feature.id}** 完成 ({done}/{total})")
            else:
                await sys_msg(Phase.REVIEW,
                    f"⚠️ **{feature.id}** 未能通过 Review")

        # ════════════════════════════════════════════════════════
        # 阶段 4: 完成
        # ════════════════════════════════════════════════════════
        session.current_phase = Phase.DONE
        done, total = self.feature_list.get_progress()

        if done == total:
            await sys_msg(Phase.DONE,
                f"**🎉 项目完成！**\n\n所有 {total} 个功能已实现并通过审查。\n\n运行：`./init.sh && python app.py`")
        else:
            await sys_msg(Phase.DONE,
                f"**⚠️ 项目部分完成**\n\n完成 {done}/{total} 个功能。")

        return session


# ═════════════════════════════════════════════════════════════
# 终端测试
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from utils import format_file_tree

    async def main():
        requirement = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "帮我做一个 TODO 管理助手"
        print(f"\n🐱 MeowDev 猫猫开发团队启动！")
        print(f"📋 需求：{requirement}\n")

        team = MeowDevTeam()

        async def on_system(phase, content):
            print(f"\n{'='*60}")
            print(f"📌 [{phase.value}] {content}")
            print(f"{'='*60}\n")

        async def on_cat_speak(cat, phase, task):
            print(f"\n---")
            print(f"🐱 {cat.name}（{cat.role}）")
            print(f"---")
            response = await cat.chat_in_group("cli-test")
            clean_text, _ = cat.process_response(response)
            result = clean_text or response
            print(result)
            return result

        session = await team.run(
            requirement,
            session_id="cli-test",
            on_cat_speak=on_cat_speak,
            on_system=on_system,
        )

        print(f"\n✅ 协作完成！")
        print(f"📁 生成文件：\n{format_file_tree(session.work_dir)}")

        if team.feature_list:
            print(f"\n{team.feature_list.format_status()}")

    asyncio.run(main())
