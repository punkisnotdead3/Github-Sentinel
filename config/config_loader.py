import os
import yaml
from pathlib import Path

_BASE_DIR = Path(__file__).parent.parent


def load_config(config_path: str = None) -> dict:
    """加载 YAML 配置文件，并从系统环境变量中读取敏感凭证"""
    if config_path is None:
        config_path = _BASE_DIR / "config" / "settings.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 从系统环境变量读取敏感凭证
    github_token = os.environ.get("GITHUB_TOKEN", "")
    deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY", "")

    if not github_token:
        raise EnvironmentError("环境变量 GITHUB_TOKEN 未设置")
    if not deepseek_api_key:
        raise EnvironmentError("环境变量 DEEPSEEK_API_KEY 未设置")

    config.setdefault("github", {})["token"] = github_token
    config.setdefault("llm", {})["api_key"] = deepseek_api_key

    # 解析相对路径为绝对路径
    config["subscriptions_file"] = str(_BASE_DIR / config.get("subscriptions_file", "config/subscriptions.json"))
    config["report"]["output_dir"] = str(_BASE_DIR / config["report"].get("output_dir", "reports"))

    return config
