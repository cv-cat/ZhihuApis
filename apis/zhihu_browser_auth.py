"""可见浏览器辅助登录；二维码由知乎页面展示，用户自行扫码。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


SIGNIN_URL = "https://www.zhihu.com/signin?next=%2F"
ME_URL = "https://www.zhihu.com/api/v4/me"
HOME_URL = "https://www.zhihu.com/"

# 只返回 HTTP 状态与登录判定，不将接口里的个人资料或 Cookie 带出浏览器。
_LOGIN_PROBE = """async () => {
    const response = await fetch('/api/v4/me', {credentials: 'include', cache: 'no-store'});
    let userType = null;
    try {
        const body = await response.json();
        userType = body?.user_type ?? body?.userType ?? null;
    } catch (_) {}
    return {http_status: response.status, user_type: userType};
}"""


@dataclass(frozen=True)
class BrowserLoginState:
    authenticated: bool | None
    http_status: int | None
    reason: str


def classify_login_probe(http_status: int | None, user_type: object) -> BrowserLoginState:
    """只有 200 且明确为非 guest 用户才确认登录。"""
    if http_status == 401:
        return BrowserLoginState(None, 401, "unauthorized_or_rejected")
    if http_status != 200:
        return BrowserLoginState(None, http_status, "request_unavailable")
    if user_type == "guest":
        return BrowserLoginState(False, 200, "guest")
    if isinstance(user_type, str) and user_type:
        return BrowserLoginState(True, 200, "authenticated")
    return BrowserLoginState(None, 200, "response_unrecognized")


class ZhihuBrowserAuth:
    """持有浏览器本人会话；不导出 Cookie，也不将其用于官方 OAuth。"""

    def __init__(
        self,
        *,
        profile_dir: str | Path | None = None,
        channel: str = "chrome",
        playwright_factory: Callable | None = None,
    ) -> None:
        if profile_dir is not None and not str(profile_dir).strip():
            raise ValueError("profile_dir 不能为空")
        self.profile_dir = Path(profile_dir).resolve() if profile_dir is not None else None
        self.channel = channel
        self._playwright_factory = playwright_factory
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._observed_state = None
        self._observed_at = 0.0

    def start(self) -> None:
        if self._context is not None:
            return
        if self._playwright_factory is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:
                raise RuntimeError("请先安装 requirements-browser.txt") from exc
            self._playwright = sync_playwright().start()
        else:
            self._playwright = self._playwright_factory()
        try:
            if self.profile_dir is None:
                self._browser = self._playwright.chromium.launch(channel=self.channel, headless=False)
                self._context = self._browser.new_context(accept_downloads=False)
            else:
                self.profile_dir.mkdir(parents=True, exist_ok=True)
                self._context = self._playwright.chromium.launch_persistent_context(
                    str(self.profile_dir), channel=self.channel, headless=False, accept_downloads=False
                )
            self._page = self._context.new_page()
            self._page.on("response", self._observe_account_response)
        except Exception:
            self.close()
            raise

    def _observe_account_response(self, response) -> None:
        """只观察知乎页面自己发起的账户请求，不读取 Cookie。"""
        if response.url.split("?", 1)[0] != ME_URL:
            return
        try:
            payload = response.json()
        except Exception:
            payload = None
        user_type = (payload.get("user_type") or payload.get("userType")) if isinstance(payload, dict) else None
        self._observed_state = classify_login_probe(response.status, user_type)
        self._observed_at = time.monotonic()

    def _recent_observed_state(self) -> BrowserLoginState | None:
        if self._observed_state is not None and time.monotonic() - self._observed_at <= 10:
            return self._observed_state
        return None

    def open_login(self) -> None:
        """显示知乎登录页。二维码的生成、刷新和扫码由页面及用户完成。"""
        self.start()
        self._page.goto(SIGNIN_URL, wait_until="domcontentloaded")

    def login_state(self) -> BrowserLoginState:
        """在已打开的知乎页发起只读 GET /api/v4/me，不返回个人资料。"""
        if self._page is None:
            raise RuntimeError("请先调用 open_login()")
        try:
            result = self._page.evaluate(_LOGIN_PROBE)
        except Exception:
            return self._recent_observed_state() or BrowserLoginState(None, None, "request_unavailable")
        if not isinstance(result, dict):
            return self._recent_observed_state() or BrowserLoginState(None, None, "response_unrecognized")
        state = classify_login_probe(result.get("http_status"), result.get("user_type"))
        if state.authenticated is not None:
            return state
        return self._recent_observed_state() or state

    def verify_account(self, *, timeout_seconds: float = 8) -> BrowserLoginState:
        """扫码后打开首页，观察页面自己的账号请求，再做只读账号态核验。"""
        if self._page is None:
            raise RuntimeError("请先调用 open_login()")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")
        self._observed_state = None
        self._observed_at = 0.0
        self._page.goto(HOME_URL, wait_until="domcontentloaded")
        deadline = time.monotonic() + timeout_seconds
        while True:
            state = self.login_state()
            if state.authenticated is not None or time.monotonic() >= deadline:
                return state
            time.sleep(min(0.5, max(0, deadline - time.monotonic())))

    def wait_for_login(self, *, timeout_seconds: float = 180, poll_interval: float = 2) -> BrowserLoginState:
        """等待用户在可见页面扫码；超时后保留页面供用户查看。"""
        if timeout_seconds <= 0 or poll_interval <= 0:
            raise ValueError("超时和轮询间隔必须大于 0")
        deadline = time.monotonic() + timeout_seconds
        while True:
            state = self.login_state()
            if state.authenticated is True:
                return state
            if time.monotonic() >= deadline:
                raise TimeoutError(f"等待知乎扫码登录超时，最后状态：{state.reason}")
            time.sleep(min(poll_interval, max(0, deadline - time.monotonic())))

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._page = None
        self._observed_state = None
        self._observed_at = 0.0

    def __enter__(self) -> "ZhihuBrowserAuth":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
