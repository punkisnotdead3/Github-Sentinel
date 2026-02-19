#!/usr/bin/env python3
"""
GitHub Sentinel - 命令行入口

用法示例：
  python main.py run              # 立即执行一次抓取并生成报告
  python main.py schedule         # 启动定时调度模式
  python main.py list             # 查看订阅列表
  python main.py add owner/repo   # 添加订阅
  python main.py remove owner/repo # 移除订阅
"""

import argparse
import logging
import sys

from config import load_config
from subscription import SubscriptionManager
from github_client import GitHubClient
from llm import LLMReporter
from notifier import FileNotifier
from scheduler import SentinelScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sentinel")


def build_components(config: dict):
    """根据配置实例化各个组件"""
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
    """立即执行一次：抓取所有订阅更新 → AI 生成报告 → 保存文件"""
    sub_manager, gh_client, reporter, notifier = build_components(config)
    subscriptions = sub_manager.list_subscriptions()

    if not subscriptions:
        print("[警告] 订阅列表为空，请先使用 `add` 命令添加仓库")
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
            logger.error(f"获取 {label} 失败：{e}")

    if not all_updates:
        print("[警告] 所有仓库获取失败，请检查 GitHub Token 和网络连接")
        return

    print("\n[AI] 正在生成摘要报告...")
    digest = reporter.generate_digest(all_updates)

    notifier.send(digest)
    print("[完成] 报告生成成功！")


def cmd_schedule(config: dict):
    """启动定时调度"""
    interval = config["scheduler"]["interval"]
    time_str = config["scheduler"]["time"]
    scheduler = SentinelScheduler(interval=interval, time_str=time_str)
    scheduler.start(lambda: run_once(config))


def cmd_list(config: dict):
    sub_manager = SubscriptionManager(config["subscriptions_file"])
    sub_manager.display()


def cmd_add(config: dict, repo_path: str):
    parts = repo_path.strip("/").split("/")
    if len(parts) != 2:
        print(f"[错误] 格式应为 owner/repo，收到：{repo_path}")
        sys.exit(1)
    owner, repo = parts
    sub_manager = SubscriptionManager(config["subscriptions_file"])
    sub_manager.add_subscription(owner, repo)


def cmd_remove(config: dict, repo_path: str):
    parts = repo_path.strip("/").split("/")
    if len(parts) != 2:
        print(f"[错误] 格式应为 owner/repo，收到：{repo_path}")
        sys.exit(1)
    owner, repo = parts
    sub_manager = SubscriptionManager(config["subscriptions_file"])
    sub_manager.remove_subscription(owner, repo)


def main():
    parser = argparse.ArgumentParser(
        description="GitHub Sentinel - GitHub 仓库动态自动监控与 AI 摘要工具"
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="立即执行一次抓取并生成报告")
    subparsers.add_parser("schedule", help="启动定时调度模式")
    subparsers.add_parser("list", help="查看当前订阅列表")

    add_parser = subparsers.add_parser("add", help="添加订阅仓库")
    add_parser.add_argument("repo", help="格式：owner/repo")

    remove_parser = subparsers.add_parser("remove", help="移除订阅仓库")
    remove_parser.add_argument("repo", help="格式：owner/repo")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    config = load_config()

    if args.command == "run":
        run_once(config)
    elif args.command == "schedule":
        cmd_schedule(config)
    elif args.command == "list":
        cmd_list(config)
    elif args.command == "add":
        cmd_add(config, args.repo)
    elif args.command == "remove":
        cmd_remove(config, args.repo)


if __name__ == "__main__":
    main()
