# GitHub Sentinel

GitHub Sentinel 是一款开源的 AI Agent 工具，专为开发者和项目管理人员设计。它能够定期（每日/每周）自动获取并汇总订阅的 GitHub 仓库最新动态，通过 Claude AI 生成结构化的中文摘要报告，帮助团队高效跟踪项目进展。

## 功能特性

- **订阅管理**：灵活添加、删除、查看订阅的 GitHub 仓库
- **更新获取**：自动抓取 Releases、Issues、Pull Requests、Commits
- **报告生成**：调用 Claude AI 对原始数据进行智能摘要，输出 Markdown 格式报告
- **通知系统**：将报告保存为本地文件，支持扩展为邮件/Webhook 推送
- **定时调度**：支持每日或每周定时自动执行

## 项目结构

```
Github-Sentinel/
├── main.py                    # 命令行入口
├── requirements.txt           # Python 依赖
├── .gitignore
├── config/
│   ├── settings.yaml          # 主配置（调度频率、模型、报告路径等）
│   ├── subscriptions.json     # 订阅仓库列表
│   ├── .env.example           # 环境变量模板
│   ├── config_loader.py       # 配置加载器（合并 YAML 与环境变量）
│   └── __init__.py
├── subscription/
│   ├── manager.py             # 订阅增删查管理
│   └── __init__.py
├── github_client/
│   ├── client.py              # GitHub REST API 封装
│   └── __init__.py
├── llm/
│   ├── reporter.py            # Claude AI 报告生成
│   └── __init__.py
├── notifier/
│   ├── file_notifier.py       # 本地 Markdown 文件输出
│   └── __init__.py
└── scheduler/
    ├── scheduler.py           # APScheduler 定时调度
    └── __init__.py
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置密钥

```bash
cp config/.env.example .env
```

编辑 `.env` 文件，填入以下内容：

```env
GITHUB_TOKEN=your_github_token_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

- **GITHUB_TOKEN**：在 [GitHub Settings → Tokens](https://github.com/settings/tokens) 创建，需要 `repo` 读取权限
- **ANTHROPIC_API_KEY**：在 [Anthropic Console](https://console.anthropic.com/) 获取

### 3. 修改配置（可选）

编辑 `config/settings.yaml`：

```yaml
llm:
  model: "claude-opus-4-6"   # 使用的 Claude 模型
  max_tokens: 4096

scheduler:
  interval: "daily"          # daily（每天）或 weekly（每周）
  time: "08:00"              # 执行时间（24小时制）

report:
  output_dir: "reports"      # 报告输出目录
```

### 4. 管理订阅

```bash
# 查看当前订阅列表
python main.py list

# 添加仓库订阅
python main.py add microsoft/vscode
python main.py add anthropics/anthropic-sdk-python

# 移除仓库订阅
python main.py remove microsoft/vscode
```

### 5. 运行

```bash
# 立即执行一次（抓取数据 + 生成报告）
python main.py run

# 启动定时调度模式（按配置文件中的时间自动运行）
python main.py schedule
```

生成的报告保存在 `reports/` 目录下，文件名格式为 `report_YYYYMMDD_HHMMSS.md`。

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.10+ |
| AI 报告 | [Anthropic Claude API](https://docs.anthropic.com/) |
| GitHub 数据 | GitHub REST API v2022-11-28 |
| 定时调度 | APScheduler |
| 配置管理 | PyYAML + python-dotenv |

## 扩展开发

### 添加新的通知方式

在 `notifier/` 目录下新建通知类，实现 `send(content: str) -> str` 方法，然后在 `main.py` 中注册即可。例如邮件通知、Slack Webhook、钉钉/飞书等。

### 调整跟踪类型

在 `config/subscriptions.json` 中，每个仓库可单独配置跟踪项：

```json
{
  "owner": "microsoft",
  "repo": "vscode",
  "label": "VS Code",
  "track": ["releases", "issues", "pull_requests", "commits"]
}
```

## License

MIT
