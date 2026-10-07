"""知乎 OAuth 2.0 第三方登录。需预先向知乎申请 app_id/app_key。"""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse

import requests

from apis.errors import ZhihuAPIError


class ZhihuOAuth:
    AUTHORIZE_URL = "https://openapi.zhihu.com/authorize"
    TOKEN_URL = "https://openapi.zhihu.com/access_token"

    def __init__(
        self,
        app_id: str,
        app_key: str,
        redirect_uri: str,
        *,
        session: requests.Session | None = None,
        timeout: float = 20,
    ) -> None:
        if not app_id or not app_key:
            raise ValueError("app_id 和 app_key 不能为空")
        parsed = urlparse(redirect_uri)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("redirect_uri 必须是完整 HTTP(S) URL")
        self.app_id = app_id
        self._app_key = app_key
        self.redirect_uri = redirect_uri
        self._session = session or requests.Session()
        self._timeout = timeout

    def close(self) -> None:
        self._session.close()

    def authorization_url(self) -> str:
        params = {
            "redirect_uri": self.redirect_uri,
            "app_id": self.app_id,
            "response_type": "code",
        }
        return self.AUTHORIZE_URL + "?" + urlencode(params)

    def authorization_code_from_callback(self, callback_url: str) -> str:
        """从已注册回调地址提取知乎返回的 authorization_code。"""
        expected = urlparse(self.redirect_uri)
        callback = urlparse(callback_url)
        if (callback.scheme, callback.netloc.lower(), callback.path) != (
            expected.scheme, expected.netloc.lower(), expected.path
        ):
            raise ValueError("OAuth 回调地址与 redirect_uri 不一致")
        params = parse_qs(callback.query, keep_blank_values=True)
        for key, values in parse_qs(expected.query, keep_blank_values=True).items():
            if params.get(key) != values:
                raise ValueError("OAuth 回调地址缺少 redirect_uri 原有参数")
        if params.get("error"):
            raise ZhihuAPIError(f"OAuth 授权失败：{params['error'][0]}")
        codes = params.get("authorization_code", [])
        if len(codes) != 1 or not codes[0]:
            raise ValueError("OAuth 回调需要且只能包含一个 authorization_code")
        return codes[0]

    def exchange_code(self, authorization_code: str) -> dict:
        if not isinstance(authorization_code, str) or not authorization_code:
            raise ValueError("authorization_code 不能为空")
        response = self._session.request(
            "POST",
            self.TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "app_id": self.app_id,
                "app_key": self._app_key,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
                "code": authorization_code,
            },
            timeout=self._timeout,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ZhihuAPIError("OAuth 返回非 JSON 响应", http_status=response.status_code) from exc
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if response.status_code >= 400 or not isinstance(token, str) or not token.strip():
            message = payload.get("message") or payload.get("msg") if isinstance(payload, dict) else None
            raise ZhihuAPIError(str(message or "OAuth 授权码交换失败"), http_status=response.status_code)
        return payload
