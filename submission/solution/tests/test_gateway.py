"""Testes do gateway (``src/gateway.py``) contra um Worker falso local."""

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import gateway  # noqa: E402

ORIGIN = "http://localhost:5173"
SECRET = "texto-sensivel-xyz"


class FakeWorker:
    """Imita o ``cloudflare/worker.ts``: valida o pedido e responde."""

    def __init__(self):
        self.requests = []
        self.script = []  # estados a devolver, por ordem; vazio = 200
        self.reply = {"model": "m", "text": "[]"}
        self.raw_reply = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                owner.requests.append({
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": json.loads(body),
                })
                status = owner.script.pop(0) if owner.script else 200
                if self.headers.get("Origin") != ORIGIN:
                    status = 403
                payload = owner.reply if status == 200 else {
                    "detail": "erro com " + SECRET}
                data = (owner.raw_reply if status == 200 and owner.raw_reply
                        is not None else json.dumps(payload).encode())
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_port
        threading.Thread(
            target=self.server.serve_forever, args=(0.01,), daemon=True
        ).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class GatewayTest(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()
        self.addCleanup(self.worker.stop)
        self.sleeps = []

    def generate(self, **options):
        options.setdefault("sleep", self.sleeps.append)
        return gateway.make_generate(self.worker.url, ORIGIN, **options)

    def test_system_prompt_and_content_travel_as_one_prompt(self):
        self.worker.reply = {"model": "m", "text": '[{"a": 1}]'}
        answer = self.generate()("SISTEMA", "<document>x</document>")
        self.assertEqual(answer, '[{"a": 1}]')
        request = self.worker.requests[0]
        self.assertEqual(request["path"], "/api/v1/generate")
        self.assertEqual(list(request["body"]), ["prompt", "format"])
        self.assertEqual(request["body"]["format"], "detection")
        self.assertEqual(
            request["body"]["prompt"], "SISTEMA\n\n<document>x</document>")

    def test_the_structured_format_can_be_left_out(self):
        self.generate(response_format=None)("s", "c")
        self.assertEqual(list(self.worker.requests[0]["body"]), ["prompt"])

    def test_origin_and_json_headers_are_sent(self):
        self.generate()("s", "c")
        headers = self.worker.requests[0]["headers"]
        self.assertEqual(headers["Origin"], ORIGIN)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertNotIn("Python-urllib", headers["User-Agent"])

    def test_a_wrong_origin_is_rejected_without_retrying(self):
        generate = gateway.make_generate(
            self.worker.url, "http://outro.pt", sleep=self.sleeps.append)
        with self.assertRaises(gateway.GatewayRejected):
            generate("s", "c")
        self.assertEqual(len(self.worker.requests), 1)

    def test_temporary_failures_are_retried(self):
        self.worker.script = [429, 503]
        self.assertEqual(self.generate(delay=2)("s", "c"), "[]")
        self.assertEqual(len(self.worker.requests), 3)
        self.assertEqual(self.sleeps, [2, 4])

    def test_it_gives_up_after_the_attempts(self):
        self.worker.script = [503, 503, 503, 503]
        with self.assertRaises(gateway.GatewayUnavailable):
            self.generate(attempts=3)("s", "c")
        self.assertEqual(len(self.worker.requests), 3)

    def test_a_validation_error_is_not_retried(self):
        self.worker.script = [422]
        with self.assertRaises(gateway.GatewayRejected):
            self.generate()("s", "c")
        self.assertEqual(len(self.worker.requests), 1)

    def test_error_messages_never_include_the_body(self):
        for status, error in ((422, gateway.GatewayRejected),
                              (503, gateway.GatewayUnavailable)):
            self.worker.script = [status] * 3
            with self.assertRaises(error) as caught:
                self.generate()("s", SECRET)
            self.assertNotIn(SECRET, str(caught.exception))

    def test_an_invalid_reply_is_rejected(self):
        for raw in (b"nao e json", b'{"text": ""}', b'{"outro": 1}',
                    b'["a"]', b'{"text": 5}'):
            self.worker.raw_reply = raw
            with self.assertRaises(gateway.GatewayRejected):
                self.generate()("s", "c")

    def test_a_prompt_above_the_limit_is_refused_before_sending(self):
        with self.assertRaises(gateway.GatewayConfigError) as caught:
            self.generate(max_prompt_length=20)("s" * 15, "c" * 15)
        self.assertEqual(self.worker.requests, [])
        self.assertNotIn("ccc", str(caught.exception))

    def test_nobody_listening_is_unavailable(self):
        self.worker.stop()
        with self.assertRaises(gateway.GatewayUnavailable):
            self.generate(attempts=1)("s", "c")


class ConfigurationTest(unittest.TestCase):
    def test_no_url_means_no_gateway(self):
        self.assertIsNone(gateway.from_env({}))
        self.assertIsNone(gateway.from_env({"GEMINI_GATEWAY_URL": "  "}))

    def test_the_origin_is_required(self):
        with self.assertRaises(gateway.GatewayConfigError):
            gateway.from_env({"GEMINI_GATEWAY_URL": "https://x.dev"})

    def test_remote_gateways_must_use_https(self):
        for url in ("http://x.workers.dev", "ftp://x", "x.dev", "https://"):
            with self.assertRaises(gateway.GatewayConfigError, msg=url):
                gateway.make_generate(url, ORIGIN)
        for url in ("https://x.workers.dev", "http://localhost:8787",
                    "http://127.0.0.1:1", "https://x.dev/"):
            self.assertTrue(callable(gateway.make_generate(url, ORIGIN)), url)

    def test_numbers_must_be_positive(self):
        for name in ("GEMINI_GATEWAY_TIMEOUT", "GEMINI_GATEWAY_MAX_PROMPT"):
            for value in ("0", "-1", "abc"):
                env = {"GEMINI_GATEWAY_URL": "https://x.dev",
                       "GEMINI_GATEWAY_ORIGIN": ORIGIN, name: value}
                with self.assertRaises(gateway.GatewayConfigError):
                    gateway.from_env(env)

    def test_a_valid_environment_gives_a_generate(self):
        env = {"GEMINI_GATEWAY_URL": "https://x.dev",
               "GEMINI_GATEWAY_ORIGIN": ORIGIN,
               "GEMINI_GATEWAY_MAX_PROMPT": "50000"}
        self.assertTrue(callable(gateway.from_env(env)))


if __name__ == "__main__":
    unittest.main()
