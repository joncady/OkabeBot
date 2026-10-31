"""Invented paired-device fixtures; no Firebase, models, speech or hardware."""

import json
import io
import wave
import base64
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
from okabebot.mobile import Mobile
from okabebot.surface_registry import Registry
from okabebot.mobile_http import handle
from okabebot.amadeus_habits import preference
from okabebot.amadeus_onboarding import SYSTEM, KEY
from okabebot.amadeus_text import TextConversation
from okabebot.mobile_proxy import handler as proxy_handler


class MobileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.registry = Registry(self.root / "registry.json")
        self.secret = "a" * 64
        self.item = self.registry.register(self.secret, "Invented pocket", "android")
        self.registry.update(self.item["id"], {"approved": True}, [])
        self.sender = Mock()
        self.mobile = Mobile(self.root / "mobile", self.registry, self.sender)
        self.mobile.configure(self.secret, {"token": "invented-fcm-device-token", "enabled": True})
        self.event = dict(
            id="b" * 32,
            source="calendar",
            title="Invented note",
            body="Private detail",
            priority="normal",
        )
        chat = TextConversation(self.root / "amadeus")
        with chat.store() as s:
            s.remember(SYSTEM, KEY, dict(profile="fiction", paused=False, guest=False))
            s.remember("fiction", "conversation.preferences", {"enabled": True})
        self.generate = Mock(return_value={"reply": "That sounds fun.", "memory": None})

    def test_push_has_only_opaque_id_and_deduplicates(self):
        self.mobile.enqueue(self.event)
        self.mobile.enqueue(self.event)
        self.mobile.flush()
        self.mobile.flush()
        self.sender.assert_called_once_with("invented-fcm-device-token", "b" * 32)
        self.assertEqual(self.mobile.inbox(self.secret)["items"], [self.event])
        self.assertEqual(self.mobile.path.stat().st_mode & 0o777, 0o600)

    def test_other_device_cannot_read_inbox_and_revocation_blocks_push(self):
        other = self.registry.register("c" * 64, "Other pocket", "android")
        self.registry.update(other["id"], {"approved": True}, [])
        self.mobile.enqueue(self.event)
        self.assertEqual(self.mobile.inbox("c" * 64)["items"], [])
        self.registry.update(self.item["id"], {"approved": False}, [])
        self.mobile.flush()
        self.sender.assert_not_called()
        with self.assertRaises(PermissionError):
            self.mobile.inbox(self.secret)

    def test_failed_push_not_replayed_and_payload_remains_private(self):
        self.sender.side_effect = RuntimeError("invented transport outage")
        self.mobile.enqueue(self.event)
        self.mobile.flush()
        self.mobile.flush()
        self.sender.assert_called_once()
        self.assertEqual(len(self.mobile.inbox(self.secret)["items"]), 1)

    def test_opt_out_and_token_rotation(self):
        self.mobile.settings({"id": self.item["id"], "enabled": False})
        refreshed = self.mobile.configure(
            self.secret, {"token": "invented-refreshed-token", "enabled": True}
        )
        self.assertFalse(refreshed["enabled"])
        self.mobile.enqueue(self.event)
        self.assertEqual(self.mobile.inbox(self.secret)["items"], [])
        self.mobile.configure(
            self.secret, {"token": "invented-rotated-token", "enabled": True, "set_enabled": True}
        )
        self.mobile.enqueue(self.event)
        self.mobile.flush()
        self.sender.assert_called_once_with("invented-rotated-token", "b" * 32)
        self.assertNotIn("token", json.dumps(self.mobile.settings()))

    def test_retention_and_forgotten_device_cleanup(self):
        self.mobile.enqueue(self.event)
        with self.mobile.db() as db:
            db.execute("UPDATE events SET created=1")
            db.execute("INSERT INTO turns VALUES (?,?,?)", (self.item["id"], "old-turn", 1))
        self.mobile.prune()
        self.assertEqual(self.mobile.inbox(self.secret)["items"], [])
        with self.mobile.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM turns").fetchone()[0], 0)
        self.registry.update(self.item["id"], {"remove": True}, [])
        self.mobile.prune()
        with self.mobile.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM devices").fetchone()[0], 0)

    def test_chat_uses_model_without_tools_and_claims_before_generation(self):
        data = {"text": "I enjoy pottery", "request_id": "invented-turn-1"}
        result = self.mobile.chat(self.secret, data, self.generate)
        self.assertEqual(result["tools"], [])
        self.assertEqual(result["reply"], "That sounds fun.")
        self.assertEqual(self.generate.call_args.args[1]["capabilities"], [])
        with self.assertRaises(ValueError):
            self.mobile.chat(self.secret, data, self.generate)
        self.generate.assert_called_once()

    def test_consent_and_inflight_revocation(self):
        def revoke(*_):
            self.registry.update(self.item["id"], {"approved": False}, [])
            return {
                "reply": "A private reply",
                "memory": {"field": "hobbies", "values": ["pottery"], "evidence": "pottery"},
            }

        with self.assertRaises(PermissionError):
            self.mobile.chat(
                self.secret, {"text": "I enjoy pottery", "request_id": "invented-turn-2"}, revoke
            )
        with TextConversation(self.root / "amadeus").store() as s:
            self.assertEqual(preference(s, "fiction", "context.preferences", {}), {})

    def test_browser_token_does_not_grant_mobile_capabilities(self):
        item = self.registry.register("d" * 64, "Invented browser", "browser")
        self.registry.update(item["id"], {"approved": True}, [])
        with self.assertRaises(PermissionError):
            self.mobile.inbox("d" * 64)

    def streaming_fixture(self, release, first):
        from okabebot.surface_audio import AudioHub

        hub = AudioHub()
        hub.poll(self.item["id"], {"session": "b" * 32, "after": 0, "enabled": True})
        surfaces = SimpleNamespace(phase="tv", active_id=self.item["id"])

        def pcm(*args, **kwargs):
            self.assertEqual(kwargs["character"], "kurisu")
            yield b"\0" * 4800
            first.set()
            release.wait(3)
            yield b"\0" * 4800

        for target, value in [
            ("okabebot.speech.state_dir", self.root),
            ("okabebot.speech.engine", "local"),
            ("okabebot.character.current_voice", "calm"),
            ("okabebot.profiles.current_character", {"style": "kurisu"}),
        ]:
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("okabebot.speech.local_pcm_chunks", side_effect=pcm)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(release.set)
        return hub, surfaces

    def test_stream_delivers_before_generation_finishes_and_holds_supervisor_lock(self):
        from okabebot.runtime import speech_active

        release, first = threading.Event(), threading.Event()
        hub, surfaces = self.streaming_fixture(release, first)
        result = self.mobile.start_voice_stream(self.secret, "Invented reply", hub, surfaces)
        self.assertEqual(result["playback_mode"], "stream")
        self.assertTrue(first.wait(1))
        identifier = result["stream_id"]
        events = hub.poll(self.item["id"], {"session": "b" * 32, "after": 0, "enabled": True})[
            "events"
        ]
        self.assertEqual([e["kind"] for e in events], ["start", "chunk"])
        self.assertEqual(events[1]["sequence"], 0)
        self.assertFalse(hub.streams[identifier]["ended"])
        self.assertTrue(speech_active(self.root))
        with self.assertRaisesRegex(ValueError, "busy"):
            self.mobile.start_voice_stream(self.secret, "Must not replay", hub, surfaces)
        job = self.mobile.voice_jobs[self.item["id"]]
        release.set()
        with hub.condition:
            self.assertTrue(
                hub.condition.wait_for(lambda: hub.streams[identifier]["ended"], timeout=1)
            )
        hub.poll(
            self.item["id"],
            {"session": "b" * 32, "after": 0, "enabled": True, "finished": identifier},
        )
        self.assertTrue(job["done"].wait(1))
        self.assertFalse(speech_active(self.root))
        self.assertEqual(self.mobile.voice_status(self.secret)["stage"], "ready")

    def test_stream_rejects_busy_worker_before_accepting_audio(self):
        from okabebot.speech import synthesis_session

        release, first = threading.Event(), threading.Event()
        hub, surfaces = self.streaming_fixture(release, first)
        with synthesis_session(), self.assertRaisesRegex(ValueError, "busy"):
            self.mobile.start_voice_stream(self.secret, "Invented reply", hub, surfaces)
        self.assertEqual(hub.streams, {})
        self.assertNotIn(self.item["id"], self.mobile.voice_jobs)

    def test_stream_source_failure_aborts_without_replay_or_completion(self):
        release, first = threading.Event(), threading.Event()
        hub, surfaces = self.streaming_fixture(release, first)

        def failed_source(*args, **kwargs):
            yield b"\0" * 4800
            first.set()
            release.wait(2)
            raise RuntimeError("invented provider failure")

        with patch("okabebot.speech.local_pcm_chunks", side_effect=failed_source):
            result = self.mobile.start_voice_stream(self.secret, "Invented reply", hub, surfaces)
            self.assertTrue(first.wait(1))
            job = self.mobile.voice_jobs[self.item["id"]]
            release.set()
            self.assertTrue(job["done"].wait(1))
        stream = hub.streams[result["stream_id"]]
        self.assertTrue(stream["aborted"])
        self.assertFalse(stream["ended"])
        self.assertEqual(stream["sequence"], 1)
        self.assertEqual(self.mobile.voice_status(self.secret)["stage"], "failed:streaming")

    def test_stream_aborts_on_move_session_change_and_revocation(self):
        for reason in ("move", "session", "revoke", "consent"):
            with self.subTest(reason=reason):
                release, first = threading.Event(), threading.Event()
                hub, surfaces = self.streaming_fixture(release, first)
                result = self.mobile.start_voice_stream(
                    self.secret, "Invented reply", hub, surfaces
                )
                self.assertTrue(first.wait(1))
                job = self.mobile.voice_jobs[self.item["id"]]
                if reason == "move":
                    surfaces.active_id = "other"
                elif reason == "session":
                    hub.poll(self.item["id"], {"session": "c" * 32, "after": 0, "enabled": True})
                elif reason == "revoke":
                    self.registry.update(self.item["id"], {"approved": False}, [])
                else:
                    with TextConversation(self.root / "amadeus").store() as store:
                        store.remember(
                            SYSTEM, KEY, dict(profile="fiction", paused=True, guest=False)
                        )
                with hub.condition:
                    self.assertTrue(
                        hub.condition.wait_for(
                            lambda: hub.streams[result["stream_id"]]["aborted"], timeout=1
                        )
                    )
                release.set()
                self.assertTrue(job["done"].wait(1))
                self.registry.update(self.item["id"], {"approved": True}, [])
                with TextConversation(self.root / "amadeus").store() as store:
                    store.remember(SYSTEM, KEY, dict(profile="fiction", paused=False, guest=False))
                self.assertEqual(hub.streams[result["stream_id"]]["sequence"], 1)

    def test_voice_timing_snapshot_has_stage_durations_without_content(self):
        with patch("okabebot.mobile.time.monotonic", side_effect=[10, 11, 13, 18]):
            for stage in ("receiving", "transcribing", "synthesizing", "ready"):
                self.mobile.trace(self.item["id"], stage)
        result = self.mobile.voice_status(self.secret)
        self.assertEqual(result["server_total_s"], 8)
        self.assertEqual(
            result["timings_s"], {"receiving": 1, "transcribing": 2, "synthesizing": 5}
        )
        self.assertNotIn("started", result)
        self.assertNotIn("phase_started", result)
        with patch("okabebot.mobile.time.monotonic", side_effect=[20, 21, 23, 26, 28, 30]):
            for stage in (
                "receiving",
                "transcribing",
                "synthesizing",
                "streaming",
                "draining",
                "ready",
            ):
                self.mobile.trace(self.item["id"], stage)
        result = self.mobile.voice_status(self.secret)
        self.assertEqual(result["first_pcm_s"], 6)
        self.assertEqual(result["synthesis_first_pcm_s"], 3)
        self.assertEqual(result["completion_s"], 10)

    def test_mobile_read_tools_are_passed_to_conversation(self):
        turn = Mock(
            return_value={"reply": "The invented TV is off.", "tools": ["get_current_media"]}
        )
        result = self.mobile.chat(
            self.secret,
            {"text": "What is playing?", "request_id": "invented-read-request"},
            self.generate,
            tool_turn=turn,
            specs={"get_current_media": {"description": "Read media"}},
        )
        turn.assert_called_once()
        self.assertEqual(result["tools"], ["get_current_media"])
        self.generate.assert_not_called()

    def test_voice_returns_private_wav_and_diagnostic_stages(self):
        raw = io.BytesIO()
        with wave.open(raw, "wb") as w:
            w.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            w.writeframes(b"\x00\x00" * 1600)
        encoded = base64.b64encode(raw.getvalue()).decode()
        data = json.dumps({"clip_id": "screen-invented-voice", "wav_base64": encoded}).encode()

        class RequestHandler:
            path = "/mobile/voice"
            headers = {
                "Host": "fiction.local:8768",
                "X-Surface-Token": self.secret,
                "Content-Length": str(len(data)),
            }
            rfile = io.BytesIO(data)
            connection = SimpleNamespace(settimeout=lambda *_: None)

            def respond(handler, code, body):
                handler.result = (code, body)

        bridge = SimpleNamespace(
            mobile=self.mobile,
            allowed_hosts={"fiction.local:8768"},
            codex=SimpleNamespace(compose_preference=self.generate),
            transcribe=Mock(return_value="Hello"),
            surfaces=SimpleNamespace(phase="tv", active_id=self.item["id"]),
        )

        def synth(text, emotion, voice, path):
            from okabebot.runtime import speech_active

            self.assertTrue(speech_active(self.root))
            Path(path).write_bytes(raw.getvalue())

        self.guard_patch = patch("okabebot.speech.state_dir", return_value=self.root)
        self.guard_patch.start()
        self.addCleanup(self.guard_patch.stop)
        request = RequestHandler()
        with patch("okabebot.character.synthesize", synth):
            handle(request, bridge, True)
        self.assertEqual(request.result[0], 200)
        self.assertEqual(request.result[1]["wav_base64"], encoded)
        self.assertEqual(self.mobile.voice_status(self.secret)["stage"], "ready")
        self.assertEqual(request.result[1]["tools"], [])
        self.assertEqual(len(request.result[1]["levels"]), 2)
        request = RequestHandler()
        request.rfile = io.BytesIO(data)
        bridge.codex.text_turn = Mock(return_value={"reply": "Invented state", "tools": []})
        bridge.codex.specs = {"get_current_media": {}, "set_speaker_volume": {}}
        with (
            patch.object(self.mobile, "chat", return_value={"reply": "Invented state"}) as chat,
            patch("okabebot.character.synthesize", synth),
        ):
            handle(request, bridge, True)
            self.assertEqual(set(chat.call_args.kwargs["specs"]), {"get_current_media"})
            chat.call_args.kwargs["tool_turn"]("What is playing?", history=[])
            bridge.codex.text_turn.assert_called_once_with(
                "What is playing?", read_only=True, history=[]
            )

        stream_data = json.dumps(
            {"clip_id": "screen-invented-stream", "wav_base64": encoded, "playback_mode": "stream"}
        ).encode()
        request = RequestHandler()
        request.headers = {**request.headers, "Content-Length": str(len(stream_data))}
        request.rfile = io.BytesIO(stream_data)
        bridge.surface_audio = Mock()
        with (
            patch.object(self.mobile, "chat", return_value={"reply": "Invented stream"}),
            patch.object(
                self.mobile,
                "start_voice_stream",
                return_value={"playback_mode": "stream", "stream_id": "invented-id"},
            ) as start,
        ):
            handle(request, bridge, True)
            self.assertEqual(request.result[0], 200)
            self.assertEqual(request.result[1]["playback_mode"], "stream")
            self.assertNotIn("wav_base64", request.result[1])
            start.assert_called_once_with(
                self.secret, "Invented stream", bridge.surface_audio, bridge.surfaces
            )

        for failure, expected in [
            (
                "Enable preference conversations in private Amadeus setup first",
                "Enable preference conversations",
            ),
            ("Already submitted; no automatic retry", "already submitted"),
            ("invented sensitive provider detail", "could not be processed"),
        ]:
            request = RequestHandler()
            request.rfile = io.BytesIO(data)
            with patch.object(self.mobile, "chat", side_effect=ValueError(failure)):
                handle(request, bridge, True)
            self.assertEqual(request.result[0], 400)
            self.assertIn(expected, request.result[1]["error"])
            self.assertNotIn("invented sensitive", request.result[1]["error"])
        request = RequestHandler()
        request.rfile = io.BytesIO(data)
        bridge.transcribe.return_value = " "
        handle(request, bridge, True)
        self.assertEqual(request.result[0], 422)
        self.assertIn("no clear speech", request.result[1]["error"])

    def test_suggestion_feedback_is_approved_id_scoped_and_has_no_tools(self):
        suggestion_id = "e" * 32
        proactive = SimpleNamespace(
            explanation=Mock(
                return_value={
                    "available": True,
                    "suggestion": {
                        "id": suggestion_id,
                        "reason": "An older interest and an available window.",
                        "kind": "checkin",
                        "topic": "interests",
                        "feedback": None,
                    },
                }
            ),
            suggestion_feedback=Mock(return_value={"saved": True, "outcome": "too_soon"}),
        )
        bridge = SimpleNamespace(
            mobile=self.mobile,
            allowed_hosts={"fiction.local:8768"},
            proactive=proactive,
            codex=None,
        )

        def request(path, data=None, secret=None):
            raw = json.dumps(data).encode() if data is not None else b""
            handler = SimpleNamespace(
                path=path,
                headers={
                    "Host": "fiction.local:8768",
                    "X-Surface-Token": self.secret if secret is None else secret,
                    "Content-Length": str(len(raw)),
                },
                rfile=io.BytesIO(raw),
                connection=SimpleNamespace(settimeout=lambda *_: None),
            )
            handler.respond = lambda code, value: setattr(handler, "result", (code, value))
            handle(handler, bridge, data is not None)
            return handler.result

        self.assertEqual(request("/mobile/suggestion")[0], 200)
        self.assertEqual(
            request("/mobile/feedback", {"suggestion_id": suggestion_id, "outcome": "too_soon"}),
            (200, {"saved": True, "outcome": "too_soon"}),
        )
        proactive.suggestion_feedback.assert_called_once_with(
            {"suggestion_id": suggestion_id, "outcome": "too_soon"}
        )
        for bad in (
            {"suggestion_id": suggestion_id, "outcome": "remember"},
            {"suggestion_id": suggestion_id, "outcome": "good_timing", "tool": "move_companion"},
            {"suggestion_id": "missing", "outcome": "not_interested"},
        ):
            self.assertEqual(request("/mobile/feedback", bad)[0], 400)
        self.assertEqual(proactive.suggestion_feedback.call_count, 1)
        proactive.explanation.side_effect = PermissionError("Private consent ended")
        self.assertEqual(request("/mobile/suggestion")[0], 403)
        proactive.suggestion_feedback.side_effect = PermissionError("Private consent ended")
        self.assertEqual(
            request("/mobile/feedback", {"suggestion_id": suggestion_id, "outcome": "good_timing"})[
                0
            ],
            403,
        )
        proactive.explanation.reset_mock()
        self.registry.update(self.item["id"], {"approved": False}, [])
        self.assertEqual(request("/mobile/suggestion")[0], 403)
        proactive.explanation.assert_not_called()

    def test_real_http_boundary_rejects_owner_routes_and_cross_origin(self):
        mobile = self.mobile

        class Handler(
            __import__("http.server", fromlist=["BaseHTTPRequestHandler"]).BaseHTTPRequestHandler
        ):
            def log_message(self, *_):
                pass

            def authorized(self):
                return False

            def respond(self, code, data):
                self.send_response(code)
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def do_GET(self):
                handle(self, bridge)

            def do_POST(self):
                handle(self, bridge, True)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        bridge = SimpleNamespace(
            mobile=mobile, allowed_hosts={"127.0.0.1:" + str(server.server_port)}, codex=None
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = "http://127.0.0.1:" + str(server.server_port)
        for path, headers, code in [
            ("/mobile/settings", {}, 403),
            ("/mobile/inbox", {"Origin": "https://evil.invalid"}, 403),
            ("/mobile/tools", {}, 404),
        ]:
            with self.assertRaises(HTTPError) as caught:
                urlopen(
                    Request(base + path, headers={"X-Surface-Token": self.secret, **headers}),
                    timeout=2,
                )
            self.assertEqual(caught.exception.code, code)

    def test_proxy_forwards_suggestion_feedback_but_strips_owner_authority(self):
        from http.server import BaseHTTPRequestHandler

        received = []

        class Backend(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self):
                # Consume POST data before closing, otherwise a TCP reset can
                # discard this fixture's response while the client sends its body.
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                received.append((self.command, self.path, dict(self.headers)))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"accepted":true}')

            do_GET = reply
            do_POST = reply

        backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        proxy = ThreadingHTTPServer(
            ("127.0.0.1", 0), proxy_handler("fiction.example.ts.net", backend.server_port)
        )
        for server in (backend, proxy):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        base = "http://127.0.0.1:" + str(proxy.server_port)
        headers = {
            "Host": "fiction.example.ts.net",
            "X-Surface-Token": self.secret,
            "X-Hardware-Token": "invented-owner-authority",
        }
        with urlopen(Request(base + "/mobile/suggestion", headers=headers), timeout=2) as response:
            self.assertEqual(response.status, 200)
        raw = json.dumps({"suggestion_id": "f" * 32, "outcome": "good_timing"}).encode()
        with urlopen(
            Request(base + "/mobile/feedback", data=raw, headers=headers), timeout=2
        ) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(
            [(method, path) for method, path, _ in received],
            [("GET", "/mobile/suggestion"), ("POST", "/mobile/feedback")],
        )
        for _, _, forwarded in received:
            self.assertNotIn("X-Hardware-Token", forwarded)
            self.assertEqual(forwarded["X-Surface-Token"], self.secret)
        for path, data in (("/mobile/feedback", None), ("/mobile/suggestion", b"{}")):
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(base + path, data=data, headers=headers), timeout=2)
            self.assertEqual(caught.exception.code, 403)
        self.assertEqual(len(received), 2)

    def test_proxy_does_not_forward_owner_or_controls(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), proxy_handler("fiction.example.ts.net", 1))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = "http://127.0.0.1:" + str(server.server_port)
        for route in (
            "/state",
            "/mobile/settings",
            "/surfaces/move",
            "/amadeus/api/export",
            "/webhooks/github",
            "/speaker/volume",
        ):
            with self.assertRaises(HTTPError) as caught:
                urlopen(
                    Request(base + route, headers={"Host": "fiction.example.ts.net"}), timeout=2
                )
            self.assertEqual(caught.exception.code, 403)
