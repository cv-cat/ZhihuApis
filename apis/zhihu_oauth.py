"""知乎 OAuth 2.0 第三方登录。需预先向知乎申请 app_id/app_key。"""

from __future__ import annotations

from urllib.parse import urlencode, urlparse

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

    def exchange_code(self, authorization_code: str) -> dict:
        if not authorization_code:
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
        if not isinstance(payload, dict) or response.status_code >= 400 or not payload.get("access_token"):
            message = payload.get("message") or payload.get("msg") if isinstance(payload, dict) else None
            raise ZhihuAPIError(str(message or "OAuth 授权码交换失败"), http_status=response.status_code)
        return payload
