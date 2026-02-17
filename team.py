"""
MeowDevTeam —— 猫猫开发团队协作编排（Supervisor 模式）

协作流程（含 GitHub PR）：
1. 圆桌讨论 — 三只猫猫各抒己见、互相评价
2. Arch酱 输出架构方案
3. Pixel咪 设计 UI
4. Git: 创建 feature 分支
5. Stack喵 编写代码
6. Git: commit + push + 创建 PR
7. Arch酱 / Pixel咪 Review（基于 PR diff）
8. 循环修改直到 PASS
9. 等待用户 /merge 确认

设计要点：
- on_cat_speak 回调处理猫猫的 UI 展示（流式输出等），返回响应文本
- on_system 回调处理系统消息展示（Git 操作状态等）
- Git 操作失败不中断流程，仅跳过 PR 相关步骤
"""

import asyncio
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable, Optional

from cats import arch, stack, pixel, CatAgent
from config import BRANCH_PREFIX, MAX_REVIEW_ROUNDS, OUTPUT_DIR
from memory import add_message

import git_ops


class Phase(str, Enum):
    """协作阶段"""
    DISCUSS = "圆桌讨论"
    ANALYZE = "需求分析"
    DESIGN = "UI 设计"
    GIT_BRANCH = "创建分支"
    CODE = "代码编写"
    GIT_PR = "创建 PR"
    REVIEW_CODE = "代码审查"
    REVIEW_UI = "UI 审查"
    REVISE = "代码修改"
    GIT_UPDATE = "更新 PR"
    DONE = "完成"


@dataclass
class TeamMessage:
    """团队消息"""
    cat: Optional[CatAgent]
    phase: Phase
    content: str
    is_system: bool = False


@dataclass
class TeamSession:
    """一次协作会话的状态"""
    requirement: str
    session_id: str = "default"
    work_dir: str = ""
    branch_name: str = ""
    pr_url: str = ""
    pr_number: int = 0
    current_phase: Phase = Phase.DISCUSS
    review_round: int = 0


# 回调类型别名
CatSpeakCallback = Callable[[CatAgent, Phase, str], Awaitable[str]]
SystemCallback = Callable[[Phase, str], Awaitable[None]]


def _slugify(text: str) -> str:
    """把需求文本转为适合做分支名的 slug"""
    ascii_part = re.sub(r"[^\w\s-]", "", text[:30])
    slug = re.sub(r"[\s]+", "-", ascii_part).strip("-").lower()
    return slug or "feature"


class MeowDevTeam:
    """猫猫开发团队 —— 三只猫猫的协作编排器"""

    def __init__(self):
        self.arch = arch
        self.stack = stack
        self.pixel = pixel

    async def run(
        self,
        requirement: str,
        session_id: str = "default",
        work_dir: Optional[str] = None,
        on_cat_speak: Optional[CatSpeakCallback] = None,
        on_system: Optional[SystemCallback] = None,
    ) -> TeamSession:
        """
        执行完整协作流程。

        参数:
            on_cat_speak: async (cat, phase, task_description) -> response_text
                          外部回调负责展示猫猫发言（含流式输出），返回猫猫的回复文本。
            on_system:    async (phase, content) -> None
                          外部回调负责展示系统消息（Git 操作结果等）。
        """
        if work_dir is None:
            work_dir = str(OUTPUT_DIR)
        Path(work_dir).mkdir(parents=True, exist_ok=True)

        session = TeamSession(
            requirement=requirement,
            session_id=session_id,
            work_dir=work_dir,
        )

        async def cat_speak(cat: CatAgent, phase: Phase, task: str) -> str:
            """让猫猫发言：通过回调或直接调用 CLI"""
            if on_cat_speak:
                return await on_cat_speak(cat, phase, task)
            # 无回调时的默认行为（终端测试用）
            add_message("system", f"[{cat.name}的任务] {task}", session_id)
            response = await cat.chat_in_group(session_id, cwd=work_dir)
            clean_text, _ = cat.process_response(response)
            result = clean_text or response
            add_message(cat.name, result, session_id)
            return result

        async def system_msg(phase: Phase, content: str):
            """发送系统消息"""
            if on_system:
                await on_system(phase, content)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 阶段 0: 圆桌讨论 — 三只猫猫各抒己见
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        session.current_phase = Phase.DISCUSS
        await system_msg(Phase.DISCUSS, "**💬 圆桌讨论**\n---")

        for cat in [self.arch, self.stack, self.pixel]:
            await cat_speak(
                cat, Phase.DISCUSS,
                f"用户提出了一个开发需求：「{requirement}」\n"
                f"请从你的专业角度（{cat.role}）简短发表看法（3-5句）。",
            )

        for cat in [self.stack, self.pixel]:
            await cat_speak(
                cat, Phase.DISCUSS,
                "听了其他猫猫的看法，你有什么补充或不同意见？简短回应即可（2-3句）。",
            )

        await cat_speak(
            self.arch, Phase.DISCUSS,
            "综合大家的讨论，简短总结一下最终方案方向（2-3句）。",
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 阶段 1: Arch酱 输出架构方案
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        session.current_phase = Phase.ANALYZE
        await system_msg(Phase.ANALYZE, "**📐 架构设计**\n---")

        await cat_speak(
            self.arch, Phase.ANALYZE,
            f"请输出正式的架构方案，包含技术栈、模块划分、文件结构。\n需求：{requirement}",
        )

        await cat_speak(
            self.stack, Phase.ANALYZE,
            "看了 Arch酱 的架构方案，从实现角度简短说说你的看法（2-3句）。",
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 阶段 2: Pixel咪 设计 UI
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        session.current_phase = Phase.DESIGN
        await system_msg(Phase.DESIGN, "**🎨 UI 设计**\n---")

        await cat_speak(
            self.pixel, Phase.DESIGN,
            "根据架构方案设计 UI 方案，包含配色（色值）、布局、关键交互。",
        )

        await cat_speak(
            self.stack, Phase.DESIGN,
            "看了 Pixel咪 的 UI 设计方案，从实现角度简短说说有没有难点（1-2句）。",
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 阶段 2.5: 初始化 Git 仓库 + 创建 feature 分支
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        session.current_phase = Phase.GIT_BRANCH
        slug = _slugify(requirement)
        branch_name = f"{BRANCH_PREFIX}{slug}-{int(time.time())}"
        try:
            await git_ops.setup_repo_for_pr(work_dir)
            await git_ops.create_branch(branch_name, work_dir)
            session.branch_name = branch_name
            await system_msg(Phase.GIT_BRANCH, f"**🌿 已创建分支** `{branch_name}`")
        except Exception as e:
            await system_msg(
                Phase.GIT_BRANCH,
                f"⚠️ 创建分支失败（{e}），将在本地继续开发",
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 阶段 3: Stack喵 编写代码
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        session.current_phase = Phase.CODE
        await system_msg(Phase.CODE, "**💻 开始编码**\n---")

        await cat_speak(
            self.stack, Phase.CODE,
            f"根据架构方案和 UI 设计，在当前目录中生成完整的项目代码。\n需求：{requirement}",
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 阶段 3.5: Commit + Push + 创建 PR
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        session.current_phase = Phase.GIT_PR
        if session.branch_name:
            try:
                commit_hash = await git_ops.commit_all(
                    f"feat: {requirement[:50]}", work_dir,
                )
                await git_ops.push_branch(work_dir)
                pr_url, pr_number = await git_ops.create_pr(
                    f"feat: {requirement[:80]}",
                    f"## 需求\n{requirement}\n\n*由 Stack喵 实现，等待 Arch酱 & Pixel咪 Review*",
                    work_dir,
                )
                session.pr_url = pr_url
                session.pr_number = pr_number
                await system_msg(Phase.GIT_PR, f"**🔗 PR 已创建:** {pr_url}")
            except Exception as e:
                await system_msg(
                    Phase.GIT_PR,
                    f"⚠️ PR 创建失败（{e}），将继续本地 Review",
                )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 阶段 4: 代码审查（循环）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        await system_msg(Phase.REVIEW_CODE, "**📝 代码审查**\n---")

        for round_num in range(1, MAX_REVIEW_ROUNDS + 1):
            session.current_phase = Phase.REVIEW_CODE
            session.review_round = round_num

            review_task = (
                "审查代码质量，给出你的评价。"
                "通过请在回复中包含 PASS，否则列出最重要的修改意见（最多3条）。"
            )
            if session.pr_number:
                try:
                    diff = await git_ops.get_pr_diff(session.pr_number, work_dir)
                    if diff:
                        truncated = diff[:3000]
                        review_task += f"\n\nPR Diff:\n```\n{truncated}\n```"
                except Exception:
                    pass

            review = await cat_speak(self.arch, Phase.REVIEW_CODE, review_task)

            if session.pr_number:
                try:
                    await git_ops.add_pr_review(
                        session.pr_number, review, self.arch.name, work_dir,
                    )
                except Exception:
                    pass

            if "PASS" in review.upper():
                await cat_speak(
                    self.pixel, Phase.REVIEW_CODE,
                    "Arch酱 通过了代码审查！你也来看看，说两句感想（1-2句，可以夸 Stack喵）。",
                )
                break

            await cat_speak(
                self.stack, Phase.REVIEW_CODE,
                f"Arch酱 的审查意见如下，简短回应（1-2句），然后修改代码。\n\n审查意见：{review}",
            )

            session.current_phase = Phase.REVISE
            await cat_speak(
                self.stack, Phase.REVISE,
                f"根据审查意见修改代码：\n{review}",
            )

            if session.branch_name:
                session.current_phase = Phase.GIT_UPDATE
                try:
                    await git_ops.commit_all(
                        f"fix: 根据 review 修改 (round {round_num})", work_dir,
                    )
                    await git_ops.push_branch(work_dir)
                    await system_msg(
                        Phase.GIT_UPDATE,
                        f"**🔄 PR 已更新** (第 {round_num} 轮修改)",
                    )
                except Exception as e:
                    await system_msg(
                        Phase.GIT_UPDATE, f"⚠️ 更新 PR 失败（{e}）",
                    )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 阶段 5: Pixel咪 UI 审查
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        session.current_phase = Phase.REVIEW_UI
        ui_review_task = (
            "从 UI/UX 角度审查代码，给出你的评价。"
            "通过请回复包含 PASS，否则给出具体修改建议。"
        )
        ui_review = await cat_speak(self.pixel, Phase.REVIEW_UI, ui_review_task)

        if session.pr_number:
            try:
                await git_ops.add_pr_review(
                    session.pr_number, ui_review, self.pixel.name, work_dir,
                )
            except Exception:
                pass

        if "PASS" not in ui_review.upper():
            await cat_speak(
                self.stack, Phase.REVIEW_UI,
                f"Pixel咪 对 UI 不太满意，意见如下。简短回应（1-2句），然后修改。\n\n{ui_review}",
            )

            session.current_phase = Phase.REVISE
            await cat_speak(
                self.stack, Phase.REVISE,
                f"根据 Pixel咪 的 UI 审查意见修改前端代码：\n{ui_review}",
            )

            if session.branch_name:
                try:
                    await git_ops.commit_all("fix: UI 修改", work_dir)
                    await git_ops.push_branch(work_dir)
                    await system_msg(Phase.GIT_UPDATE, "**🔄 PR 已更新** (UI 修改)")
                except Exception:
                    pass

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 完成
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        session.current_phase = Phase.DONE
        return session


# ── 终端测试 ────────────────────────────────────────────────

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
            print(f"📌 {content}")
            print(f"{'='*60}\n")

        async def on_cat_speak(cat, phase, task):
            add_message("system", f"[{cat.name}的任务] {task}", "cli-test")
            response = await cat.chat_in_group("cli-test")
            clean_text, _ = cat.process_response(response)
            result = clean_text or response
            add_message(cat.name, result, "cli-test")
            print(f"\n{'='*60}")
            print(f"🏷️  阶段：{phase.value}")
            print(f"🐱 {cat.name}（{cat.role}）：")
            print(f"{'-'*60}")
            print(result)
            print(f"{'='*60}\n")
            return result

        session = await team.run(
            requirement,
            session_id="cli-test",
            on_cat_speak=on_cat_speak,
            on_system=on_system,
        )

        print(f"\n✅ 协作完成！")
        if session.pr_url:
            print(f"🔗 PR: {session.pr_url}")
        print(f"📁 生成文件：\n{format_file_tree(session.work_dir)}")

    asyncio.run(main())
