import json
from typing import Dict, List
import anthropic


SYSTEM_PROMPT = """你是一位专业的 GitHub 项目分析师。
你的任务是将 GitHub 仓库的原始更新数据整理成一份清晰、结构化的中文摘要报告。

报告要求：
1. 按类别（发布版本、Issues、Pull Requests、提交记录）分组汇总
2. 突出重要变更和值得关注的内容
3. 语言简洁，使用 Markdown 格式
4. 如果某类数据为空，则跳过该类别
5. 在报告末尾给出一句话的整体评价
"""


def _build_user_prompt(updates: Dict) -> str:
    owner = updates["owner"]
    repo = updates["repo"]
    label = updates["label"]
    fetched_at = updates["fetched_at"]
    items = updates.get("items", [])

    # 按类型分组
    groups: Dict[str, List] = {
        "release": [],
        "issue": [],
        "pull_request": [],
        "commit": [],
    }
    for item in items:
        t = item.get("type", "")
        if t in groups:
            groups[t].append(item)

    prompt_parts = [
        f"仓库：{label} ({owner}/{repo})",
        f"数据获取时间：{fetched_at}",
        "",
    ]

    if groups["release"]:
        prompt_parts.append("## Releases 数据")
        prompt_parts.append(json.dumps(groups["release"], ensure_ascii=False, indent=2))

    if groups["issue"]:
        prompt_parts.append("## Issues 数据")
        prompt_parts.append(json.dumps(groups["issue"], ensure_ascii=False, indent=2))

    if groups["pull_request"]:
        prompt_parts.append("## Pull Requests 数据")
        prompt_parts.append(json.dumps(groups["pull_request"], ensure_ascii=False, indent=2))

    if groups["commit"]:
        prompt_parts.append("## Commits 数据")
        prompt_parts.append(json.dumps(groups["commit"], ensure_ascii=False, indent=2))

    if not any(groups.values()):
        prompt_parts.append("（本周期内无任何更新）")

    prompt_parts.append("\n请根据以上数据生成一份 Markdown 格式的中文摘要报告。")
    return "\n\n".join(prompt_parts)


class LLMReporter:
    """使用 Claude API 生成仓库更新摘要报告"""

    def __init__(self, api_key: str, model: str = "claude-opus-4-6", max_tokens: int = 4096):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def generate_report(self, updates: Dict) -> str:
        """为单个仓库的更新生成 AI 摘要"""
        user_prompt = _build_user_prompt(updates)

        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text

    def generate_digest(self, all_updates: List[Dict]) -> str:
        """为多个仓库生成汇总 Digest 报告"""
        parts = []
        for updates in all_updates:
            label = updates.get("label", f"{updates['owner']}/{updates['repo']}")
            report = self.generate_report(updates)
            parts.append(f"# {label}\n\n{report}")

        return "\n\n---\n\n".join(parts)
