from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import requests


class GitHubClient:
    """封装 GitHub REST API 调用，获取仓库动态"""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _get(self, path: str, params: dict = None) -> list | dict:
        url = f"{self.BASE_URL}{path}"
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _since_str(self, days: int) -> str:
        """返回 ISO 8601 格式的时间字符串（UTC）"""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        return since.isoformat()

    # ------------------------------------------------------------------ #
    # 各类动态获取方法
    # ------------------------------------------------------------------ #

    def get_releases(self, owner: str, repo: str, limit: int = 5) -> List[Dict]:
        """获取最新 Release"""
        data = self._get(f"/repos/{owner}/{repo}/releases", params={"per_page": limit})
        return [
            {
                "type": "release",
                "tag": r["tag_name"],
                "name": r["name"],
                "url": r["html_url"],
                "published_at": r["published_at"],
                "body": (r.get("body") or "")[:500],  # 截断过长描述
            }
            for r in data
        ]

    def get_issues(self, owner: str, repo: str, days: int = 7, limit: int = 20) -> List[Dict]:
        """获取近期 Issues"""
        data = self._get(
            f"/repos/{owner}/{repo}/issues",
            params={
                "state": "all",
                "since": self._since_str(days),
                "per_page": limit,
                "sort": "updated",
            },
        )
        return [
            {
                "type": "issue",
                "number": i["number"],
                "title": i["title"],
                "state": i["state"],
                "url": i["html_url"],
                "created_at": i["created_at"],
                "updated_at": i["updated_at"],
                "user": i["user"]["login"],
            }
            for i in data
            if "pull_request" not in i  # 排除 PR（GitHub Issues API 会混合返回）
        ]

    def get_pull_requests(self, owner: str, repo: str, days: int = 7, limit: int = 20) -> List[Dict]:
        """获取近期 Pull Requests"""
        data = self._get(
            f"/repos/{owner}/{repo}/pulls",
            params={
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": limit,
            },
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = []
        for pr in data:
            updated = datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
            if updated < cutoff:
                break
            result.append({
                "type": "pull_request",
                "number": pr["number"],
                "title": pr["title"],
                "state": pr["state"],
                "url": pr["html_url"],
                "created_at": pr["created_at"],
                "updated_at": pr["updated_at"],
                "user": pr["user"]["login"],
                "merged": pr.get("merged_at") is not None,
            })
        return result

    def get_commits(self, owner: str, repo: str, days: int = 7, limit: int = 20) -> List[Dict]:
        """获取近期 Commits"""
        data = self._get(
            f"/repos/{owner}/{repo}/commits",
            params={
                "since": self._since_str(days),
                "per_page": limit,
            },
        )
        return [
            {
                "type": "commit",
                "sha": c["sha"][:7],
                "message": c["commit"]["message"].split("\n")[0],  # 只取首行
                "url": c["html_url"],
                "date": c["commit"]["committer"]["date"],
                "author": c["commit"]["author"]["name"],
            }
            for c in data
        ]

    def fetch_updates(self, subscription: Dict, days: int = 7) -> Dict:
        """根据订阅配置抓取所有跟踪类型的更新"""
        owner = subscription["owner"]
        repo = subscription["repo"]
        track = subscription.get("track", ["releases", "issues", "pull_requests", "commits"])

        updates = {
            "owner": owner,
            "repo": repo,
            "label": subscription.get("label", f"{owner}/{repo}"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "items": [],
        }

        if "releases" in track:
            updates["items"].extend(self.get_releases(owner, repo))

        if "issues" in track:
            updates["items"].extend(self.get_issues(owner, repo, days=days))

        if "pull_requests" in track:
            updates["items"].extend(self.get_pull_requests(owner, repo, days=days))

        if "commits" in track:
            updates["items"].extend(self.get_commits(owner, repo, days=days))

        return updates
