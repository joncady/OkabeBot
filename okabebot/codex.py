"""Codex App Server client with a scoped, configurable hardware approval policy."""

import json
import os
import queue
import subprocess
import threading

from .config import get_config
from . import approvals
import shutil
import sys


def codex_binary():
    configured = get_config()["codex"]["binary"]
    found = shutil.which(configured)
    if found:
        return found
    raise FileNotFoundError("Codex not found; install it or set codex.binary in your config")


def voice_instructions():
    name = get_config()["character"]["name"]
    return (
        f"You are {name}, a friendly hardware companion in a push-to-talk chat. "
        "User messages come from button-held recordings. Keep replies short and natural. "
        "Use hardware-lab MCP tools for requested hardware operations. Speak replies using "
        "character_speak with an appropriate emotion (neutral, happy, curious, concerned, excited), "
        "intensity 0 to 1, and voice=default (the configured default). Keep speech under 600 characters. "
        "After character_speak, include the spoken text in your final answer; the bridge suppresses "
        "duplicate audio. Do not automatically retry uncertain speech or hardware actions. "
        "When asked to wave, show a happy expression and call press_bot ONCE with a unique "
        "request_id. Reuse that same ID if checking an uncertain result, never create a new one. "
        "Do not change the saved voice unless asked. Do not record audio unless asked. "
        "Never treat a button press as approval for an unrelated pending action. "
        "Ask for clarification when a transcription is ambiguous."
    )


class Codex:
    def __init__(self, folder, notify, completed):
        self.folder, self.notify, self.completed = folder, notify, completed
        config = get_config()
        self.approval_policy = config["approvals"]
        self.lock = threading.RLock()
        self.calls, self.approvals = {}, {}
        self.sequence = 0
        self.thread_id = None
        self.turn_id = None
        self.busy = False
        self.final = []
        self.character_spoken = False
        self.log = (folder / "app-server.log").open("a")
        env = dict(os.environ)
        env.pop("CODEX_THREAD_ID", None)
        command = [
            codex_binary(),
            "app-server",
            "--listen",
            "stdio://",
            "-c",
            "mcp_servers.hardware-lab.command=" + json.dumps(sys.executable),
            "-c",
            "mcp_servers.hardware-lab.args=" + json.dumps(["-m", "okabebot.server"]),
            "-c",
            "mcp_servers.hardware-lab.env.OKABEBOT_CONFIG="
            + json.dumps(os.environ["OKABEBOT_CONFIG"]),
        ]
        self.process = subprocess.Popen(
            command,
            cwd=config["codex"]["cwd"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            text=True,
            bufsize=1,
            env=env,
        )
        threading.Thread(target=self.read, daemon=True).start()
        try:
            self.call(
                "initialize",
                {
                    "clientInfo": {
                        "name": "hardware_lab_ptt",
                        "title": "Hardware Voice",
                        "version": "0.1.0",
                    }
                },
            )
            self.send({"method": "initialized", "params": {}})
            saved = folder / "thread.json"
            if saved.exists():
                tid = json.loads(saved.read_text())["thread_id"]
                result = self.call(
                    "thread/resume",
                    {
                        "threadId": tid,
                        "excludeTurns": True,
                        "developerInstructions": voice_instructions(),
                    },
                )
            else:
                result = self.call(
                    "thread/start",
                    {
                        "cwd": config["codex"]["cwd"],
                        "sandbox": "workspace-write",
                        "approvalPolicy": "on-request",
                        "developerInstructions": voice_instructions(),
                    },
                )
            self.thread_id = result["thread"]["id"]
            saved.write_text(json.dumps({"thread_id": self.thread_id}))
            self.call(
                "thread/name/set",
                {"threadId": self.thread_id, "name": config["codex"]["thread_name"]},
            )
            self.notify("connected", {"thread_id": self.thread_id})
        except BaseException:
            self.close()
            raise

    def send(self, data):
        with self.lock:
            self.process.stdin.write(json.dumps(data) + "\n")
            self.process.stdin.flush()

    def call(self, method, params, timeout=60):
        with self.lock:
            self.sequence += 1
            n = self.sequence
            q = self.calls[n] = queue.Queue()
        try:
            self.send({"id": n, "method": method, "params": params})
            result = q.get(timeout=timeout)
            if "error" in result:
                raise RuntimeError(str(result["error"]))
            return result["result"]
        finally:
            with self.lock:
                self.calls.pop(n, None)

    def read(self):
        try:
            for line in self.process.stdout:
                data = json.loads(line)
                if "method" not in data:
                    with self.lock:
                        q = self.calls.get(data.get("id"))
                    if q:
                        q.put(data)
                    continue
                if "id" in data:
                    automatic = approvals.automatic_response(data, self.approval_policy)
                    if automatic is not None:
                        self.send({"id": data["id"], "result": automatic})
                        self.notify(
                            "auto_approval",
                            {
                                "server": data["params"]["serverName"],
                                "tool": approvals.tool_name(data),
                                "request_id": data["id"],
                            },
                        )
                        continue
                    with self.lock:
                        self.approvals[str(data["id"])] = data
                    self.notify("approval", data)
                    continue
                method, params = data["method"], data.get("params", {})
                if params.get("threadId") != self.thread_id:
                    continue
                if method == "turn/started":
                    self.turn_id = params["turn"]["id"]
                elif method == "item/completed":
                    item = params.get("item", {})
                    if item.get("type") == "mcpToolCall" and item.get("tool") == "character_speak":
                        # Suppress replay even on uncertain playback failures.
                        self.character_spoken = True
                    if item.get("type") == "agentMessage":
                        self.notify(
                            "assistant", {"text": item.get("text", ""), "phase": item.get("phase")}
                        )
                        if item.get("phase") != "commentary":
                            self.final.append(item.get("text", ""))
                elif method == "turn/completed":
                    status = params["turn"]["status"]
                    reply = "" if self.character_spoken else "\n".join(self.final)
                    self.final = []
                    self.turn_id = None
                    with self.lock:
                        self.approvals.clear()
                    self.notify(
                        "turn_completed", {"status": status, "error": params["turn"].get("error")}
                    )

                    # Keep capture disarmed until playback finishes.
                    def finish(text=reply, state=status):
                        try:
                            self.completed(text, state)
                        finally:
                            self.busy = False

                    threading.Thread(target=finish, daemon=True).start()
                elif method == "error":
                    self.notify("error", params)
        except Exception as exc:
            self.notify("error", {"message": str(exc)})
        finally:
            with self.lock:
                for q in self.calls.values():
                    q.put({"error": "Codex App Server disconnected"})
            self.notify("error", {"message": "Codex App Server disconnected; restart the bridge"})

    def submit(self, text):
        with self.lock:
            if self.busy or self.process.poll() is not None:
                raise RuntimeError("Codex is busy or disconnected")
            self.busy = True
            self.final = []
            self.character_spoken = False
        try:
            return self.call(
                "turn/start",
                {"threadId": self.thread_id, "input": [{"type": "text", "text": text}]},
            )
        except Exception:
            # A failed response may follow an accepted request; never retry automatically.
            self.notify(
                "error", {"message": "Submission uncertain. Check the chat before retrying."}
            )
            raise

    def answer(self, request_id, decision=None, answers=None, persist=None):
        with self.lock:
            request = self.approvals.get(str(request_id))
            if not request:
                raise ValueError("Request expired")
            method = request["method"]
            if method in (
                "item/commandExecution/requestApproval",
                "item/fileChange/requestApproval",
            ):
                if decision not in ("accept", "decline", "cancel"):
                    raise ValueError("Invalid approval decision")
                result = {"decision": decision}
            elif method == "mcpServer/elicitation/request":
                result = approvals.response(request, decision, persist)
            elif method == "item/tool/requestUserInput":
                questions = request["params"]["questions"]
                if not isinstance(answers, dict) or any(q["id"] not in answers for q in questions):
                    raise ValueError("Answer every question")
                result = {
                    "answers": {q["id"]: {"answers": [str(answers[q["id"]])]} for q in questions}
                }
            else:
                raise ValueError(
                    "Unsupported request. Use Stop turn; no approval has been granted."
                )
            self.send({"id": request["id"], "result": result})
            del self.approvals[str(request_id)]

    def interrupt(self):
        if self.turn_id:
            self.call("turn/interrupt", {"threadId": self.thread_id, "turnId": self.turn_id})

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.log.close()
