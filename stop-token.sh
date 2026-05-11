#!/bin/bash
# Stop hook: 简洁的单行 token 报告
set -euo pipefail

INPUT=$(cat)
TRANSCRIPT=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null || true)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null || true)

if [ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ]; then
    exit 0
fi

python3 - "$TRANSCRIPT" "$SESSION_ID" << 'PYEOF' 2>/dev/null
import sys, json, os

transcript = sys.argv[1]
session_id = sys.argv[2]
state_file = os.path.expanduser('~/.claude/cache/token-state.json')

total_input = 0
total_output = 0
total_cache_read = 0
total_cache_creation = 0
seen = set()

with open(transcript) as f:
    for line in f:
        try:
            msg = json.loads(line)
            if msg.get('type') == 'assistant':
                usage = msg.get('message', {}).get('usage', {})
                msg_id = msg.get('message', {}).get('id', '')
                if usage and msg_id and msg_id not in seen:
                    total_input += usage.get('input_tokens', 0)
                    total_output += usage.get('output_tokens', 0)
                    total_cache_read += usage.get('cache_read_input_tokens', 0)
                    total_cache_creation += usage.get('cache_creation_input_tokens', 0)
                    seen.add(msg_id)
        except:
            pass

cumulative = total_input + total_output
if cumulative == 0:
    sys.exit(0)

# read previous
prev_total = 0
prev_cache_read = 0
if os.path.exists(state_file):
    try:
        with open(state_file) as f:
            state = json.load(f)
        prev_total = state.get(session_id, {}).get('total', 0)
        prev_input = state.get(session_id, {}).get('input', 0)
        prev_output = state.get(session_id, {}).get('output', 0)
        prev_cache_read = state.get(session_id, {}).get('cache_read', 0)
    except:
        pass

# save current
try:
    state = {}
    if os.path.exists(state_file):
        with open(state_file) as f:
            state = json.load(f)
    state[session_id] = {'total': cumulative, 'input': total_input, 'output': total_output, 'cache_read': total_cache_read, 'cache_creation': total_cache_creation}
    if len(state) > 10:
        keys = sorted(state.keys(), key=lambda k: state[k].get('total', 0), reverse=True)[:5]
        state = {k: state[k] for k in keys}
    with open(state_file, 'w') as f:
        json.dump(state, f)
except:
    pass

def fmt(n):
    if n >= 10000:
        return f'{n/10000:.1f}万'
    return str(n)

delta_in = total_input - prev_input
delta_out = total_output - prev_output
delta_total = cumulative - prev_total
delta_cache = total_cache_read - prev_cache_read

cache_info = f' 缓存命中{fmt(total_cache_read)}' if total_cache_read > 0 else ''

if delta_total > 0 and prev_total > 0:
    msg = f'本轮 +入{fmt(delta_in)} +出{fmt(delta_out)} | 累计 入{fmt(total_input)} 出{fmt(total_output)}' + cache_info
else:
    msg = f'本轮 入{fmt(total_input)} 出{fmt(total_output)} | 累计 {fmt(cumulative)}' + cache_info

print(json.dumps({'continue': True, 'systemMessage': msg}))
PYEOF
