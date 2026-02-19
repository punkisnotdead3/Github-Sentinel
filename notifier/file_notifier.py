from datetime import datetime, timezone
from pathlib import Path


class FileNotifier:
    """将报告保存为本地 Markdown 文件"""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _report_filename(self, prefix: str = "report") -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{ts}.md"

    def send(self, content: str, title: str = "GitHub Sentinel 报告") -> str:
        """将报告内容写入 Markdown 文件，返回文件路径"""
        filename = self._report_filename()
        file_path = self.output_dir / filename

        header = f"# {title}\n\n生成时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n---\n\n"
        file_path.write_text(header + content, encoding="utf-8")

        print(f"[通知] 报告已保存至：{file_path}")
        return str(file_path)
