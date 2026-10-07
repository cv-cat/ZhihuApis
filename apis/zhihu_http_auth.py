"""知乎网页会话的纯 HTTP 鉴权与登录接口。

本模块只使用 :mod:`requests`。二维码登录与短信登录接口的路径、字段
来自知乎当前网页脚本；二维码扫码由用户在知乎 App 完成，验证码只接受
知乎返回的人工验证票据，不尝试生成、绕过或破解验证码。
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests

from apis.errors import UnsupportedCapabilityError, ZhihuAPIError

BASE_URL = "https://www.zhihu.com"
SIGNIN_URL = f"{BASE_URL}/signin?next=%2F"
HOME_URL = f"{BASE_URL}/"
ME_URL = f"{BASE_URL}/api/v4/me"
UDID_URL = f"{BASE_URL}/udid"
QR_TOKEN_URL = f"{BASE_URL}/api/v3/account/api/login/qrcode"
QR_STATUS_URL = f"{BASE_URL}/api/v3/account/api/login/qrcode/{{token}}/scan_info"
SMS_SUPPORTED_COUNTRIES_URL = f"{BASE_URL}/api/v3/oauth/sms/supported_countries"
SMS_CODE_URL = f"{BASE_URL}/api/v3/oauth/sign_in/digits"
SMS_VALIDATE_URL = f"{BASE_URL}/api/v3/oauth/validate/sign_in/digits"
PASSWORD_LOGIN_URL = f"{BASE_URL}/api/v3/oauth/sign_in"
CAPTCHA_URL = f"{BASE_URL}/api/v3/oauth/captcha/v2"

_COOKIE_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class LoginState:
    """只包含账号态判定和 HTTP 状态，不暴露 Cookie 或个人资料。"""

    authenticated: bool | None
    http_status: int | None
    reason: str
    user_type: str | None = None


def classify_login_probe(http_status: int | None, user_type: object) -> LoginState:
    """只有 ``/api/v4/me`` 200 且明确非 guest 才算登录。"""
    if http_status in {401, 403}:
        return LoginState(None, http_status, "unauthorized_or_rejected")
    if http_status != 200:
        return LoginState(None, http_status, "request_unavailable")
    if user_type == "guest":
        return LoginState(False, 200, "guest", "guest")
    if isinstance(user_type, str) and user_type:
        return LoginState(True, 200, "authenticated", user_type)
    return LoginState(None, 200, "response_unrecognized")


@dataclass(frozen=True)
class QRLoginChallenge:
    token: str
    link: str
    expires_at: int | float | None = None

    @property
    def qr_text(self) -> str:
        """交给二维码渲染器的原始文本；客户端不依赖任何 GUI。"""
        return self.link


@dataclass(frozen=True)
class QRLoginState:
    token: str
    status: int | str | None
    authenticated: bool
    http_status: int
    verification_required: bool = False
    payload: Mapping[str, Any] | None = None


class HumanVerificationRequired(ZhihuAPIError):
    """知乎要求在官方验证页完成人工验证；客户端不自动处理验证码。"""


class ZhihuHTTPAuth:
    """纯 HTTP 的知乎网页会话。

    可从本人复制的完整 ``Cookie`` 请求头建立临时会话，也可把外部
    ``requests.Session`` 注入进行测试。库不把 Cookie 写入文件或日志。
    """

    def __init__(
        self,
        *,
        session: requests.Session | Any | None = None,
        cookie_header: str | None = None,
        timeout: float = 20,
        user_agent: str = _DEFAULT_UA,
        body_encryptor: Callable[[Mapping[str, Any]], tuple[str, Mapping[str, str]]] | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout 必须大于 0")
        if not isinstance(user_agent, str) or not user_agent.strip():
            raise ValueError("user_agent 不能为空")
        self._session = session if session is not None else requests.Session()
        self.timeout = float(timeout)
        self._body_encryptor = body_encryptor
        self._duid = None
        headers = {
            "User-Agent": user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": SIGNIN_URL,
            "Origin": BASE_URL,
            "X-Requested-With": "fetch",
        }
        if hasattr(self._session, "headers"):
            self._session.headers.update(headers)
        if cookie_header is not None:
            self.import_cookie_header(cookie_header)

    @classmethod
    def from_cookie(cls, cookie_header: str, **kwargs) -> "ZhihuHTTPAuth":
        return cls(cookie_header=cookie_header, **kwargs)

    @classmethod
    def from_cookie_header(cls, cookie_header: str, **kwargs) -> "ZhihuHTTPAuth":
        return cls.from_cookie(cookie_header, **kwargs)

    @property
    def session(self):
        return self._session

    def close(self) -> None:
        close = getattr(self._session, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> "ZhihuHTTPAuth":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def import_cookie_header(self, cookie_header: str) -> None:
        if not isinstance(cookie_header, str) or not cookie_header.strip():
            raise ValueError("Cookie 不能为空")
        pairs: list[tuple[str, str]] = []
        for part in cookie_header.split(";"):
            part = part.strip()
            if not part:
                continue
            name, sep, value = part.partition("=")
            if not sep or not _COOKIE_NAME.fullmatch(name.strip()):
                raise ValueError("Cookie 格式无效")
            pairs.append((name.strip(), value))
        if not pairs:
            raise ValueError("Cookie 不能为空")
        cookies = getattr(self._session, "cookies", None)
        if cookies is None or not hasattr(cookies, "set"):
            raise TypeError("注入的 session 不支持 Cookie")
        for name, value in pairs:
            cookies.set(name, value, domain=".zhihu.com", path="/")

    def open_login(self):
        """用 HTTP 读取登录页，返回 ``requests.Response``；不启动任何窗口。"""
        return self._request("GET", SIGNIN_URL, allow_redirects=False)

    def login_state(self) -> LoginState:
        response = self._request("GET", ME_URL, allow_redirects=False)
        # 401/403 是账号未授权或风控拒绝的有效探针结果。某些风控页返回
        # HTML，因此这里不能先强制解析 JSON。
        if response.status_code in {401, 403}:
            return classify_login_probe(response.status_code, None)
        payload = self._json(response, "账号状态接口")
        user_type = payload.get("user_type", payload.get("userType")) if isinstance(payload, dict) else None
        return classify_login_probe(response.status_code, user_type)

    def verify_account(self) -> LoginState:
        return self.login_state()

    def wait_for_login(self, *, timeout_seconds: float = 180, poll_interval: float = 2) -> LoginState:
        if timeout_seconds <= 0 or poll_interval <= 0:
            raise ValueError("超时和轮询间隔必须大于 0")
        deadline = time.monotonic() + timeout_seconds
        state = LoginState(None, None, "not_checked")
        while True:
            state = self.login_state()
            if state.authenticated is not None:
                return state
            if time.monotonic() >= deadline:
                raise TimeoutError(f"等待登录态超时，最后状态：{state.reason}")
            time.sleep(min(poll_interval, max(0, deadline - time.monotonic())))

    def ensure_browser_id(self) -> str:
        """按知乎网页的 ``POST /udid`` 生成本会话的浏览器 ID。"""
        if self._duid:
            return self._duid
        response = self._request("POST", UDID_URL, allow_redirects=False)
        if response.status_code != 200:
            raise ZhihuAPIError("知乎浏览器 ID 请求失败", http_status=response.status_code)
        value = response.text.strip()
        if not value or len(value) > 256:
            raise ZhihuAPIError("知乎浏览器 ID 响应格式异常", http_status=response.status_code)
        self._duid = value
        if hasattr(self._session, "headers"):
            self._session.headers["x-du-bid"] = value
        return value

    def begin_qr_login(self) -> QRLoginChallenge:
        """请求知乎网页二维码登录 token，二维码文本是响应中的 ``link``。"""
        self.ensure_browser_id()
        response = self._request("POST", QR_TOKEN_URL, allow_redirects=False)
        payload = self._json(response, "二维码 token 接口")
        if response.status_code != 200:
            raise self._error_from_payload("二维码 token 请求失败", response, payload)
        token = payload.get("token") if isinstance(payload, dict) else None
        link = payload.get("link") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token or not isinstance(link, str) or not link:
            raise ZhihuAPIError("二维码 token 响应缺少 token/link", http_status=response.status_code)
        expires = payload.get("expires_at")
        return QRLoginChallenge(token=token, link=link, expires_at=expires)

    def poll_qr_login(self, challenge: QRLoginChallenge | str) -> QRLoginState:
        token = challenge.token if isinstance(challenge, QRLoginChallenge) else challenge
        if not isinstance(token, str) or not token:
            raise ValueError("二维码 token 不能为空")
        self.ensure_browser_id()
        response = self._request("GET", QR_STATUS_URL.format(token=token), allow_redirects=False)
        payload = self._json(response, "二维码状态接口")
        if response.status_code == 403 and isinstance(payload, dict) and payload.get("error", {}).get("code") == 40352:
            return QRLoginState(token, None, False, response.status_code, True, payload)
        if response.status_code != 200:
            raise self._error_from_payload("二维码状态请求失败", response, payload)
        if not isinstance(payload, dict):
            raise ZhihuAPIError("二维码状态响应格式异常", http_status=response.status_code)
        access = payload.get("accessToken") or payload.get("access_token")
        authenticated = bool(access)
        if authenticated:
            # 站点通常通过 Set-Cookie 写入网页会话；最终以 /api/v4/me 为准。
            state = self.login_state()
            authenticated = state.authenticated is True
        return QRLoginState(token, payload.get("status"), authenticated, response.status_code, False, payload)

    def wait_for_qr_login(self, challenge: QRLoginChallenge, *, timeout_seconds: float = 180, poll_interval: float = 2) -> LoginState:
        if timeout_seconds <= 0 or poll_interval <= 0:
            raise ValueError("超时和轮询间隔必须大于 0")
        deadline = time.monotonic() + timeout_seconds
        while True:
            result = self.poll_qr_login(challenge)
            if result.verification_required:
                raise HumanVerificationRequired(
                    "知乎要求完成人工安全验证；请在知乎官方页面完成验证后重新轮询",
                    http_status=result.http_status,
                )
            if result.authenticated:
                return self.login_state()
            if time.monotonic() >= deadline:
                raise TimeoutError("等待知乎二维码扫码确认超时")
            time.sleep(min(poll_interval, max(0, deadline - time.monotonic())))

    def get_captcha(self, *, scene: str = "digits_login") -> dict:
        if not isinstance(scene, str) or not scene.strip():
            raise ValueError("scene 不能为空")
        response = self._request(
            "GET", CAPTCHA_URL, params={"type": "captcha_sign_in", "scene": scene.strip()}, allow_redirects=False
        )
        payload = self._json(response, "验证码接口")
        if response.status_code != 200:
            raise self._error_from_payload("验证码请求失败", response, payload)
        if not isinstance(payload, dict):
            raise ZhihuAPIError("验证码响应格式异常", http_status=response.status_code)
        return payload

    def validate_captcha(self, ticket: str, *, scene: str = "digits_login") -> dict:
        if not isinstance(ticket, str) or not ticket.strip():
            raise ValueError("ticket 不能为空")
        response = self._request(
            "PUT", CAPTCHA_URL, data={"ticket": ticket.strip(), "scene": scene}, allow_redirects=False
        )
        payload = self._json(response, "验证码校验接口")
        if response.status_code != 200:
            raise self._error_from_payload("验证码校验失败", response, payload)
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise ZhihuAPIError("验证码未通过", http_status=response.status_code)
        return payload

    def supported_sms_countries(self) -> dict:
        response = self._request("GET", SMS_SUPPORTED_COUNTRIES_URL, allow_redirects=False)
        payload = self._json(response, "短信国家列表接口")
        if response.status_code != 200:
            raise self._error_from_payload("短信国家列表请求失败", response, payload)
        return payload if isinstance(payload, dict) else {"data": payload}

    def request_sms_code(
        self,
        phone_no: str,
        *,
        sms_type: str = "text",
        captcha_ticket: str | None = None,
        encrypted_body: str | None = None,
    ) -> dict:
        """请求短信验证码。

        网页端会先用动态 ``zsEncrypt`` 加密 ``phone_no``，并可能要求人工
        验证。调用者可传入自己按当前页面抓包得到的加密 body；缺少它时
        明确停止，不把明文伪装成已对齐协议。
        """
        if not isinstance(phone_no, str) or not phone_no.strip():
            raise ValueError("phone_no 不能为空")
        if sms_type not in {"text", "voice"}:
            raise ValueError("sms_type 必须为 text 或 voice")
        body = {"phone_no": phone_no.strip(), "sms_type": sms_type}
        if captcha_ticket:
            body["captcha_ticket"] = captcha_ticket
        encrypted_body, extra_headers = self._encrypted_body(body, encrypted_body)
        response = self._request(
            "POST", SMS_CODE_URL, data=encrypted_body, headers={"Content-Type": "application/x-www-form-urlencoded", **dict(extra_headers)}, allow_redirects=False
        )
        payload = self._json(response, "短信接口")
        if response.status_code != 200:
            raise self._error_from_payload("短信验证码请求失败", response, payload)
        return payload if isinstance(payload, dict) else {"data": payload}

    def validate_sms_code(
        self,
        phone_no: str,
        code: str,
        *,
        scene: str = "digits_login",
        encrypted_body: str | None = None,
    ) -> LoginState:
        """提交短信验证码并用 ``/api/v4/me`` 确认登录态。

        知乎网页会对手机号和验证码执行动态 ``zsEncrypt``。本方法只接受
        调用方提供的当前加密请求体，或者由 ``body_encryptor`` 注入已验证
        的实现；不会把明文请求伪装成可用协议。
        """
        if not isinstance(phone_no, str) or not phone_no.strip():
            raise ValueError("phone_no 不能为空")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("code 不能为空")
        if not isinstance(scene, str) or not scene.strip():
            raise ValueError("scene 不能为空")
        body = {"phone_no": phone_no.strip(), "code": code.strip(), "scene": scene.strip()}
        encrypted_body, extra_headers = self._encrypted_body(body, encrypted_body)
        response = self._request(
            "POST",
            SMS_VALIDATE_URL,
            data=encrypted_body,
            headers={"Content-Type": "application/x-www-form-urlencoded", **extra_headers},
            allow_redirects=False,
        )
        payload = self._json(response, "短信校验接口")
        if response.status_code != 200:
            raise self._error_from_payload("短信校验请求失败", response, payload)
        # 接口响应有时只表示校验已接收，账号态仍以 /api/v4/me 为准。
        state = self.login_state()
        if state.authenticated is True:
            return state
        if isinstance(payload, dict) and payload.get("success") is False:
            raise ZhihuAPIError("短信验证码未通过", http_status=response.status_code)
        return state

    def login_with_password(
        self,
        username: str,
        password: str,
        *,
        scene: str = "password_login",
        encrypted_body: str | None = None,
    ) -> LoginState:
        """提交密码登录请求，并以账号探针确认结果。

        密码只在调用栈内使用，不写入日志；请求体必须由当前网页加密链路
        生成，避免向知乎发送未经验证的明文字段。
        """
        if not isinstance(username, str) or not username.strip():
            raise ValueError("username 不能为空")
        if not isinstance(password, str) or not password:
            raise ValueError("password 不能为空")
        if not isinstance(scene, str) or not scene.strip():
            raise ValueError("scene 不能为空")
        body = {"username": username.strip(), "password": password, "scene": scene.strip()}
        encrypted_body, extra_headers = self._encrypted_body(body, encrypted_body)
        response = self._request(
            "POST",
            PASSWORD_LOGIN_URL,
            data=encrypted_body,
            headers={"Content-Type": "application/x-www-form-urlencoded", **extra_headers},
            allow_redirects=False,
        )
        payload = self._json(response, "密码登录接口")
        if response.status_code != 200:
            raise self._error_from_payload("密码登录请求失败", response, payload)
        state = self.login_state()
        if state.authenticated is True:
            return state
        if isinstance(payload, dict) and payload.get("success") is False:
            raise ZhihuAPIError("密码登录未通过", http_status=response.status_code)
        return state

    def _encrypted_body(
        self,
        body: Mapping[str, Any],
        encrypted_body: str | None,
    ) -> tuple[str, Mapping[str, str]]:
        if encrypted_body is not None:
            if not isinstance(encrypted_body, str) or not encrypted_body:
                raise ValueError("encrypted_body 必须是非空字符串")
            return encrypted_body, {}
        if self._body_encryptor is None:
            raise UnsupportedCapabilityError(
                "知乎网页登录接口要求动态 zsEncrypt body；请传入当前抓包的 encrypted_body "
                "或注入已验证的 body_encryptor"
            )
        encrypted, headers = self._body_encryptor(body)
        if not isinstance(encrypted, str) or not encrypted:
            raise ValueError("body_encryptor 必须返回非空字符串")
        if headers is None:
            return encrypted, {}
        if not isinstance(headers, Mapping):
            raise TypeError("body_encryptor 返回的 headers 必须是映射")
        return encrypted, {str(key): str(value) for key, value in headers.items()}

    def _request(self, method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        return self._session.request(method, url, **kwargs)

    @staticmethod
    def _json(response, label: str):
        try:
            return response.json()
        except (TypeError, ValueError) as exc:
            raise ZhihuAPIError(f"{label}返回非 JSON 响应", http_status=getattr(response, "status_code", None)) from exc

    @staticmethod
    def _error_from_payload(message: str, response, payload) -> ZhihuAPIError:
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            message = str(error.get("message") or message)
            code = error.get("code") if type(error.get("code")) is int else None
        else:
            code = payload.get("code") if isinstance(payload, dict) and type(payload.get("code")) is int else None
        return ZhihuAPIError(message, code=code, http_status=getattr(response, "status_code", None))
