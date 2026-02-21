import json
import logging
from typing import Dict, List
from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位专业的 GitHub 项目分析师。
你的任务是将 GitHub 仓库的原始更新数据整理成一份清晰、结构化的中文摘要报告。

报告要求：
1. 按类别（发布版本、Issues、Pull Requests、提交记录）分组汇总
2. 突出重要变更和值得关注的内容
3. 语言简洁，使用 Markdown 格式
4. 如果某类数据为空，则跳过该类别
5. 在报告末尾给出一句话的整体评价
"""

_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434"


def list_ollama_models(base_url: str = _OLLAMA_DEFAULT_BASE_URL) -> List[str]:
    """查询 Ollama 本地可用模型列表，返回模型名称列表。失败时返回空列表。"""
    import requests
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        return [m["name"] for m in models]
    except Exception as e:
        logger.warning("获取 Ollama 模型列表失败: %s", e)
        return []


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
    """生成仓库更新摘要报告，支持 DeepSeek 和本地 Ollama 模型"""

    def __init__(
        self,
        model: str = "deepseek-chat",
        max_tokens: int = 4096,
        provider: str = "deepseek",
        api_key: str = "",
        base_url: str = "",
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.provider = provider

        if provider == "ollama":
            actual_base_url = (base_url or _OLLAMA_DEFAULT_BASE_URL).rstrip("/")
            self.client = OpenAI(
                api_key="ollama",
                base_url=f"{actual_base_url}/v1",
            )
        else:  # deepseek
            self.client = OpenAI(
                api_key=api_key,
                base_url=_DEEPSEEK_BASE_URL,
            )

    def generate_report(self, updates: Dict) -> str:
        """为单个仓库的更新生成 AI 摘要"""
        label = updates.get("label", f"{updates['owner']}/{updates['repo']}")
        user_prompt = _build_user_prompt(updates)

        logger.info("开始调用 LLM | 仓库: %s | 模型: %s", label, self.model)
        logger.debug(
            "LLM system prompt:\n%s",
            SYSTEM_PROMPT,
        )
        logger.debug(
            "LLM user prompt | 仓库: %s\n%s",
            label,
            user_prompt,
        )

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        usage = response.usage
        if usage:
            logger.info(
                "LLM 调用完成 | 仓库: %s | prompt_tokens: %s | completion_tokens: %s | total_tokens: %s",
                label,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
            )
        else:
            logger.info("LLM 调用完成 | 仓库: %s", label)

        return response.choices[0].message.content

    def generate_digest(self, all_updates: List[Dict]) -> str:
        """为多个仓库生成汇总 Digest 报告"""
        parts = []
        for updates in all_updates:
            label = updates.get("label", f"{updates['owner']}/{updates['repo']}")
            report = self.generate_report(updates)
            parts.append(f"# {label}\n\n{report}")

        return "\n\n---\n\n".join(parts)
