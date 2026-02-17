"""
Git & GitHub 异步操作封装

所有 git / gh 命令通过 asyncio.subprocess 执行。
每个函数都接收 cwd 参数，可以操作 meowdev 本身或 output/ 目录。
"""

import asyncio
import re
from typing import Optional

from config import GIT_MAIN_BRANCH

# 单条命令超时（秒）
_CMD_TIMEOUT = 60


async def _run(
    cmd: list[str],
    cwd: str,
    input_data: Optional[str] = None,
    timeout: int = _CMD_TIMEOUT,
) -> tuple[int, str, str]:
    """执行命令，返回 (returncode, stdout, stderr)"""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if input_data else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await asyncio.wait_for(
        process.communicate(input=input_data.encode() if input_data else None),
        timeout=timeout,
    )
    return process.returncode, stdout.decode().strip(), stderr.decode().strip()


# ── 仓库初始化 ─────────────────────────────────────────────


async def ensure_git_repo(cwd: str) -> bool:
    """确保目录是一个 git 仓库，不是则执行 git init。返回是否新创建。"""
    rc, _, _ = await _run(["git", "rev-parse", "--is-inside-work-tree"], cwd)
    if rc == 0:
        return False
    rc, _, err = await _run(["git", "init"], cwd)
    if rc != 0:
        raise RuntimeError(f"git init 失败: {err}")
    return True


async def has_remote(cwd: str) -> bool:
    """检查是否已配置 remote origin"""
    rc, out, _ = await _run(["git", "remote", "get-url", "origin"], cwd)
    return rc == 0 and bool(out)


async def create_github_repo(name: str, cwd: str, private: bool = False) -> str:
    """用 gh 创建 GitHub 仓库并添加为 remote，返回仓库 URL"""
    visibility = "--private" if private else "--public"
    rc, out, err = await _run(
        ["gh", "repo", "create", name, visibility, "--source", ".", "--remote", "origin", "--push"],
        cwd,
    )
    if rc != 0:
        raise RuntimeError(f"创建 GitHub 仓库失败: {err}")
    return out.strip()


async def setup_repo_for_pr(cwd: str, repo_name: str = "meowdev-output") -> str:
    """
    确保目录可以走 PR 流程：git init + 初始 commit + GitHub remote。
    返回 remote URL（如果成功），空字符串表示无远程。
    """
    await ensure_git_repo(cwd)

    # 确保至少有一次 commit（否则无法创建分支）
    rc, _, _ = await _run(["git", "rev-parse", "HEAD"], cwd)
    if rc != 0:
        # 没有任何 commit，创建初始 commit
        await _run(["git", "add", "-A"], cwd)
        rc, _, err = await _run(
            ["git", "commit", "--allow-empty", "-m", "init: meowdev workspace"],
            cwd,
        )
        if rc != 0:
            raise RuntimeError(f"初始 commit 失败: {err}")

    # 确保有 remote origin
    if not await has_remote(cwd):
        url = await create_github_repo(repo_name, cwd, private=False)
        return url

    rc, url, _ = await _run(["git", "remote", "get-url", "origin"], cwd)
    return url


# ── 分支操作 ─────────────────────────────────────────────


async def create_branch(name: str, cwd: str) -> str:
    """创建并切换到新分支，返回分支名"""
    rc, _, err = await _run(["git", "checkout", "-b", name], cwd)
    if rc != 0:
        raise RuntimeError(f"创建分支失败: {err}")
    return name


async def current_branch(cwd: str) -> str:
    """获取当前分支名"""
    _, out, _ = await _run(["git", "branch", "--show-current"], cwd)
    return out


async def switch_to_main(cwd: str) -> str:
    """切回主分支并拉取最新代码"""
    main = GIT_MAIN_BRANCH
    await _run(["git", "checkout", main], cwd)
    await _run(["git", "pull", "origin", main], cwd)
    return main


# ── 提交 & 推送 ─────────────────────────────────────────────


async def commit_all(message: str, cwd: str) -> str:
    """git add -A && git commit，返回 commit 短哈希"""
    await _run(["git", "add", "-A"], cwd)
    rc, out, err = await _run(["git", "commit", "-m", message, "--allow-empty"], cwd)
    if rc != 0:
        raise RuntimeError(f"提交失败: {err}")
    _, hash_out, _ = await _run(["git", "rev-parse", "--short", "HEAD"], cwd)
    return hash_out


async def push_branch(cwd: str) -> str:
    """推送当前分支到 origin，返回分支名"""
    rc, _, err = await _run(["git", "push", "-u", "origin", "HEAD"], cwd)
    if rc != 0:
        raise RuntimeError(f"推送失败: {err}")
    return await current_branch(cwd)


# ── PR 操作 ─────────────────────────────────────────────


async def create_pr(title: str, body: str, cwd: str) -> tuple[str, int]:
    """创建 Pull Request，返回 (PR URL, PR 编号)"""
    rc, out, err = await _run(
        ["gh", "pr", "create", "--title", title, "--body", body],
        cwd,
    )
    if rc != 0:
        raise RuntimeError(f"创建 PR 失败: {err}")
    url = out.strip()
    match = re.search(r"/pull/(\d+)", url)
    pr_number = int(match.group(1)) if match else 0
    return url, pr_number


async def get_pr_diff(pr_number: int, cwd: str) -> str:
    """获取 PR 的 diff 内容"""
    rc, out, err = await _run(
        ["gh", "pr", "diff", str(pr_number)],
        cwd,
    )
    if rc != 0:
        raise RuntimeError(f"获取 diff 失败: {err}")
    return out


async def add_pr_review(pr_number: int, body: str, author_name: str, cwd: str):
    """以猫猫名义在 PR 上添加评论"""
    comment_body = f"**{author_name} (Review):**\n\n{body}"
    rc, _, err = await _run(
        ["gh", "pr", "comment", str(pr_number), "--body", comment_body],
        cwd,
    )
    if rc != 0:
        raise RuntimeError(f"添加评论失败: {err}")


async def merge_pr(pr_number: int, cwd: str) -> str:
    """合并 PR（squash），返回合并信息"""
    rc, out, err = await _run(
        ["gh", "pr", "merge", str(pr_number), "--squash", "--delete-branch"],
        cwd,
    )
    if rc != 0:
        raise RuntimeError(f"合并 PR 失败: {err}")
    return out or "PR 已合并"
