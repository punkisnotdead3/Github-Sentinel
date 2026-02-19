import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

_BASE_DIR = Path(__file__).parent.parent


def load_config(config_path: str = None) -> dict:
    """加载 YAML 配置文件，并将环境变量合并进来"""
    if config_path is None:
        config_path = _BASE_DIR / "config" / "settings.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 注入环境变量
    config.setdefault("github", {})["token"] = os.getenv("GITHUB_TOKEN", "")
    config.setdefault("llm", {})["api_key"] = os.getenv("DEEPSEEK_API_KEY", "")

    # 解析相对路径为绝对路径
    config["subscriptions_file"] = str(_BASE_DIR / config.get("subscriptions_file", "config/subscriptions.json"))
    config["report"]["output_dir"] = str(_BASE_DIR / config["report"].get("output_dir", "reports"))

    return config
