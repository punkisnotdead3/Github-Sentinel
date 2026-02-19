#!/usr/bin/env python3
"""
GitHub Sentinel - 交互式 REPL 入口
"""

import logging
import re
import threading

from config import load_config
from subscription import SubscriptionManager
from github_client import GitHubClient
from llm import LLMReporter
from notifier import FileNotifier
from scheduler import SentinelScheduler

logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sentinel")

HELP_TEXT = """
可用命令：
  run                  立即抓取所有订阅仓库并生成 AI 摘要报告
  schedule             在后台启动定时调度（按 settings.yaml 中的时间执行）
  list                 查看当前订阅列表
  add <owner/repo>     添加仓库订阅，例如：add microsoft/vscode
  remove <owner/repo>  移除仓库订阅，例如：remove microsoft/vscode
  help                 显示帮助信息
  exit / quit          退出程序
"""


def build_components(config: dict):
    sub_manager = SubscriptionManager(config["subscriptions_file"])
    gh_client = GitHubClient(config["github"]["token"])
    reporter = LLMReporter(
        api_key=config["llm"]["api_key"],
        model=config["llm"]["model"],
        max_tokens=config["llm"]["max_tokens"],
    )
    notifier = FileNotifier(config["report"]["output_dir"])
    return sub_manager, gh_client, reporter, notifier


def run_once(config: dict):
    sub_manager, gh_client, reporter, notifier = build_components(config)
    subscriptions = sub_manager.list_subscriptions()

    if not subscriptions:
        print("[警告] 订阅列表为空，请先用 add <owner/repo> 添加仓库")
        return

    days = 7 if config["scheduler"]["interval"] == "weekly" else 1
    print(f"[开始] 抓取 {len(subscriptions)} 个仓库的近 {days} 天更新...")

    all_updates = []
    for sub in subscriptions:
        label = sub.get("label", f"{sub['owner']}/{sub['repo']}")
        print(f"  → 正在获取 {label} ...")
        try:
            updates = gh_client.fetch_updates(sub, days=days)
            all_updates.append(updates)
            print(f"     获取到 {len(updates['items'])} 条更新")
        except Exception as e:
            print(f"[错误] 获取 {label} 失败：{e}")

    if not all_updates:
        print("[警告] 所有仓库获取失败，请检查 GitHub Token 和网络连接")
        return

    print("\n[AI] 正在生成摘要报告...")
    for updates in all_updates:
        label = updates.get("label", f"{updates['owner']}/{updates['repo']}")
        repo_slug = f"{updates['owner']}_{updates['repo']}"
        print(f"  → 正在为 {label} 生成摘要报告...")
        report = reporter.generate_report(updates)
        notifier.send(report, title=f"{label} 报告", repo_slug=repo_slug)
    print("[完成] 所有报告生成成功！")


def start_schedule(config: dict):
    interval = config["scheduler"]["interval"]
    time_str = config["scheduler"]["time"]
    scheduler = SentinelScheduler(interval=interval, time_str=time_str)
    # 在后台线程中运行，不阻塞 REPL
    t = threading.Thread(target=scheduler.start, args=(lambda: run_once(config),), daemon=True)
    t.start()


def parse_repo_arg(arg: str):
    """解析 owner/repo 或完整 GitHub URL，返回 (owner, repo) 或 None"""
    arg = arg.strip()
    # 匹配完整 URL：https://github.com/owner/repo 或 github.com/owner/repo
    match = re.search(r"github\.com/([^/]+)/([^/\s]+)", arg)
    if match:
        return match.group(1), match.group(2).rstrip("/")
    # 匹配 owner/repo 格式
    parts = arg.strip("/").split("/")
    if len(parts) == 2 and all(parts):
        return parts[0], parts[1]
    return None



def repl(config: dict):
    print("=" * 50)
    print("  GitHub Sentinel - 交互式控制台")
    print("  输入 help 查看可用命令")
    print("=" * 50)

    while True:
        try:
            raw = input("\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[退出] Bye!")
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("exit", "quit"):
            print("[退出] Bye!")
            break

        elif cmd == "help":
            print(HELP_TEXT)

        elif cmd == "list":
            sub_manager = SubscriptionManager(config["subscriptions_file"])
            sub_manager.display()

        elif cmd == "add":
            parsed = parse_repo_arg(arg)
            if not parsed:
                print("[错误] 格式：add <owner/repo> 或 add <GitHub URL>")
                print("  例如：add microsoft/vscode")
                print("  例如：add https://github.com/microsoft/vscode")
                continue
            owner, repo = parsed
            sub_manager = SubscriptionManager(config["subscriptions_file"])
            sub_manager.add_subscription(owner, repo)

        elif cmd == "remove":
            parsed = parse_repo_arg(arg)
            if not parsed:
                print("[错误] 格式：remove <owner/repo> 或 remove <GitHub URL>")
                continue
            owner, repo = parsed
            sub_manager = SubscriptionManager(config["subscriptions_file"])
            sub_manager.remove_subscription(owner, repo)

        elif cmd == "run":
            run_once(config)

        elif cmd == "schedule":
            start_schedule(config)

        else:
            print(f"[未知命令] '{cmd}'，输入 help 查看可用命令")


if __name__ == "__main__":
    config = load_config()
    repl(config)
