"""Generic SSH stdin bridge to either loopback device service (Python 3.7)."""

import argparse
import json
import sys
from urllib.request import Request, ProxyHandler, build_opener


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(2_000_001)
        if not 0 < len(raw) <= 2_000_000 or not 1024 <= args.port <= 65535:
            raise ValueError("Invalid request size or port")
        request = Request(
            "http://127.0.0.1:%d/rpc" % args.port, raw, {"Content-Type": "application/json"}
        )
        with build_opener(ProxyHandler({})).open(request, timeout=55) as response:
            print(response.read().decode())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))


if __name__ == "__main__":
    main()
