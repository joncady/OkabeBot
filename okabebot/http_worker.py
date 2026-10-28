"""Optional local inference-server adapter using structured tool_calls responses.

The server owns model-format parsing. This worker never executes tools or retries.
"""

import argparse
import json
import sys
import time
import urllib.request
from urllib.parse import urlsplit

from .local_worker import system_prompt


def decode_message(message):
    calls = message.get("tool_calls") or []
    if len(calls) > 1:
        raise ValueError("Only one tool call is permitted")
    call = None
    if calls:
        entry = calls[0]
        if entry.get("type") != "function":
            raise ValueError("Unsupported tool call type")
        function = entry["function"]
        arguments = function["arguments"]
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object")
        call = {"name": function["name"], "arguments": arguments}
    text = message.get("content") or ""
    if not isinstance(text, str):
        raise ValueError("Unsupported assistant content")
    # A broken server response must not speak raw model-format markup.
    if not call and ("<tool_call>" in text or text.lstrip().startswith("{")):
        raise ValueError("Server did not return a structured tool call")
    return {"text": text, "tool_call": call}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8771/v1/chat/completions")
    args = parser.parse_args()
    url = urlsplit(args.endpoint)
    if url.scheme != "http" or url.hostname not in ("127.0.0.1", "::1", "localhost"):
        parser.error("Evaluation endpoint must be local loopback HTTP")
    setup = json.loads(sys.stdin.readline())
    tools = {t["function"]["name"]: t for t in setup["tools"]}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        try:
            data = json.loads(line)
            started = time.monotonic()
            if data.get("location_tool"):
                tools["move_companion"] = data["location_tool"]
            selected = [tools[n] for n in sorted(set(data.get("tool_names", tools)) & tools.keys())]
            payload = {
                "model": setup["model"],
                "messages": [
                    {"role": "system", "content": system_prompt(data["persona"])},
                    {"role": "user", "content": data["text"]},
                ],
                "temperature": 0,
                "max_tokens": 130,
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
            }
            if selected:
                payload["tools"] = selected
            request = urllib.request.Request(
                args.endpoint,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with opener.open(request, timeout=40) as response:
                result = json.load(response)
            decoded = decode_message(result["choices"][0]["message"])
            decoded.update(selection_s=round(time.monotonic() - started, 3))
            decoded["generated_tokens"] = result.get("usage", {}).get("completion_tokens")
            print(json.dumps(decoded), flush=True)
        except Exception:
            print(
                json.dumps({"error": "Local inference server failed; no action executed"}),
                flush=True,
            )


if __name__ == "__main__":
    main()
