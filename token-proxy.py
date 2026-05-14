#!/usr/bin/env python3
"""API 代理 — 拦截所有 LLM 调用，统一记录 token 用量到 JSONL
支持多后端：deepseek (Anthropic 兼容)、kimi (OpenAI 兼容) 等
"""
import json, os, sys, time, http.client, urllib.parse, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

LOG_FILE = os.path.expanduser("~/.claude/token-usage.jsonl")
PORT = int(os.environ.get("TOKEN_PROXY_PORT", "8080"))

# 后端路由配置
BACKENDS = {
    "deepseek": {
        "host": "api.deepseek.com",
        "port": 443,
    },
    "kimi": {
        "host": "api.kimi.com",
        "port": 443,
    },
}

# 默认后端
default_backend = os.environ.get("TOKEN_PROXY_BACKEND", "kimi")


def log_usage(entry: dict):
    entry["recorded_at"] = int(time.time())
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def extract_usage_from_response(body: bytes, backend: str) -> dict:
    """从响应体中提取 usage 数据"""
    try:
        data = json.loads(body)
    except:
        return {}

    usage = {}
    # Anthropic 格式 (DeepSeek 兼容)
    if "usage" in data:
        u = data["usage"]
        usage["input_tokens"] = u.get("input_tokens", 0)
        usage["output_tokens"] = u.get("output_tokens", 0)
        usage["cache_read_input_tokens"] = u.get("cache_read_input_tokens", 0)
        usage["cache_creation_input_tokens"] = u.get("cache_creation_input_tokens", 0)
    # OpenAI 格式 (Kimi 等)
    elif "usage" in data:
        u = data["usage"]
        usage["input_tokens"] = u.get("prompt_tokens", 0)
        usage["output_tokens"] = u.get("completion_tokens", 0)

    usage["model"] = data.get("model", "?")
    return usage


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 静默模式

    def _forward(self, backend_name: str, method: str, path: str, body: bytes = None, headers: dict = None):
        cfg = BACKENDS.get(backend_name, BACKENDS[default_backend])
        target_host = cfg["host"]
        target_port = cfg["port"]

        # 路径直接透传，不修改（ANTHROPIC_BASE_URL 已包含完整路径前缀）
        target_path = path

        conn = http.client.HTTPSConnection(target_host, target_port, timeout=60)
        try:
            # 复制请求头，替换 host
            fwd_headers = dict(headers) if headers else {}
            fwd_headers["Host"] = target_host
            # 去掉可能导致问题的头
            fwd_headers.pop("Content-Length", None)

            conn.request(method, target_path, body=body, headers=fwd_headers)
            resp = conn.getresponse()
            resp_body = resp.read()

            # 记录 token 用量
            if method == "POST" and b"usage" in resp_body:
                usage = extract_usage_from_response(resp_body, backend_name)
                if usage:
                    log_usage({
                        "backend": backend_name,
                        "path": path,
                        "model": usage.get("model", "?"),
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                        "cache_read": usage.get("cache_read_input_tokens", 0),
                        "cache_creation": usage.get("cache_creation_input_tokens", 0),
                    })

            # 返回给客户端
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in ("transfer-encoding", "content-encoding"):
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(resp_body)

        finally:
            conn.close()

    def do_GET(self):
        self._forward(default_backend, "GET", self.path, headers=dict(self.headers))

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        self._forward(default_backend, "POST", self.path, body=body, headers=dict(self.headers))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, x-api-key, anthropic-version")
        self.end_headers()


def main():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    server = HTTPServer(("127.0.0.1", PORT), ProxyHandler)
    print(f"Token proxy running on http://127.0.0.1:{PORT}")
    print(f"Usage log: {LOG_FILE}")
    print(f"Backend: {default_backend}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
