# GitHub Sentinel v0.0.4

> [中文文档](README.md)

GitHub Sentinel is an open-source AI Agent tool designed for developers and project managers. It automatically fetches and summarizes updates from subscribed GitHub repositories on a daily or weekly basis, using DeepSeek AI to generate structured Markdown reports — helping teams stay on top of project activity with minimal effort.

## Features

- **Subscription Management** — Flexibly add, remove, and view subscribed GitHub repositories
- **Update Fetching** — Automatically pulls Releases, Issues, and merged Pull Requests
- **AI Report Generation** — Calls DeepSeek AI to produce concise, structured Markdown summaries
- **Local Notifications** — Saves reports as Markdown files; extensible to email or Webhook delivery
- **Scheduled Execution** — Supports daily or weekly automatic runs via APScheduler
- **Web UI** — Gradio-based browser interface for subscription management, on-demand runs, report browsing, and scheduler control

## Project Structure

```
Github-Sentinel/
├── app.py                     # Gradio Web UI entry point
├── main.py                    # Interactive REPL entry point
├── requirements.txt           # Python dependencies
├── .gitignore
├── config/
│   ├── settings.yaml          # Main config (schedule, model, output path, etc.)
│   ├── subscriptions.json     # Subscribed repository list
│   ├── .env.example           # Environment variable template
│   ├── config_loader.py       # Config loader (merges YAML + env vars)
│   └── __init__.py
├── subscription/
│   ├── manager.py             # Subscription CRUD
│   └── __init__.py
├── github_client/
│   ├── client.py              # GitHub REST API wrapper
│   └── __init__.py
├── llm/
│   ├── reporter.py            # DeepSeek AI report generation
│   └── __init__.py
├── notifier/
│   ├── file_notifier.py       # Local Markdown file output
│   └── __init__.py
└── scheduler/
    ├── scheduler.py           # APScheduler-based task scheduler
    └── __init__.py
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Environment Variables

```env
GITHUB_TOKEN=your_github_token_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

- **GITHUB_TOKEN** — Create one at [GitHub Settings → Tokens](https://github.com/settings/tokens) with `repo` read access
- **DEEPSEEK_API_KEY** — Obtain from the [DeepSeek Open Platform](https://platform.deepseek.com/)

### 3. Configure (Optional)

Edit `config/settings.yaml`:

```yaml
llm:
  model: "deepseek-chat"     # DeepSeek model to use
  max_tokens: 4096

scheduler:
  interval: "daily"          # "daily" or "weekly"
  time: "08:00"              # Execution time (24-hour format)

report:
  output_dir: "reports"      # Report output directory
```

### 4. Launch Web UI (Recommended)

```bash
python app.py
```

A browser window opens automatically at `http://localhost:7860` with four tabs:

| Tab | Description |
|-----|-------------|
| **Subscriptions** | Add or remove repositories; view the current subscription list |
| **Run Now** | Trigger an immediate fetch; view streaming logs and AI-generated reports inline; download the result |
| **Report History** | Browse and download previously generated report files |
| **Scheduler** | Start or stop the background scheduled task |

### 5. Launch CLI (Alternative)

```bash
python main.py
```

Type `help` at the prompt to see all available commands:

```
>>> help

Available commands:
  run                  Fetch all subscribed repos and generate AI summary reports
  schedule             Start the background scheduler (uses settings.yaml timing)
  list                 Show current subscription list
  add <owner/repo>     Add a repository, e.g.: add microsoft/vscode
  remove <owner/repo>  Remove a repository, e.g.: remove microsoft/vscode
  help                 Show this help message
  exit / quit          Exit the program
```

**Example session:**

```
# View subscriptions
>>> list

# Add a repo (owner/repo or full GitHub URL)
>>> add microsoft/vscode
>>> add https://github.com/anthropics/anthropic-sdk-python

# Remove a repo
>>> remove microsoft/vscode

# Fetch and generate reports immediately
>>> run

# Start background scheduled monitoring
>>> schedule
```

Generated reports are saved under `reports/` with filenames like `report_owner_repo_YYYYMMDD_HHMMSS.md`.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| Web UI | [Gradio](https://www.gradio.app/) |
| AI Reports | [DeepSeek API](https://platform.deepseek.com/) (OpenAI-compatible) |
| GitHub Data | GitHub REST API v2022-11-28 |
| Scheduler | APScheduler |
| Config | PyYAML |

## Extending

### Add a New Notifier

Create a new class under `notifier/` that implements a `send(content: str) -> str` method, then register it in `main.py` or `app.py`. Common extensions include email (SMTP), Slack webhooks, or DingTalk/Feishu bots.

### Customize Tracked Event Types

Each subscription in `config/subscriptions.json` supports an independent `track` list:

```json
{
  "owner": "microsoft",
  "repo": "vscode",
  "label": "VS Code",
  "track": ["releases", "issues", "pull_requests"]
}
```

Supported values: `releases`, `issues`, `pull_requests`, `commits`.

## License

MIT
