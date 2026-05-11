# Token 仪表盘

无侵入式多模型 Token 用量统计仪表盘，支持 Claude Code / OpenClaw / Hermes，自动识别 Gemini / DeepSeek / Kimi / Claude / GPT 等模型。

## 特性

- **零拦截**：直接从 transcript/session 文件读取 usage，不代理网络请求
- **三合一**：同时统计 Claude Code、OpenClaw、Hermes 的调用
- **模型归一化**：自动合并模型别名（如 `kimi-for-coding` → `kimi-k2.6`）
- **极致 UI**：玻璃拟态设计、暗色/亮色主题切换、响应式布局
- **缓存统计**：精确显示缓存命中率

## 文件

| 文件 | 说明 |
|------|------|
| `generate-token-dashboard.py` | 主脚本，读取数据源并生成 HTML 仪表盘 |
| `stop-token.sh` | Claude Code Stop hook，对话结束时显示本轮 token 统计 |

## 使用方法

### 1. 生成仪表盘

```bash
python3 generate-token-dashboard.py
```

输出：`~/.claude/token-dashboard.html`（同时复制到桌面）

### 2. 配置 Stop hook（可选）

在 `~/.claude/settings.json` 中添加：

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/Users/dd/.claude/hooks/stop-token.sh"
          }
        ]
      }
    ]
  }
}
```

每次对话结束会自动显示本轮 token 用量。

## 数据源

| 工具 | 数据来源 |
|------|---------|
| Claude Code | `~/.claude/projects/-Users-dd/*.jsonl` |
| OpenClaw | `~/.openclaw/agents/main/sessions/*.trajectory.jsonl` |
| Hermes | `~/.hermes/sessions/session_*.json` |

## 技术栈

- Python 3（数据分析）
- Chart.js（图表渲染）
- 纯 CSS（玻璃拟态 UI）
