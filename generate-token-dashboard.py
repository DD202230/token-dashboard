#!/usr/bin/env python3
"""Token 仪表盘 — 无侵入方案，极致 UI

支持: Claude Code / OpenClaw / Hermes / Gemini
"""
import json, os, glob, hashlib
from datetime import datetime, timezone

OUTPUT_PATH = os.path.expanduser("~/.claude/token-dashboard.html")
CACHE_FILE = os.path.expanduser("~/.claude/cache/dashboard-cache.json")


# ── 工具函数 ────────────────────────────────────────────

def fmt(n):
    if n >= 100_000_000:
        return f"{n/100_000_000:.2f}亿"
    if n >= 10_000:
        return f"{n/10_000:.1f}万"
    return f"{n:,}"


def fmt_short(n):
    if n >= 100_000_000:
        return f"{n/100_000_000:.2f}亿"
    if n >= 10_000:
        return f"{n/10_000:.1f}w"
    return str(n)


# ── 模型元数据 ──────────────────────────────────────────

MODEL_META = {
    # DeepSeek
    "deepseek-v4-pro": {"label": "DeepSeek V4-Pro", "brand": "#E75A5A", "icon": "⚡"},
    "deepseek-v4-flash": {"label": "DeepSeek V4-Flash", "brand": "#FF6B6B", "icon": "⚡"},
    "deepseek-chat": {"label": "DeepSeek Chat", "brand": "#E75A5A", "icon": "⚡"},
    "deepseek-reasoner": {"label": "DeepSeek R1", "brand": "#E75A5A", "icon": "🔮"},
    # Kimi
    "kimi-k2.6": {"label": "Kimi K2.6", "brand": "#6B8EFF", "icon": "🌙"},
    "kimi-for-coding": {"label": "Kimi Coding", "brand": "#6B8EFF", "icon": "🌙"},
    "kimi-k2-latest": {"label": "Kimi K2", "brand": "#6B8EFF", "icon": "🌙"},
    "kimi-k2.5": {"label": "Kimi K2.5", "brand": "#6B8EFF", "icon": "🌙"},
    # Gemini
    "gemini-2.5-pro": {"label": "Gemini 2.5 Pro", "brand": "#4285F4", "icon": "♊"},
    "gemini-2.5-flash": {"label": "Gemini 2.5 Flash", "brand": "#34A853", "icon": "♊"},
    "gemini-2.0-pro": {"label": "Gemini 2.0 Pro", "brand": "#4285F4", "icon": "♊"},
    "gemini-2.0-flash": {"label": "Gemini 2.0 Flash", "brand": "#34A853", "icon": "♊"},
    "gemini-1.5-pro": {"label": "Gemini 1.5 Pro", "brand": "#4285F4", "icon": "♊"},
    "gemini-1.5-flash": {"label": "Gemini 1.5 Flash", "brand": "#34A853", "icon": "♊"},
    "gemini-pro": {"label": "Gemini Pro", "brand": "#4285F4", "icon": "♊"},
    "gemini-flash": {"label": "Gemini Flash", "brand": "#34A853", "icon": "♊"},
    # Claude
    "claude-opus-4-7": {"label": "Claude Opus 4.7", "brand": "#D4A574", "icon": "🎭"},
    "claude-sonnet-4-6": {"label": "Claude Sonnet 4.6", "brand": "#D4A574", "icon": "🎭"},
    "claude-haiku-4-5": {"label": "Claude Haiku 4.5", "brand": "#D4A574", "icon": "🎭"},
    "claude-3-opus": {"label": "Claude 3 Opus", "brand": "#D4A574", "icon": "🎭"},
    "claude-3-sonnet": {"label": "Claude 3 Sonnet", "brand": "#D4A574", "icon": "🎭"},
    "claude-3-haiku": {"label": "Claude 3 Haiku", "brand": "#D4A574", "icon": "🎭"},
    "claude-3-5-sonnet": {"label": "Claude 3.5 Sonnet", "brand": "#D4A574", "icon": "🎭"},
    # Generic
    "gpt-4o": {"label": "GPT-4o", "brand": "#10A37F", "icon": "🤖"},
    "gpt-4o-mini": {"label": "GPT-4o Mini", "brand": "#10A37F", "icon": "🤖"},
    "gpt-4": {"label": "GPT-4", "brand": "#10A37F", "icon": "🤖"},
    "gpt-4-turbo": {"label": "GPT-4 Turbo", "brand": "#10A37F", "icon": "🤖"},
    "o1": {"label": "o1", "brand": "#10A37F", "icon": "🧠"},
    "o1-mini": {"label": "o1-mini", "brand": "#10A37F", "icon": "🧠"},
    "o3": {"label": "o3", "brand": "#10A37F", "icon": "🧠"},
    "o3-mini": {"label": "o3-mini", "brand": "#10A37F", "icon": "🧠"},
}


def model_info(m):
    if not m:
        return {"label": "?", "brand": "#8b949e", "icon": "❓"}
    m_lower = m.lower()
    if m_lower in MODEL_META:
        return MODEL_META[m_lower]
    for key, info in MODEL_META.items():
        if key in m_lower or m_lower in key:
            return info
    return {"label": m, "brand": "#8b949e", "icon": "🔹"}


def normalize_model(m):
    """模型名归一化：kimi-for-coding 等别名统一为 kimi-k2.6"""
    if not m:
        return "unknown"
    m_lower = m.lower()
    if m_lower in ("kimi-for-coding", "kimi-k2-latest", "kimi-k2"):
        return "kimi-k2.6"
    return m


# ── 数据源解析 ──────────────────────────────────────────

def parse_claude_transcripts():
    daily = {}
    total = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "count": 0}
    model_stats = {}

    files = glob.glob(os.path.expanduser("~/.claude/projects/-Users-dd/*.jsonl"))
    for path in files:
        mtime = os.path.getmtime(path)
        day = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")

        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except:
                        continue
                    if d.get("type") != "assistant":
                        continue
                    usage = d.get("message", {}).get("usage")
                    if not usage:
                        continue

                    inp = usage.get("input_tokens", 0)
                    out = usage.get("output_tokens", 0)
                    cr = usage.get("cache_read_input_tokens", 0)
                    cc = usage.get("cache_creation_input_tokens", 0)
                    model = normalize_model(d.get("message", {}).get("model", "claude"))

                    dd = daily.setdefault(day, {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "count": 0})
                    for k, v in [("input", inp), ("output", out), ("cache_read", cr), ("cache_creation", cc), ("count", 1)]:
                        dd[k] += v

                    for k, v in [("input", inp), ("output", out), ("cache_read", cr), ("cache_creation", cc), ("count", 1)]:
                        total[k] += v

                    ms = model_stats.setdefault(model, {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "count": 0})
                    for k, v in [("input", inp), ("output", out), ("cache_read", cr), ("cache_creation", cc), ("count", 1)]:
                        ms[k] += v
        except Exception:
            pass

    return daily, total, model_stats, {"Claude Code": total.copy()}


def parse_openclaw_trajectories():
    daily = {}
    total = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "count": 0}
    model_stats = {}

    files = glob.glob(os.path.expanduser("~/.openclaw/agents/main/sessions/*.trajectory.jsonl"))
    for path in files:
        mtime = os.path.getmtime(path)
        day = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")

        seen_runs = set()
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except:
                        continue
                    if d.get("type") not in ("model.completed", "model.response"):
                        continue

                    data = d.get("data", {})
                    usage = data.get("usage", {})
                    if not usage:
                        continue

                    run_id = d.get("runId", "")
                    if run_id in seen_runs:
                        continue
                    seen_runs.add(run_id)

                    inp = usage.get("input", usage.get("prompt_tokens", 0))
                    out = usage.get("output", usage.get("completion_tokens", 0))

                    cache = data.get("promptCache", {}).get("lastCallUsage", {})
                    cr = cache.get("cacheRead", 0)
                    cc = cache.get("cacheWrite", 0)

                    if cr == 0 and cc == 0:
                        pt_details = usage.get("prompt_tokens_details", {})
                        if pt_details:
                            cr = pt_details.get("cached_tokens", 0)

                    model = normalize_model(d.get("modelId", d.get("model", "unknown")))

                    dd = daily.setdefault(day, {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "count": 0})
                    for k, v in [("input", inp), ("output", out), ("cache_read", cr), ("cache_creation", cc), ("count", 1)]:
                        dd[k] += v

                    for k, v in [("input", inp), ("output", out), ("cache_read", cr), ("cache_creation", cc), ("count", 1)]:
                        total[k] += v

                    ms = model_stats.setdefault(model, {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "count": 0})
                    for k, v in [("input", inp), ("output", out), ("cache_read", cr), ("cache_creation", cc), ("count", 1)]:
                        ms[k] += v
        except Exception:
            pass

    return daily, total, model_stats, {"OpenClaw": total.copy()}


def estimate_tokens(text):
    if not text:
        return 0
    return int(len(text) / 3)


def parse_hermes_sessions():
    daily = {}
    total = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "count": 0}
    model_stats = {}

    files = glob.glob(os.path.expanduser("~/.hermes/sessions/session_*.json"))
    for path in files:
        mtime = os.path.getmtime(path)
        day = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")

        try:
            with open(path) as f:
                session = json.load(f)
        except Exception:
            continue

        messages = session.get("messages", [])
        if not messages:
            continue

        model = normalize_model(session.get("model", "hermes"))
        inp = 0
        out = 0
        for msg in messages:
            role = msg.get("role", "")
            content = str(msg.get("content", "") or "")
            reasoning = str(msg.get("reasoning_content", "") or "")
            text = content + reasoning
            tokens = estimate_tokens(text)
            if role == "user":
                inp += tokens
            elif role == "assistant":
                out += tokens

        count = max(1, len([m for m in messages if m.get("role") == "assistant"]))

        dd = daily.setdefault(day, {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "count": 0})
        for k, v in [("input", inp), ("output", out), ("count", count)]:
            dd[k] += v

        for k, v in [("input", inp), ("output", out), ("count", count)]:
            total[k] += v

        ms = model_stats.setdefault(model, {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "count": 0})
        for k, v in [("input", inp), ("output", out), ("count", count)]:
            ms[k] += v

    return daily, total, model_stats, {"Hermes": total.copy()}


# ── 合并 ────────────────────────────────────────────────

def merge_dailies(*sources):
    merged = {}
    for src in sources:
        for day, vals in src.items():
            dd = merged.setdefault(day, {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "count": 0})
            for k in dd:
                dd[k] += vals.get(k, 0)
    return merged


def merge_totals(*totals):
    merged = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "count": 0}
    for t in totals:
        for k in merged:
            merged[k] += t.get(k, 0)
    return merged


def merge_model_stats(*model_stat_list):
    merged = {}
    for ms in model_stat_list:
        for model, vals in ms.items():
            dd = merged.setdefault(model, {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "count": 0})
            for k in dd:
                dd[k] += vals.get(k, 0)
    return merged


# ── HTML 生成 ───────────────────────────────────────────

def generate_html(daily, total, model_stats, source_stats):
    total_tokens = total["input"] + total["output"]
    total_all = total_tokens + total["cache_read"]
    cache_rate = round(total["cache_read"] / (total["input"] + total["cache_read"]) * 100) if (total["input"] + total["cache_read"]) > 0 else 0

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dates = sorted(daily.keys())

    # 模型卡片
    model_cards = []
    sorted_models = sorted(model_stats.keys(), key=lambda x: model_stats[x]["input"] + model_stats[x]["output"], reverse=True)
    for m in sorted_models:
        ms = model_stats[m]
        mt = ms["input"] + ms["output"]
        if mt == 0 and ms["count"] == 0:
            continue
        info = model_info(m)
        cache_r = round(ms.get("cache_read", 0) / (ms.get("input", 0) + ms.get("cache_read", 0)) * 100) if (ms.get("input", 0) + ms.get("cache_read", 0)) > 0 else 0

        model_cards.append(f"""
            <div class="model-card" style="--brand:{info['brand']}">
                <div class="model-header">
                    <span class="model-icon">{info['icon']}</span>
                    <span class="model-name">{info['label']}</span>
                </div>
                <div class="model-body">
                    <div class="model-metric">
                        <span class="metric-value">{fmt_short(mt)}</span>
                        <span class="metric-label">tokens</span>
                    </div>
                    <div class="model-metric">
                        <span class="metric-value">{ms['count']:,}</span>
                        <span class="metric-label">调用</span>
                    </div>
                    <div class="model-metric">
                        <span class="metric-value">{fmt_short(ms['input'])}</span>
                        <span class="metric-label">输入</span>
                    </div>
                    <div class="model-metric">
                        <span class="metric-value">{fmt_short(ms['output'])}</span>
                        <span class="metric-label">输出</span>
                    </div>
                </div>
                <div class="model-footer">
                    <div class="mini-bar">
                        <div class="mini-bar-fill" style="width:{min(100, cache_r)}%"></div>
                    </div>
                    <span class="cache-tag">缓存 {cache_r}%</span>
                </div>
            </div>""")

    # 数据源卡片
    source_cards = []
    source_colors = {"Claude Code": "#f78166", "OpenClaw": "#3fb950", "Hermes": "#a371f7"}
    for name in ["Claude Code", "OpenClaw", "Hermes"]:
        if name not in source_stats:
            continue
        ss = source_stats[name]
        st = ss["input"] + ss["output"]
        if st == 0 and ss["count"] == 0:
            continue
        color = source_colors.get(name, "#8b949e")
        pct = round(st / total_tokens * 100) if total_tokens > 0 else 0
        source_cards.append(f"""
            <div class="source-card" style="--brand:{color}">
                <div class="source-header">
                    <span class="source-dot" style="background:{color}"></span>
                    <span class="source-name">{name}</span>
                    <span class="source-pct">{pct}%</span>
                </div>
                <div class="source-bar-track">
                    <div class="source-bar-fill" style="width:{pct}%;background:{color}"></div>
                </div>
                <div class="source-stats">
                    <span>{fmt_short(st)} tokens</span>
                    <span>{ss['count']:,} 次</span>
                    <span>{fmt_short(ss['input'])} 入 / {fmt_short(ss['output'])} 出</span>
                </div>
            </div>""")

    # 每日明细表
    table_rows = []
    for day in reversed(dates):
        d = daily[day]
        dt = d["input"] + d["output"]
        cr = d["cache_read"]
        cr_rate = round(cr / (d["input"] + cr) * 100) if (d["input"] + cr) > 0 else 0
        table_rows.append(f"""
            <tr>
                <td><span class="date-pill">{day}</span></td>
                <td class="num">{d['count']:,}</td>
                <td class="num">{fmt(d['input'])}</td>
                <td class="num">{fmt(d['output'])}</td>
                <td class="num"><strong>{fmt(dt)}</strong></td>
                <td class="num">{fmt(cr)}</td>
                <td class="num"><span class="badge-rate" style="--rate:{cr_rate}">{cr_rate}%</span></td>
            </tr>""")

    # 图表数据
    daily_input = [daily[d]["input"] for d in dates]
    daily_output = [daily[d]["output"] for d in dates]
    daily_total = [daily[d]["input"] + daily[d]["output"] for d in dates]
    daily_calls = [daily[d]["count"] for d in dates]

    # 模型分布（前5）
    top_models = sorted_models[:5]
    model_pie_labels = []
    model_pie_data = []
    model_pie_colors = []
    for m in top_models:
        mt = model_stats[m]["input"] + model_stats[m]["output"]
        if mt > 0:
            info = model_info(m)
            model_pie_labels.append(info["label"])
            model_pie_data.append(mt)
            model_pie_colors.append(info["brand"])

    no_data_msg = ""
    if not dates:
        no_data_msg = '<div class="no-data">暂无数据 — 开始对话后将自动统计</div>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Token 仪表盘</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
:root {{
    --bg: #0a0e1a;
    --bg-elevated: rgba(20,25,40,0.6);
    --bg-card: rgba(25,30,48,0.7);
    --border: rgba(255,255,255,0.06);
    --text-primary: #e8ecf1;
    --text-secondary: #8b92a8;
    --text-muted: #5a6278;
    --accent-blue: #5b8def;
    --accent-green: #4ade80;
    --accent-orange: #fb923c;
    --accent-purple: #a78bfa;
    --accent-red: #f87171;
    --glass: rgba(255,255,255,0.03);
    --shadow: 0 8px 32px rgba(0,0,0,0.3);
}}
[data-theme="light"] {{
    --bg: #f0f2f5;
    --bg-elevated: rgba(255,255,255,0.8);
    --bg-card: rgba(255,255,255,0.9);
    --border: rgba(0,0,0,0.06);
    --text-primary: #1a1d29;
    --text-secondary: #5a6278;
    --text-muted: #8b92a8;
    --glass: rgba(255,255,255,0.5);
    --shadow: 0 8px 32px rgba(0,0,0,0.08);
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text-primary);
    min-height:100vh;
    padding: 24px;
    line-height:1.5;
    transition: background 0.3s, color 0.3s;
}}
body::before {{
    content:'';
    position:fixed; inset:0;
    background:
        radial-gradient(ellipse 80% 50% at 20% 40%, rgba(91,141,239,0.08) 0%, transparent 50%),
        radial-gradient(ellipse 60% 40% at 80% 60%, rgba(167,139,250,0.06) 0%, transparent 50%),
        radial-gradient(ellipse 50% 30% at 50% 100%, rgba(74,222,128,0.05) 0%, transparent 50%);
    pointer-events:none;
    z-index:0;
}}
.container {{ position:relative; z-index:1; max-width:1400px; margin:0 auto; }}

/* Header */
.header {{
    display:flex; justify-content:space-between; align-items:center;
    margin-bottom:28px; padding-bottom:20px;
    border-bottom:1px solid var(--border);
}}
.header-left {{ display:flex; align-items:center; gap:16px; }}
.header h1 {{
    font-size:28px; font-weight:700; letter-spacing:-0.5px;
    background: linear-gradient(135deg, var(--text-primary), var(--accent-blue));
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
}}
.tag {{
    display:inline-flex; align-items:center; gap:6px;
    padding:4px 12px; border-radius:20px; font-size:12px; font-weight:500;
    background: var(--glass); border:1px solid var(--border); color: var(--text-secondary);
}}
.tag::before {{ content:''; width:6px; height:6px; border-radius:50%; background:var(--accent-green); animation:pulse 2s infinite; }}
@keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.4; }} }}
.header-right {{ display:flex; align-items:center; gap:16px; }}
.updated {{ color: var(--text-muted); font-size:13px; }}
.theme-toggle {{
    cursor:pointer; padding:8px 14px; border-radius:10px;
    background:var(--glass); border:1px solid var(--border);
    color:var(--text-secondary); font-size:13px; transition:all 0.2s;
}}
.theme-toggle:hover {{ background:var(--bg-card); color:var(--text-primary); }}

/* KPI Grid */
.kpi-grid {{
    display:grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap:16px; margin-bottom:24px;
}}
.kpi {{
    position:relative;
    background: var(--bg-card);
    backdrop-filter: blur(20px);
    border:1px solid var(--border);
    border-radius:16px;
    padding:20px 24px;
    overflow:hidden;
    transition: transform 0.2s, box-shadow 0.2s;
}}
.kpi:hover {{ transform: translateY(-2px); box-shadow: var(--shadow); }}
.kpi::before {{
    content:''; position:absolute; top:0; left:0; right:0; height:3px;
    background: linear-gradient(90deg, var(--accent-blue), var(--accent-purple));
    opacity:0.6;
}}
.kpi:nth-child(2)::before {{ background: linear-gradient(90deg, var(--accent-green), #22d3ee); }}
.kpi:nth-child(3)::before {{ background: linear-gradient(90deg, var(--accent-orange), #f472b6); }}
.kpi:nth-child(4)::before {{ background: linear-gradient(90deg, var(--accent-purple), #60a5fa); }}
.kpi .label {{
    font-size:12px; color:var(--text-secondary); text-transform:uppercase;
    letter-spacing:0.8px; margin-bottom:8px; font-weight:600;
}}
.kpi .value {{
    font-size:32px; font-weight:800; color:var(--text-primary);
    letter-spacing:-1px; font-variant-numeric:tabular-nums;
}}
.kpi .sub {{
    font-size:12px; color:var(--text-muted); margin-top:6px;
    display:flex; align-items:center; gap:8px;
}}

/* Source Section */
.section-title {{
    font-size:14px; font-weight:600; color:var(--text-secondary);
    margin-bottom:14px; letter-spacing:0.3px;
    display:flex; align-items:center; gap:8px;
}}
.section-title::before {{
    content:''; width:4px; height:16px; border-radius:2px;
    background:linear-gradient(180deg, var(--accent-blue), var(--accent-purple));
}}
.source-grid {{
    display:grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap:14px; margin-bottom:24px;
}}
.source-card {{
    background:var(--bg-card); backdrop-filter:blur(20px);
    border:1px solid var(--border); border-radius:14px;
    padding:18px 20px; transition:all 0.2s;
    border-left:3px solid var(--brand);
}}
.source-card:hover {{ transform:translateY(-1px); box-shadow:var(--shadow); }}
.source-header {{ display:flex; align-items:center; gap:10px; margin-bottom:10px; }}
.source-dot {{ width:8px; height:8px; border-radius:50%; }}
.source-name {{ font-size:14px; font-weight:600; color:var(--text-primary); flex:1; }}
.source-pct {{ font-size:13px; font-weight:700; color:var(--brand); }}
.source-bar-track {{
    height:6px; border-radius:3px; background:var(--glass);
    overflow:hidden; margin-bottom:10px;
}}
.source-bar-fill {{ height:100%; border-radius:3px; transition:width 1s ease; }}
.source-stats {{
    display:flex; justify-content:space-between;
    font-size:12px; color:var(--text-muted);
}}

/* Model Grid */
.model-grid {{
    display:grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap:14px; margin-bottom:24px;
}}
.model-card {{
    background:var(--bg-card); backdrop-filter:blur(20px);
    border:1px solid var(--border); border-radius:14px;
    padding:16px; transition:all 0.2s;
    position:relative; overflow:hidden;
}}
.model-card:hover {{ transform:translateY(-2px); box-shadow:var(--shadow); }}
.model-card::after {{
    content:''; position:absolute; top:0; right:0; width:60px; height:60px;
    background: radial-gradient(circle, var(--brand) 0%, transparent 70%);
    opacity:0.1; border-radius:50%; transform:translate(20px,-20px);
}}
.model-header {{ display:flex; align-items:center; gap:8px; margin-bottom:12px; }}
.model-icon {{ font-size:18px; }}
.model-name {{ font-size:13px; font-weight:700; color:var(--text-primary); }}
.model-body {{
    display:grid; grid-template-columns: repeat(2, 1fr);
    gap:8px; margin-bottom:12px;
}}
.model-metric {{ text-align:center; }}
.metric-value {{ font-size:16px; font-weight:800; color:var(--text-primary); font-variant-numeric:tabular-nums; }}
.metric-label {{ font-size:11px; color:var(--text-muted); }}
.model-footer {{ display:flex; align-items:center; gap:8px; }}
.mini-bar {{
    flex:1; height:4px; border-radius:2px; background:var(--glass); overflow:hidden;
}}
.mini-bar-fill {{
    height:100%; border-radius:2px;
    background: linear-gradient(90deg, var(--accent-green), #22d3ee);
    transition: width 1s ease;
}}
.cache-tag {{ font-size:11px; color:var(--text-muted); white-space:nowrap; }}

/* Charts */
.charts-grid {{
    display:grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr));
    gap:16px; margin-bottom:24px;
}}
.chart-box {{
    background:var(--bg-card); backdrop-filter:blur(20px);
    border:1px solid var(--border); border-radius:16px;
    padding:20px;
}}
.chart-box h3 {{
    font-size:14px; color:var(--text-secondary); margin-bottom:16px;
    font-weight:600; display:flex; align-items:center; gap:8px;
}}
.chart-box canvas {{ min-height:220px; max-height:280px; }}

/* Table */
.table-box {{
    background:var(--bg-card); backdrop-filter:blur(20px);
    border:1px solid var(--border); border-radius:16px;
    padding:20px; overflow-x:auto; margin-bottom:24px;
}}
.table-box h3 {{
    font-size:14px; color:var(--text-secondary); margin-bottom:16px;
    font-weight:600; display:flex; align-items:center; gap:8px;
}}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{
    text-align:left; padding:10px 14px; color:var(--text-muted);
    font-weight:600; border-bottom:1px solid var(--border);
    white-space:nowrap; font-size:12px; text-transform:uppercase; letter-spacing:0.5px;
}}
td {{ padding:10px 14px; border-bottom:1px solid var(--border); color:var(--text-secondary); }}
tr:hover td {{ background:rgba(255,255,255,0.02); color:var(--text-primary); }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; font-weight:600; }}
.date-pill {{
    display:inline-block; padding:3px 10px; border-radius:8px;
    background:var(--glass); font-size:12px; font-weight:600;
    color:var(--text-primary); border:1px solid var(--border);
}}
.badge-rate {{
    display:inline-flex; align-items:center; justify-content:center;
    padding:2px 8px; border-radius:6px; font-size:12px; font-weight:700;
    background: rgba(74,222,128, calc(var(--rate) / 100 * 0.3));
    color: hsl(calc(120 - var(--rate) * 1.2), 80%, 60%);
}}

/* Footer */
.footer {{
    text-align:center; padding:20px; color:var(--text-muted);
    font-size:12px; border-top:1px solid var(--border);
}}

/* No data */
.no-data {{
    text-align:center; padding:60px 20px; color:var(--text-muted);
    font-size:16px;
}}

/* Scrollbar */
::-webkit-scrollbar {{ width:8px; height:8px; }}
::-webkit-scrollbar-track {{ background:transparent; }}
::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:4px; }}
::-webkit-scrollbar-thumb:hover {{ background:var(--text-muted); }}

/* Responsive */
@media (max-width: 768px) {{
    body {{ padding: 12px; }}
    .header {{ flex-direction:column; gap:12px; align-items:flex-start; }}
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .kpi .value {{ font-size:24px; }}
    .model-body {{ grid-template-columns: repeat(2, 1fr); }}
}}
</style>
</head>
<body>

<div class="container">
<div class="header">
    <div class="header-left">
        <h1>Token 仪表盘</h1>
        <span class="tag">实时统计</span>
    </div>
    <div class="header-right">
        <span class="updated">更新于 {now}</span>
        <button class="theme-toggle" onclick="toggleTheme()">🌓 切换主题</button>
    </div>
</div>

<div class="kpi-grid">
    <div class="kpi">
        <div class="label">输入 Token</div>
        <div class="value">{fmt_short(total['input'])}</div>
        <div class="sub">含缓存命中 {fmt_short(total['cache_read'])}</div>
    </div>
    <div class="kpi">
        <div class="label">输出 Token</div>
        <div class="value">{fmt_short(total['output'])}</div>
        <div class="sub">{total['count']:,} 次 API 调用</div>
    </div>
    <div class="kpi">
        <div class="label">输入+输出</div>
        <div class="value">{fmt_short(total_tokens)}</div>
        <div class="sub">全部含缓存: {fmt_short(total_all)}</div>
    </div>
    <div class="kpi">
        <div class="label">缓存命中率</div>
        <div class="value">{cache_rate}%</div>
        <div class="sub">命中 {fmt(total['cache_read'])} / 写入 {fmt(total['cache_creation'])}</div>
    </div>
</div>

<div class="section-title">数据源分布</div>
<div class="source-grid">
    {''.join(source_cards)}
</div>

<div class="section-title">模型统计</div>
<div class="model-grid">
    {''.join(model_cards)}
</div>

{no_data_msg}

<div class="charts-grid">
    <div class="chart-box">
        <h3>🍩 输入 vs 输出</h3>
        <canvas id="chartPie"></canvas>
    </div>
    <div class="chart-box">
        <h3>📈 每日 Token 趋势</h3>
        <canvas id="chartDaily"></canvas>
    </div>
    <div class="chart-box">
        <h3>📊 每日调用次数</h3>
        <canvas id="chartCalls"></canvas>
    </div>
</div>

<div class="table-box">
    <h3>📋 每日明细</h3>
    <table>
        <thead>
            <tr>
                <th>日期</th><th>调用</th><th>输入</th><th>输出</th><th>总计</th><th>缓存命中</th><th>命中率</th>
            </tr>
        </thead>
        <tbody>{''.join(table_rows)}</tbody>
    </table>
</div>

<div class="footer">
    数据来源: Claude Code / OpenClaw / Hermes &nbsp;·&nbsp; 支持 Gemini / DeepSeek / Kimi / Claude / GPT 等模型
</div>
</div>

<script>
// Theme toggle
function toggleTheme() {{
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    html.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
    localStorage.setItem('dashboard-theme', html.getAttribute('data-theme'));
    updateChartColors();
}}
// Restore theme
const savedTheme = localStorage.getItem('dashboard-theme');
if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);

// Get computed colors for charts
function getChartColors() {{
    const style = getComputedStyle(document.body);
    return {{
        text: style.getPropertyValue('--text-secondary').trim(),
        grid: style.getPropertyValue('--border').trim(),
    }};
}}

Chart.defaults.color = getChartColors().text;
Chart.defaults.borderColor = getChartColors().grid;
Chart.defaults.font.family = "'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif";
Chart.defaults.font.size = 12;

function updateChartColors() {{
    const c = getChartColors();
    Chart.defaults.color = c.text;
    Chart.defaults.borderColor = c.grid;
}}

// Input vs Output Pie
new Chart(document.getElementById('chartPie'),{{
    type:'doughnut',
    data:{{
        labels:['输入 Token','输出 Token'],
        datasets:[{{
            data:[{total['input']},{total['output']}],
            backgroundColor:['#5b8def','#4ade80'],
            borderWidth:0, hoverOffset:8
        }}]
    }},
    options:{{
        responsive:true, maintainAspectRatio:false, cutout:'60%',
        plugins:{{
            legend:{{ position:'bottom', labels:{{ usePointStyle:true, padding:16 }} }}
        }}
    }}
}});

// Daily Trend
new Chart(document.getElementById('chartDaily'),{{
    type:'line',
    data:{{
        labels:{json.dumps(dates)},
        datasets:[
            {{ label:'输入', data:{json.dumps(daily_input)}, borderColor:'#5b8def', backgroundColor:'rgba(91,141,239,0.08)', fill:true, tension:0.4, pointRadius:3, pointHoverRadius:6, borderWidth:2 }},
            {{ label:'输出', data:{json.dumps(daily_output)}, borderColor:'#4ade80', backgroundColor:'rgba(74,222,128,0.08)', fill:true, tension:0.4, pointRadius:3, pointHoverRadius:6, borderWidth:2 }},
            {{ label:'合计', data:{json.dumps(daily_total)}, borderColor:'#fb923c', backgroundColor:'rgba(251,146,60,0.05)', fill:false, tension:0.4, pointRadius:4, pointHoverRadius:7, borderWidth:2, borderDash:[6,4] }}
        ]
    }},
    options:{{
        responsive:true, maintainAspectRatio:false,
        interaction:{{ mode:'index', intersect:false }},
        scales:{{
            y:{{ ticks:{{ callback:v=>v>=10000?(v/10000).toFixed(1)+'w':v }} }},
            x:{{ grid:{{ display:false }} }}
        }},
        plugins:{{ legend:{{ position:'bottom', labels:{{ usePointStyle:true, padding:16 }} }} }}
    }}
}});

// Daily Calls
new Chart(document.getElementById('chartCalls'),{{
    type:'bar',
    data:{{
        labels:{json.dumps(dates)},
        datasets:[{{
            label:'调用次数',
            data:{json.dumps(daily_calls)},
            backgroundColor:'rgba(167,139,250,0.6)',
            borderColor:'rgba(167,139,250,1)',
            borderWidth:1, borderRadius:6, borderSkipped:false
        }}]
    }},
    options:{{
        responsive:true, maintainAspectRatio:false,
        scales:{{
            y:{{ beginAtZero:true }},
            x:{{ grid:{{ display:false }} }}
        }},
        plugins:{{ legend:{{ display:false }} }}
    }}
}});
</script>
</body>
</html>"""
    return html


# ── 主流程 ──────────────────────────────────────────────

def main():
    c_daily, c_total, c_models, c_source = parse_claude_transcripts()
    o_daily, o_total, o_models, o_source = parse_openclaw_trajectories()
    h_daily, h_total, h_models, h_source = parse_hermes_sessions()

    daily = merge_dailies(c_daily, o_daily, h_daily)
    total = merge_totals(c_total, o_total, h_total)
    model_stats = merge_model_stats(c_models, o_models, h_models)
    source_stats = {**c_source, **o_source, **h_source}

    current_hash = hashlib.sha256(json.dumps(total, sort_keys=True).encode()).hexdigest()[:16]
    try:
        with open(CACHE_FILE) as f:
            cached = json.load(f).get("hash", "")
    except:
        cached = ""

    if current_hash == cached and os.path.exists(OUTPUT_PATH):
        return

    html = generate_html(daily, total, model_stats, source_stats)
    for path in [OUTPUT_PATH, os.path.expanduser("~/Desktop/token-dashboard.html")]:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        except PermissionError:
            pass

    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump({"hash": current_hash, "updated": datetime.now().isoformat()}, f)

    src_names = [k for k, v in source_stats.items() if v.get("count", 0) > 0]
    print(f"Token 仪表盘已更新 | 来源: {', '.join(src_names) or '无'} | 调用 {total['count']} 次")


if __name__ == "__main__":
    main()
