import contextlib
import io
import os
import unittest
from datetime import date
from unittest.mock import patch

from src.daily_claim import ClaimError, claim, main


DAY = "2026-09-17"
SHA = "a" * 40
TOKEN = "TEST_TOKEN"
REF = f"refs/tags/ldr-daily-{DAY}"


class Response:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class Http:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)


class TimeoutHttp(Http):
    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        raise TimeoutError("untrusted timeout detail")


class DailyClaimTests(unittest.TestCase):
    def test_201_creates_exact_ref_without_get(self):
        http = Http([Response(201, {"ref": REF})])
        self.assertTrue(claim(DAY, "carloshuangspec/wechat-ldr-daily-push", SHA, TOKEN,
                              http=http, now=date(2026, 9, 17)))
        self.assertEqual(["POST"], [call[0] for call in http.calls])
        method, url, kwargs = http.calls[0]
        self.assertEqual("https://api.github.com/repos/carloshuangspec/wechat-ldr-daily-push/git/refs", url)
        self.assertEqual({"ref": REF, "sha": SHA}, kwargs["json"])
        self.assertEqual({"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}, kwargs["headers"])
        self.assertEqual((10, False), (kwargs["timeout"], kwargs["allow_redirects"]))

    def test_201_with_wrong_or_malformed_ref_fails_closed(self):
        for payload in ({"ref": "refs/tags/other"}, {}, ValueError("bad json")):
            with self.subTest(payload=payload), self.assertRaises(ClaimError):
                claim(DAY, "carloshuangspec/wechat-ldr-daily-push", SHA, TOKEN,
                     http=Http([Response(201, payload)]), now=date(2026, 9, 17))

    def test_conflict_lookup_returns_false_only_for_exact_ref(self):
        for status in (409, 422):
            http = Http([Response(status), Response(200, {"ref": REF})])
            self.assertFalse(claim(DAY, "carloshuangspec/wechat-ldr-daily-push", SHA, TOKEN,
                                   http=http, now=date(2026, 9, 17)))
            self.assertEqual("GET", http.calls[1][0])
            self.assertEqual(f"https://api.github.com/repos/carloshuangspec/wechat-ldr-daily-push/git/ref/tags/ldr-daily-{DAY}", http.calls[1][1])

    def test_lookup_404_wrong_ref_and_timeout_fail_closed(self):
        for response in (Response(404), Response(200, {"ref": "refs/tags/other"})):
            with self.subTest(response=response.status_code), self.assertRaises(ClaimError):
                claim(DAY, "carloshuangspec/wechat-ldr-daily-push", SHA, TOKEN,
                     http=Http([Response(409), response]), now=date(2026, 9, 17))
        with self.assertRaises(ClaimError):
            claim(DAY, "carloshuangspec/wechat-ldr-daily-push", SHA, TOKEN,
                 http=TimeoutHttp([Response(409)]), now=date(2026, 9, 17))

    def test_invalid_context_fails_before_http(self):
        for repo, day, sha, token in (
            ("other/repo", DAY, SHA, TOKEN),
            ("carloshuangspec/wechat-ldr-daily-push", "2026-09-16", SHA, TOKEN),
            ("carloshuangspec/wechat-ldr-daily-push", "2026-09-17T00:00:00", SHA, TOKEN),
            ("carloshuangspec/wechat-ldr-daily-push", DAY, "A" * 40, TOKEN),
            ("carloshuangspec/wechat-ldr-daily-push", DAY, SHA[:-1], TOKEN),
            ("carloshuangspec/wechat-ldr-daily-push", DAY, SHA, ""),
        ):
            http = Http([])
            with self.subTest(repo=repo, day=day), self.assertRaises(ClaimError):
                claim(day, repo, sha, token, http=http, now=date(2026, 9, 17))
            self.assertEqual([], http.calls)

    def test_invalid_now_fails_before_http(self):
        http = Http([])
        with self.assertRaises(ClaimError):
            claim(DAY, "carloshuangspec/wechat-ldr-daily-push", SHA, TOKEN,
                 http=http, now="2026-09-17")
        self.assertEqual([], http.calls)

    def test_cli_output_path_is_opened_before_network(self):
        with patch.dict(os.environ, {"DELIVERY_DATE": DAY, "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
                                     "GITHUB_SHA": SHA, "GH_TOKEN": TOKEN, "GITHUB_OUTPUT": "/unwritable/output"}, clear=False), \
             patch("src.daily_claim.requests.post") as post, \
             patch("builtins.open", side_effect=OSError("untrusted path detail")), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(2, main())
        post.assert_not_called()
        self.assertEqual("daily_claim_failed\n", err.getvalue())

    def test_cli_missing_output_path_stops_before_network(self):
        with patch.dict(os.environ, {"DELIVERY_DATE": DAY, "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
                                     "GITHUB_SHA": SHA, "GH_TOKEN": TOKEN}, clear=True), \
             patch("src.daily_claim.requests.post") as post, \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(2, main())
        post.assert_not_called()
        self.assertEqual("daily_claim_failed\n", err.getvalue())

    def test_cli_exists_writes_false_and_uses_safe_get_options(self):
        output = io.StringIO()
        http = Http([Response(409), Response(200, {"ref": REF})])
        with patch.dict(os.environ, {"DELIVERY_DATE": DAY, "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
                                     "GITHUB_SHA": SHA, "GH_TOKEN": TOKEN, "GITHUB_OUTPUT": "/tmp/test-claim-output"}, clear=False), \
             patch("src.daily_claim.claim", side_effect=lambda *args, **kwargs: claim(*args, http=http, **kwargs)), \
             patch("src.daily_claim._today", return_value=date(2026, 9, 17)), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            with patch("builtins.open", unittest.mock.mock_open()) as opened:
                self.assertEqual(0, main())
                written = opened().write.call_args_list
        self.assertEqual("daily_claim=exists day=2026-09-17\n", output.getvalue())
        self.assertEqual([unittest.mock.call("claimed=false\nday=2026-09-17\n")], written)
        self.assertEqual({"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}, http.calls[1][2]["headers"])
        self.assertEqual((10, False), (http.calls[1][2]["timeout"], http.calls[1][2]["allow_redirects"]))

    def test_cli_success_writes_only_safe_output(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"DELIVERY_DATE": DAY, "GITHUB_REPOSITORY": "carloshuangspec/wechat-ldr-daily-push",
                                     "GITHUB_SHA": SHA, "GH_TOKEN": TOKEN, "GITHUB_OUTPUT": "/tmp/test-claim-output"}, clear=False), \
             patch("src.daily_claim.claim", return_value=True), contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            with patch("builtins.open", unittest.mock.mock_open()) as opened:
                self.assertEqual(0, main())
                written = opened().write.call_args_list
        self.assertEqual("daily_claim=created day=2026-09-17\n", output.getvalue())
        self.assertEqual([unittest.mock.call("claimed=true\nday=2026-09-17\n")], written)
        self.assertNotIn(TOKEN, output.getvalue())

    def test_cli_error_hides_token_and_response(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"DELIVERY_DATE": DAY, "GITHUB_REPOSITORY": "bad/repo",
                                     "GITHUB_SHA": SHA, "GH_TOKEN": TOKEN}, clear=False), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(2, main())
        self.assertEqual("", out.getvalue())
        self.assertEqual("daily_claim_failed\n", err.getvalue())
        self.assertNotIn(TOKEN, err.getvalue())


if __name__ == "__main__":
    unittest.main()
