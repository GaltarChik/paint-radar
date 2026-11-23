"""Pain Radar local server: serves the web version (docs/) and keeps the OpenAI key on this computer.

    python server.py           -> http://localhost:8000, only on this computer
    python server.py --share   -> also opens on other computers in the same Wi-Fi

The browser never receives the key: the page sends its requests to /api/chat,
and this server adds the key from .env and forwards them to OpenAI.
"""

import argparse
import json
import os
import socket
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MAX_TOKENS_LIMIT = 3000  # the page never asks for more; protects the key from oversized requests

load_dotenv(ROOT / ".env")
API_KEY = os.getenv("OPENAI_API_KEY")


class Handler(SimpleHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/config":  # tells the page: the key lives on the server, do not ask for it
            return self.send_json(200, {"server": True, "has_key": bool(API_KEY)})
        super().do_GET()  # static files from docs/ (.env is outside docs/, so it is never served)

    def do_POST(self):
        if self.path != "/api/chat":
            return self.send_json(404, {"error": {"message": "Not found"}})
        if not API_KEY:
            return self.send_json(500, {"error": {"message": "OPENAI_API_KEY is missing in .env"}})
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if json.loads(body or b"{}").get("max_tokens", 0) > MAX_TOKENS_LIMIT:
            return self.send_json(400, {"error": {"message": f"max_tokens above {MAX_TOKENS_LIMIT}"}})
        request = urllib.request.Request(OPENAI_URL, data=body, headers={
            "Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status, data = response.status, response.read()
        except urllib.error.HTTPError as e:  # OpenAI answered with an error: pass it to the page unchanged
            status, data = e.code, e.read()
        except OSError:  # no internet on this computer, or OpenAI did not answer in 60 s
            return self.send_json(502, {"error": {"message": "The laptop could not reach OpenAI."}})
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def lan_address():
    """The address of this computer in the local network (no data is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Pain Radar web version with the key from .env")
    parser.add_argument("--share", action="store_true", help="allow other computers in the same network")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    host = "0.0.0.0" if args.share else "127.0.0.1"
    server = ThreadingHTTPServer((host, args.port), partial(Handler, directory=str(ROOT / "docs")))
    print("Pain Radar is running. Stop it with Ctrl+C.")
    print(f"  On this computer:  http://localhost:{args.port}")
    if args.share:
        print(f"  Other computers:   http://{lan_address() or '<this computer IP>'}:{args.port}  (same Wi-Fi)")
        print("  While it runs, anyone on this network who opens the address uses your key.")
    if not API_KEY:
        print("  Warning: OPENAI_API_KEY is missing in .env, analysis will fail.")
    server.serve_forever()
