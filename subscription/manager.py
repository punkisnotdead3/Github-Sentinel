import json
from pathlib import Path
from typing import List, Dict


class SubscriptionManager:
    """管理 GitHub 仓库订阅列表"""

    def __init__(self, subscriptions_file: str):
        self.file_path = Path(subscriptions_file)
        self._data = self._load()

    def _load(self) -> dict:
        if not self.file_path.exists():
            return {"subscriptions": []}
        with open(self.file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def list_subscriptions(self) -> List[Dict]:
        return self._data.get("subscriptions", [])

    def add_subscription(self, owner: str, repo: str, label: str = "", track: List[str] = None):
        """添加仓库订阅"""
        if track is None:
            track = ["releases", "issues", "pull_requests"]

        # 检查是否已存在
        for sub in self._data["subscriptions"]:
            if sub["owner"] == owner and sub["repo"] == repo:
                print(f"[已存在] {owner}/{repo} 已在订阅列表中")
                return

        entry = {
            "owner": owner,
            "repo": repo,
            "label": label or f"{owner}/{repo}",
            "track": track,
        }
        self._data["subscriptions"].append(entry)
        self._save()
        print(f"[已添加] {owner}/{repo}")

    def remove_subscription(self, owner: str, repo: str):
        """移除仓库订阅"""
        original = self._data["subscriptions"]
        self._data["subscriptions"] = [
            s for s in original if not (s["owner"] == owner and s["repo"] == repo)
        ]
        if len(self._data["subscriptions"]) < len(original):
            self._save()
            print(f"[已移除] {owner}/{repo}")
        else:
            print(f"[未找到] {owner}/{repo} 不在订阅列表中")

    def display(self):
        """打印当前订阅列表"""
        subs = self.list_subscriptions()
        if not subs:
            print("订阅列表为空")
            return
        print(f"\n当前订阅列表（共 {len(subs)} 个仓库）：")
        for i, sub in enumerate(subs, 1):
            track_str = ", ".join(sub.get("track", []))
            print(f"  {i}. {sub['owner']}/{sub['repo']}  [{sub.get('label','')}]  跟踪: {track_str}")
