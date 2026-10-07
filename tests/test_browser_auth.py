"""浏览器登录助手的离线契约测试，不启动 Chrome。"""

import tempfile
import unittest
from pathlib import Path

from apis.zhihu_browser_auth import (
    HOME_URL,
    ME_URL,
    SIGNIN_URL,
    ZhihuBrowserAuth,
    classify_login_probe,
)


class FakeResponse:
    url = ME_URL
    status = 200

    def json(self):
        return {"user_type": "people"}


class FakePage:
    def __init__(self):
        self.urls = []
        self.probe_results = []
        self.response_handler = None
        self.probe_script = ""
        self.emit_on_home = False

    def on(self, event, handler):
        assert event == "response"
        self.response_handler = handler

    def goto(self, url, **kwargs):
        self.urls.append(url)
        if url == HOME_URL and self.emit_on_home:
            self.response_handler(FakeResponse())

    def evaluate(self, script):
        self.probe_script = script
        return self.probe_results.pop(0) if self.probe_results else {"http_status": 401, "user_type": None}


class FakeContext:
    def __init__(self):
        self.page = FakePage()
        self.closed = False
        self.cookies_added = []

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True

    def add_cookies(self, cookies):
        self.cookies_added.extend(cookies)


class FakeBrowser:
    def __init__(self, context):
        self.context = context
        self.closed = False
        self.new_context_kwargs = None

    def new_context(self, **kwargs):
        self.new_context_kwargs = kwargs
        return self.context

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self):
        self.context = FakeContext()
        self.browser = FakeBrowser(self.context)
        self.launch_kwargs = None
        self.persistent_args = None

    def launch(self, **kwargs):
        self.launch_kwargs = kwargs
        return self.browser

    def launch_persistent_context(self, *args, **kwargs):
        self.persistent_args = (args, kwargs)
        return self.context


class FakePlaywright:
    def __init__(self):
        self.chromium = FakeChromium()
        self.stopped = False

    def stop(self):
        self.stopped = True


class BrowserAuthTests(unittest.TestCase):
    def test_login_state_requires_positive_account_evidence(self):
        self.assertIsNone(classify_login_probe(401, None).authenticated)
        self.assertFalse(classify_login_probe(200, "guest").authenticated)
        self.assertTrue(classify_login_probe(200, "people").authenticated)
        self.assertIsNone(classify_login_probe(200, None).authenticated)

    def test_visible_memory_browser_waits_for_user_scan(self):
        playwright = FakePlaywright()
        page = playwright.chromium.context.page
        page.probe_results = [
            {"http_status": 401, "user_type": None},
            {"http_status": 200, "user_type": "people"},
        ]
        auth = ZhihuBrowserAuth(playwright_factory=lambda: playwright)
        auth.open_login()
        self.assertEqual(page.urls, [SIGNIN_URL])
        self.assertEqual(playwright.chromium.launch_kwargs, {"channel": "chrome", "headless": False})
        self.assertEqual(playwright.chromium.browser.new_context_kwargs, {"accept_downloads": False})
        self.assertTrue(auth.wait_for_login(timeout_seconds=1, poll_interval=0.01).authenticated)
        self.assertIn("/api/v4/me", page.probe_script)
        self.assertNotIn("document.cookie", page.probe_script)
        auth.close()
        self.assertTrue(playwright.chromium.context.closed)
        self.assertTrue(playwright.chromium.browser.closed)
        self.assertTrue(playwright.stopped)

    def test_homepage_can_verify_site_issued_read_only_account_response(self):
        playwright = FakePlaywright()
        page = playwright.chromium.context.page
        page.emit_on_home = True
        auth = ZhihuBrowserAuth(playwright_factory=lambda: playwright)
        auth.open_login()
        state = auth.verify_account(timeout_seconds=0.1)
        self.assertEqual(page.urls[-1], HOME_URL)
        self.assertTrue(state.authenticated)
        self.assertEqual(state.reason, "authenticated")
        auth.close()

    def test_profile_mode_uses_separate_ignored_directory(self):
        playwright = FakePlaywright()
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="zhihu-browser-test-", dir=repo) as tempdir:
            profile = Path(tempdir) / "profile"
            auth = ZhihuBrowserAuth(profile_dir=profile, playwright_factory=lambda: playwright)
            auth.open_login()
            args, kwargs = playwright.chromium.persistent_args
            self.assertEqual(args, (str(profile.resolve()),))
            self.assertEqual(kwargs["headless"], False)
            self.assertTrue(profile.exists())
            auth.close()
            self.assertTrue(playwright.chromium.context.closed)
            self.assertTrue(playwright.stopped)

    def test_temporary_context_imports_cookie_without_persistent_profile(self):
        playwright = FakePlaywright()
        playwright.chromium.context.page.emit_on_home = True
        auth = ZhihuBrowserAuth(headless=True, playwright_factory=lambda: playwright)
        auth.import_cookie_header("z_c0=token=part; __Host-probe=ok;")
        self.assertEqual(playwright.chromium.launch_kwargs, {"channel": "chrome", "headless": True})
        self.assertEqual(playwright.chromium.browser.new_context_kwargs, {"accept_downloads": False})
        cookies = playwright.chromium.context.cookies_added
        self.assertEqual(len(cookies), 2)
        self.assertEqual(cookies[0]["value"], "token=part")
        self.assertEqual(cookies[0]["domain"], ".zhihu.com")
        self.assertEqual(cookies[1]["url"], HOME_URL)
        self.assertTrue(auth.verify_account(timeout_seconds=0.1).authenticated)
        auth.close()
        self.assertTrue(playwright.chromium.context.closed)

    def test_cookie_import_rejects_persistent_profile_and_malformed_header(self):
        playwright = FakePlaywright()
        auth = ZhihuBrowserAuth(profile_dir="ignored-profile", playwright_factory=lambda: playwright)
        with self.assertRaises(ValueError):
            auth.import_cookie_header("z_c0=temporary")
        self.assertIsNone(playwright.chromium.launch_kwargs)

        auth = ZhihuBrowserAuth(playwright_factory=lambda: playwright)
        for header in ("", "missing-equals", "bad name=value"):
            with self.assertRaises(ValueError):
                auth.import_cookie_header(header)
        self.assertIsNone(playwright.chromium.launch_kwargs)


if __name__ == "__main__":
    unittest.main()
