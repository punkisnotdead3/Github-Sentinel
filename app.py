#!/usr/bin/env python3
"""
GitHub Sentinel - Gradio Web UI 入口
"""

import logging
import logging.handlers
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import gradio as gr

from config import load_config
from subscription import SubscriptionManager
from github_client import GitHubClient
from llm import LLMReporter
from notifier import FileNotifier
from scheduler import SentinelScheduler

# --------------------------------------------------------------------------- #
# 日志配置（与 main.py 相同，共享同一日志文件）
# --------------------------------------------------------------------------- #
_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_file_handler = logging.handlers.RotatingFileHandler(
    _LOG_DIR / "sentinel.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=7,
    encoding="utf-8",
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.WARNING)
_console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

logging.basicConfig(level=logging.DEBUG, handlers=[_file_handler, _console_handler])
logger = logging.getLogger("sentinel.app")

# --------------------------------------------------------------------------- #
# 全局配置与调度器状态
# --------------------------------------------------------------------------- #
config = load_config()

_scheduler_obj: "SentinelScheduler | None" = None
_scheduler_thread: "threading.Thread | None" = None


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #

def parse_repo_arg(arg: str):
    """解析 owner/repo 或完整 GitHub URL，返回 (owner, repo) 或 None"""
    arg = arg.strip()
    match = re.search(r"github\.com/([^/]+)/([^/\s]+)", arg)
    if match:
        return match.group(1), match.group(2).rstrip("/")
    parts = arg.strip("/").split("/")
    if len(parts) == 2 and all(parts):
        return parts[0], parts[1]
    return None


def _build_components():
    sub_manager = SubscriptionManager(config["subscriptions_file"])
    gh_client = GitHubClient(config["github"]["token"])
    reporter = LLMReporter(
        api_key=config["llm"]["api_key"],
        model=config["llm"]["model"],
        max_tokens=config["llm"]["max_tokens"],
    )
    notifier = FileNotifier(config["report"]["output_dir"])
    return sub_manager, gh_client, reporter, notifier


_ALL_REPOS = "全部（所有订阅仓库）"


def _get_repo_choices() -> list[str]:
    """返回仓库选择列表，格式：'标签 (owner/repo)'"""
    sub_manager = SubscriptionManager(config["subscriptions_file"])
    subs = sub_manager.list_subscriptions()
    choices = [_ALL_REPOS] + [
        f"{s.get('label', s['owner'] + '/' + s['repo'])}  ({s['owner']}/{s['repo']})"
        for s in subs
    ]
    return choices


def _parse_repo_choice(choice: str):
    """从 '标签 (owner/repo)' 格式解析出 (owner, repo)，返回 None 表示全部"""
    if not choice or choice == _ALL_REPOS:
        return None
    m = re.search(r'\(([^/]+)/([^)]+)\)\s*$', choice)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None


# --------------------------------------------------------------------------- #
# Tab 1: 订阅管理
# --------------------------------------------------------------------------- #

def _subs_to_rows(subs):
    return [
        [
            s.get("label", f"{s['owner']}/{s['repo']}"),
            f"{s['owner']}/{s['repo']}",
            ", ".join(s.get("track", [])),
        ]
        for s in subs
    ]


def refresh_subscriptions():
    sub_manager = SubscriptionManager(config["subscriptions_file"])
    rows = _subs_to_rows(sub_manager.list_subscriptions())
    return rows


def _refresh_repo_dropdown():
    return gr.update(choices=_get_repo_choices(), value=_ALL_REPOS)


def add_subscription(repo_str: str, label: str, track_types: list):
    repo_str = repo_str.strip()
    if not repo_str:
        return "请输入仓库地址", refresh_subscriptions(), _refresh_repo_dropdown()
    parsed = parse_repo_arg(repo_str)
    if not parsed:
        return "格式错误，请输入 owner/repo 或完整 GitHub URL", refresh_subscriptions(), _refresh_repo_dropdown()
    owner, repo = parsed
    track = track_types if track_types else ["releases", "issues", "pull_requests"]
    sub_manager = SubscriptionManager(config["subscriptions_file"])
    subs = sub_manager.list_subscriptions()
    for s in subs:
        if s["owner"] == owner and s["repo"] == repo:
            return f"已存在：{owner}/{repo}", _subs_to_rows(subs), _refresh_repo_dropdown()
    sub_manager.add_subscription(owner, repo, label=label.strip(), track=track)
    return f"已添加：{owner}/{repo}", refresh_subscriptions(), _refresh_repo_dropdown()


def remove_subscription(repo_str: str):
    repo_str = repo_str.strip()
    if not repo_str:
        return "请输入要移除的仓库地址", refresh_subscriptions(), _refresh_repo_dropdown()
    parsed = parse_repo_arg(repo_str)
    if not parsed:
        return "格式错误，请输入 owner/repo 或完整 GitHub URL", refresh_subscriptions(), _refresh_repo_dropdown()
    owner, repo = parsed
    sub_manager = SubscriptionManager(config["subscriptions_file"])
    before = len(sub_manager.list_subscriptions())
    sub_manager.remove_subscription(owner, repo)
    after = len(sub_manager.list_subscriptions())
    if after < before:
        return f"已移除：{owner}/{repo}", refresh_subscriptions(), _refresh_repo_dropdown()
    return f"未找到：{owner}/{repo}", refresh_subscriptions(), _refresh_repo_dropdown()


# --------------------------------------------------------------------------- #
# Tab 2: 立即运行（流式生成器）
# --------------------------------------------------------------------------- #

def run_and_stream(selected_repo: str):
    """
    Generator: yields (log_text, report_markdown, download_file).
    download_file 在最后一次 yield 时才会设置为实际路径。
    """
    log_lines = []
    combined_report = ""

    sub_manager, gh_client, reporter, notifier = _build_components()
    all_subs = sub_manager.list_subscriptions()

    # 根据选择过滤仓库
    parsed = _parse_repo_choice(selected_repo)
    if parsed is None:
        subscriptions = all_subs
    else:
        owner, repo = parsed
        subscriptions = [s for s in all_subs if s["owner"] == owner and s["repo"] == repo]

    if not subscriptions:
        yield "⚠ 订阅列表为空，请先在「订阅管理」中添加仓库", "", None
        return

    days = 7 if config["scheduler"]["interval"] == "weekly" else 1
    scope = f"「{selected_repo}」" if parsed else f"全部 {len(subscriptions)} 个仓库"
    log_lines.append(f"开始抓取 {scope} 的近 {days} 天更新...")
    yield "\n".join(log_lines), combined_report, None

    all_updates = []
    for sub in subscriptions:
        label = sub.get("label", f"{sub['owner']}/{sub['repo']}")
        log_lines.append(f"→ 正在获取 {label} ...")
        yield "\n".join(log_lines), combined_report, None
        try:
            updates = gh_client.fetch_updates(sub, days=days)
            all_updates.append(updates)
            log_lines.append(f"  ✓ {label}：{len(updates['items'])} 条更新")
        except Exception as e:
            log_lines.append(f"  ✗ {label} 获取失败：{e}")
        yield "\n".join(log_lines), combined_report, None

    if not all_updates:
        log_lines.append("所有仓库获取失败，请检查 GitHub Token 和网络连接")
        yield "\n".join(log_lines), combined_report, None
        return

    log_lines.append("\n正在调用 AI 生成摘要报告...")
    yield "\n".join(log_lines), combined_report, None

    saved_paths = []
    for updates in all_updates:
        label = updates.get("label", f"{updates['owner']}/{updates['repo']}")
        repo_slug = f"{updates['owner']}_{updates['repo']}"
        log_lines.append(f"→ 正在为 {label} 生成报告...")
        yield "\n".join(log_lines), combined_report, None

        try:
            report = reporter.generate_report(updates)
            saved_path = notifier.send(report, title=f"{label} 报告", repo_slug=repo_slug)
            saved_paths.append(saved_path)
            combined_report += f"# {label}\n\n{report}\n\n---\n\n"
            log_lines.append(f"  ✓ {label} 报告已生成并保存")
        except Exception as e:
            log_lines.append(f"  ✗ {label} 报告生成失败：{e}")
        yield "\n".join(log_lines), combined_report, None

    log_lines.append("\n✅ 所有报告生成完成！")

    # 生成可供下载的文件
    download_path = None
    if saved_paths:
        if len(saved_paths) == 1:
            download_path = saved_paths[0]
        else:
            # 多个仓库 → 生成合并文件
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_dir = Path(config["report"]["output_dir"])
            digest_path = output_dir / f"digest_{ts}.md"
            digest_path.write_text(combined_report, encoding="utf-8")
            download_path = str(digest_path)
            log_lines.append(f"合并报告已写入：{digest_path.name}")

    yield "\n".join(log_lines), combined_report, download_path


# --------------------------------------------------------------------------- #
# Tab 3: 历史报告
# --------------------------------------------------------------------------- #

def list_reports() -> list[str]:
    output_dir = Path(config["report"]["output_dir"])
    if not output_dir.exists():
        return []
    files = sorted(output_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(f) for f in files]


def refresh_report_list():
    files = list_reports()
    if not files:
        return gr.update(choices=[], value=None), "（暂无报告）", None
    content = Path(files[0]).read_text(encoding="utf-8")
    return gr.update(choices=files, value=files[0]), content, files[0]


def view_report(file_path: str):
    if not file_path:
        return "（未选择报告）", None
    p = Path(file_path)
    if not p.exists():
        return "（文件不存在）", None
    return p.read_text(encoding="utf-8"), file_path


# --------------------------------------------------------------------------- #
# Tab 4: 定时调度
# --------------------------------------------------------------------------- #

def _scheduler_status() -> str:
    if _scheduler_thread and _scheduler_thread.is_alive():
        interval = config["scheduler"]["interval"]
        time_str = config["scheduler"]["time"]
        return f"✅ 运行中（{interval}，每次 {time_str}）"
    return "⏹ 未运行"


def get_scheduler_info() -> tuple[str, str]:
    interval = config["scheduler"]["interval"]
    time_str = config["scheduler"]["time"]
    cfg_text = f"执行频率：{'每天' if interval == 'daily' else '每周一'}  |  执行时间：{time_str}"
    return cfg_text, _scheduler_status()


def start_scheduler():
    global _scheduler_obj, _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return _scheduler_status()

    interval = config["scheduler"]["interval"]
    _scheduler_obj = SentinelScheduler(
        interval=interval,
        time_str=config["scheduler"]["time"],
    )

    def _job():
        _, gh_client, reporter, notifier = _build_components()
        sub_manager = SubscriptionManager(config["subscriptions_file"])
        days = 7 if interval == "weekly" else 1
        for sub in sub_manager.list_subscriptions():
            try:
                updates = gh_client.fetch_updates(sub, days=days)
                label = updates.get("label", f"{updates['owner']}/{updates['repo']}")
                repo_slug = f"{updates['owner']}_{updates['repo']}"
                report = reporter.generate_report(updates)
                notifier.send(report, title=f"{label} 报告", repo_slug=repo_slug)
            except Exception as e:
                logger.error("调度任务失败 %s/%s: %s", sub["owner"], sub["repo"], e)

    _scheduler_thread = threading.Thread(
        target=_scheduler_obj.start, args=(_job,), daemon=True
    )
    _scheduler_thread.start()
    return _scheduler_status()


def stop_scheduler():
    global _scheduler_obj, _scheduler_thread
    if _scheduler_obj is not None:
        try:
            _scheduler_obj._scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler_obj = None
    return _scheduler_status()


# --------------------------------------------------------------------------- #
# Gradio UI
# --------------------------------------------------------------------------- #

with gr.Blocks(title="GitHub Sentinel", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# GitHub Sentinel\n> 自动追踪 GitHub 仓库动态，AI 生成中文摘要报告")

    with gr.Tabs():

        # ------------------------------------------------------------------ #
        # Tab 1: 订阅管理
        # ------------------------------------------------------------------ #
        with gr.Tab("订阅管理"):
            sub_table = gr.Dataframe(
                headers=["标签", "仓库", "跟踪类型"],
                value=refresh_subscriptions,
                interactive=False,
                label="当前订阅列表",
            )
            sub_msg = gr.Textbox(label="操作结果", interactive=False)

            with gr.Row():
                repo_input = gr.Textbox(
                    label="仓库地址",
                    placeholder="owner/repo 或 https://github.com/owner/repo",
                    scale=3,
                )
                label_input = gr.Textbox(
                    label="展示标签（可选）",
                    placeholder="例如：VS Code",
                    scale=2,
                )

            track_input = gr.CheckboxGroup(
                choices=["releases", "issues", "pull_requests"],
                value=["releases", "issues", "pull_requests"],
                label="跟踪类型",
            )

            with gr.Row():
                add_btn = gr.Button("添加订阅", variant="primary")
                remove_btn = gr.Button("移除订阅", variant="stop")
                refresh_sub_btn = gr.Button("刷新列表")

        # ------------------------------------------------------------------ #
        # Tab 2: 立即运行
        # ------------------------------------------------------------------ #
        with gr.Tab("立即运行"):
            with gr.Row():
                repo_selector = gr.Dropdown(
                    label="选择仓库",
                    choices=_get_repo_choices(),
                    value=_ALL_REPOS,
                    scale=4,
                )
                refresh_run_btn = gr.Button("刷新列表", scale=1)

            run_btn = gr.Button("立即运行", variant="primary", size="lg")
            run_log = gr.Textbox(
                label="运行日志",
                lines=10,
                interactive=False,
                placeholder="点击「立即运行」开始...",
            )
            run_report = gr.Markdown(label="生成的报告")
            run_download = gr.File(label="下载报告", interactive=False)

            refresh_run_btn.click(
                fn=_refresh_repo_dropdown,
                outputs=[repo_selector],
            )
            run_btn.click(
                fn=run_and_stream,
                inputs=[repo_selector],
                outputs=[run_log, run_report, run_download],
            )

        # ------------------------------------------------------------------ #
        # Tab 3: 历史报告
        # ------------------------------------------------------------------ #
        with gr.Tab("历史报告"):
            with gr.Row():
                report_dropdown = gr.Dropdown(
                    label="选择报告文件",
                    choices=list_reports(),
                    scale=4,
                )
                refresh_report_btn = gr.Button("刷新列表", scale=1)

            report_view = gr.Markdown(label="报告内容")
            report_download = gr.File(label="下载报告", interactive=False)

            refresh_report_btn.click(
                fn=refresh_report_list,
                outputs=[report_dropdown, report_view, report_download],
            )
            report_dropdown.change(
                fn=view_report,
                inputs=[report_dropdown],
                outputs=[report_view, report_download],
            )

        # ------------------------------------------------------------------ #
        # Tab 4: 定时调度
        # ------------------------------------------------------------------ #
        with gr.Tab("定时调度"):
            scheduler_cfg = gr.Textbox(
                label="当前配置",
                interactive=False,
                value=lambda: get_scheduler_info()[0],
            )
            scheduler_status = gr.Textbox(
                label="调度器状态",
                interactive=False,
                value=lambda: get_scheduler_info()[1],
            )

            with gr.Row():
                start_btn = gr.Button("启动调度", variant="primary")
                stop_btn = gr.Button("停止调度", variant="stop")
                refresh_status_btn = gr.Button("刷新状态")

            start_btn.click(fn=start_scheduler, outputs=[scheduler_status])
            stop_btn.click(fn=stop_scheduler, outputs=[scheduler_status])
            refresh_status_btn.click(fn=lambda: _scheduler_status(), outputs=[scheduler_status])

    # ---------------------------------------------------------------------- #
    # 跨 Tab 联动：订阅变更时同步更新立即运行的仓库下拉框
    # ---------------------------------------------------------------------- #
    add_btn.click(
        fn=add_subscription,
        inputs=[repo_input, label_input, track_input],
        outputs=[sub_msg, sub_table, repo_selector],
    )
    remove_btn.click(
        fn=remove_subscription,
        inputs=[repo_input],
        outputs=[sub_msg, sub_table, repo_selector],
    )
    refresh_sub_btn.click(
        fn=lambda: (refresh_subscriptions(), _refresh_repo_dropdown()),
        outputs=[sub_table, repo_selector],
    )


if __name__ == "__main__":
    demo.launch(inbrowser=True)
