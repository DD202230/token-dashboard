#!/usr/bin/env python3
"""Generate AI reply via API (auto-detects Anthropic or OpenAI-compatible endpoint)."""
import json, os, sys, time, urllib.request

API_BASE = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
API_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
API_MODEL = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-pro")
USAGE_FILE = "/tmp/telegram-usage.jsonl"

SYSTEM_PROMPT = """你是小克 (Claude Code 的 Telegram 分身)，运行在用户的 Mac 上 (macOS, Apple Silicon)。
用户叫你"小克"。用中文回复，简洁、实用。
你能力有限（不能操作文件、不能执行命令），但可以回答问题、提供建议。
如果用户需要文件操作或系统操作，告诉他们"等我主程序上线后帮你处理"。
当前时间: """ + __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 2.5))


def log_usage(source: str, model: str, inp: int, out: int, cache_read: int = 0, cache_creation: int = 0):
    entry = {
        "time": int(time.time()),
        "source": source,
        "model": model,
        "input": inp,
        "output": out,
        "cache_read": cache_read,
        "cache_creation": cache_creation,
    }
    try:
        with open(USAGE_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _is_anthropic() -> bool:
    return "anthropic" in API_BASE.lower()


def ai_reply(user_message: str) -> str:
    if _is_anthropic():
        return _anthropic_reply(user_message)
    return _openai_reply(user_message)


def _anthropic_reply(user_message: str) -> str:
    body = json.dumps({
        "model": API_MODEL,
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_message}],
    }).encode()

    req = urllib.request.Request(
        f"{API_BASE.rstrip('/')}/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_TOKEN,
            "anthropic-version": "2023-06-01",
        },
    )

    resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    text = ""
    for block in resp.get("content", []):
        if block.get("type") == "text":
            text = block["text"]
            break
    usage = resp.get("usage", {})
    inp = usage.get("input_tokens") or estimate_tokens(user_message + SYSTEM_PROMPT)
    out = usage.get("output_tokens") or estimate_tokens(text)
    log_usage("telegram-ai-reply", API_MODEL, inp, out)
    return text or "(no text in response)"


def _openai_reply(user_message: str) -> str:
    body = json.dumps({
        "model": API_MODEL,
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    }).encode()

    req = urllib.request.Request(
        f"{API_BASE.rstrip('/')}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_TOKEN}",
        },
    )

    resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    text = ""
    for choice in resp.get("choices", []):
        msg = choice.get("message", {})
        if msg.get("role") == "assistant":
            text = msg.get("content", "")
            break
    usage = resp.get("usage", {})
    inp = usage.get("prompt_tokens") or estimate_tokens(user_message + SYSTEM_PROMPT)
    out = usage.get("completion_tokens") or estimate_tokens(text)
    log_usage("telegram-ai-reply", API_MODEL, inp, out)
    return text or "(no text in response)"


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    if msg:
        try:
            print(ai_reply(msg))
        except Exception as e:
            print(f"(AI reply failed: {e})")
