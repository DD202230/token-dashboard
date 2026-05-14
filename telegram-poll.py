#!/usr/bin/env python3
"""Poll Telegram and reply via claude -p with self-managed conversation history."""
import fcntl, json, os, subprocess, sys, time, urllib.parse, urllib.request

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OFFSET_FILE = "/tmp/telegram-offset.txt"
CLAUDE_CMD = "/Users/dd/.local/bin/claude"
HISTORY_FILE = "/tmp/telegram-history.jsonl"
USAGE_FILE = "/tmp/telegram-usage.jsonl"
LOCK_FILE = "/tmp/telegram-claude.lock"
MAX_HISTORY = 20  # Keep last N exchanges for context


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

store_file = None
args = sys.argv[1:]
i = 0
while i < len(args):
    if args[i] == "--store" and i + 1 < len(args):
        store_file = args[i + 1]
        i += 2
    else:
        i += 1


def send_telegram(chat_id: str, text: str):
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage", data, timeout=10
        )
    except Exception as e:
        print(f"Send failed: {e}", file=sys.stderr)


def send_typing(chat_id: str):
    data = urllib.parse.urlencode({"chat_id": chat_id, "action": "typing"}).encode()
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{TOKEN}/sendChatAction", data, timeout=5
        )
    except Exception:
        pass


def load_history(chat_id: str) -> list[dict]:
    """Load conversation history for a chat."""
    history = []
    try:
        with open(HISTORY_FILE) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry["chat_id"] == chat_id:
                        history.append(entry)
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass
    return history[-MAX_HISTORY:]


def save_history(chat_id: str, role: str, text: str):
    """Append a message to the conversation history."""
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps({
            "chat_id": chat_id,
            "role": role,
            "text": text,
            "time": int(time.time()),
        }, ensure_ascii=False) + "\n")


def build_prompt(user_text: str, history: list[dict]) -> str:
    """Build a prompt with conversation context."""
    if not history:
        return user_text

    lines = ["以下是之前的对话上下文：", ""]
    for entry in history:
        tag = "用户" if entry["role"] == "user" else "小克"
        lines.append(f"{tag}: {entry['text']}")
    lines.append("")
    lines.append(f"用户刚才说: {user_text}")
    lines.append("")
    lines.append("请基于以上对话上下文回复用户的最新消息。用中文回复，简洁实用。")

    return "\n".join(lines)


def claude_reply(prompt: str) -> str:
    """Run claude -p and return the response."""
    try:
        result = subprocess.run(
            [CLAUDE_CMD, "-p", prompt, "--dangerously-skip-permissions"],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "CLAUDE_CODE_SIMPLE": "1"},
        )
        output = result.stdout.strip()
        if result.returncode != 0 or not output:
            err = result.stderr.strip()
            return f"Claude 回复失败: {err[:200]}" if err else "Claude 没有返回内容"
        if len(output) > 4000:
            output = output[:4000] + "\n\n... (已截断)"
        return output
    except subprocess.TimeoutExpired:
        return "Claude 回复超时 (2分钟)，请稍后重试。"
    except Exception as e:
        return f"Claude 调用异常: {e}"


# Get offset
offset = 0
try:
    with open(OFFSET_FILE) as f:
        offset = int(f.read().strip())
except FileNotFoundError:
    pass

# Poll
url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={offset}&timeout=10"
try:
    resp = json.loads(urllib.request.urlopen(url).read())
except Exception as e:
    print(f"Poll failed: {e}", file=sys.stderr)
    sys.exit(1)

if not resp.get("ok") or not resp.get("result"):
    sys.exit(0)

# Parse messages
messages = []
for upd in resp["result"]:
    msg = upd.get("message", {})
    text = msg.get("text", "")
    if not text:
        continue
    entry = {
        "update_id": upd["update_id"],
        "chat_id": str(msg["chat"]["id"]),
        "message_id": msg["message_id"],
        "from": msg.get("from", {}).get("first_name", "unknown"),
        "text": text,
        "date": msg["date"],
    }
    messages.append(entry)

if not messages:
    sys.exit(0)

# Save offset
new_offset = resp["result"][-1]["update_id"] + 1
with open(OFFSET_FILE, "w") as f:
    f.write(str(new_offset))

# Store to queue file
if store_file:
    with open(store_file, "a") as f:
        for m in messages:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

# Acquire lock to prevent concurrent claude -p calls
lock_fd = open(LOCK_FILE, "w")
try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("Locked, skipping this cycle", file=sys.stderr)
    sys.exit(0)

try:
    seen = set()
    for m in messages:
        cid = m["chat_id"]
        text = m["text"]

        if cid not in seen:
            seen.add(cid)
            send_typing(cid)

        if text == "/reset":
            send_telegram(cid, "会话已重置，开始新对话。")
            # Clear history for this chat
            save_history(cid, "system", "/reset")
            continue

        # Load context and build prompt
        history = load_history(cid)
        prompt = build_prompt(text, history)

        # Get response
        reply = claude_reply(prompt)

        # Log token usage (claude -p doesn't expose real counts, estimate)
        inp_tok = estimate_tokens(prompt)
        out_tok = estimate_tokens(reply)
        log_usage("telegram-poll", "claude", inp_tok, out_tok)

        # Save to history
        save_history(cid, "user", text)
        save_history(cid, "assistant", reply)

        send_telegram(cid, reply)
finally:
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    lock_fd.close()
