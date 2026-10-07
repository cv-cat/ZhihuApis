"""知乎网页接口的纯 HTTP 客户端。

请求通过注入的 ``requests.Session`` 发出，复用其 Cookie、CSRF Cookie 和
会话 Header。接口路径来自知乎网页当前实测请求；本模块不创建窗口、不执
行页面脚本，也不把登录凭据写入文件。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode, urlparse

import requests

from apis.errors import ZhihuAPIError
from apis.zhihu_http_auth import BASE_URL, ZhihuHTTPAuth


WWW_URL = BASE_URL
ZHUANLAN_URL = "https://zhuanlan.zhihu.com"


class ZhihuWebDraftSaveError(ZhihuAPIError):
    """创建已成功，但更新或回读失败；draft_id 可用于定位残留草稿。"""

    def __init__(self, message: str, *, draft_id: str) -> None:
        super().__init__(message)
        self.draft_id = draft_id


class ZhihuWebAPI:
    """使用纯 HTTP 会话访问知乎网页搜索、内容和文章草稿接口。"""

    ARTICLE_EDITOR_URL = f"{ZHUANLAN_URL}/write"
    DRAFT_URLS = {
        "answer": f"{WWW_URL}/draft?type=answer",
        "article": f"{WWW_URL}/draft?type=article",
    }

    def __init__(
        self,
        auth: ZhihuHTTPAuth | requests.Session | Any,
        *,
        session: requests.Session | Any | None = None,
        timeout: float = 20,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout 必须大于 0")
        if session is not None:
            candidate = session
        else:
            candidate = getattr(auth, "session", None)
            if candidate is None:
                candidate = auth
        if not hasattr(candidate, "request"):
            raise TypeError("auth 必须是 ZhihuHTTPAuth 或 requests.Session")
        self._auth = auth if isinstance(auth, ZhihuHTTPAuth) else None
        self._session = candidate
        self.timeout = float(timeout)
        if hasattr(self._session, "headers"):
            self._session.headers.setdefault("Accept", "application/json, text/plain, */*")

    @property
    def session(self):
        return self._session

    def _url(self, path: str, *, host: str = WWW_URL) -> str:
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise ValueError("只允许站内相对路径")
        return f"{host}{path}"

    def _xsrf_header(self) -> dict[str, str]:
        cookies = getattr(self._session, "cookies", None)
        if cookies is None or not hasattr(cookies, "get"):
            return {}
        try:
            value = cookies.get("_xsrf") or cookies.get("xsrf")
        except (KeyError, TypeError):
            value = None
        return {"x-xsrftoken": str(value)} if value else {}

    def _request(self, method: str, path: str, *, host: str = WWW_URL, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("allow_redirects", False)
        url = self._url(path, host=host)
        if self._auth is not None:
            return self._auth.request(method, url, **kwargs)
        return self._session.request(method, url, **kwargs)

    @staticmethod
    def _payload(response, label: str, *, allow_empty: bool = False):
        try:
            return response.json()
        except (TypeError, ValueError) as exc:
            raw = getattr(response, "text", "")
            if allow_empty and not raw:
                return None
            raise ZhihuAPIError(f"{label}返回非 JSON 响应", http_status=getattr(response, "status_code", None)) from exc

    @staticmethod
    def _error(message: str, response, payload: Any = None) -> ZhihuAPIError:
        error = payload.get("error") if isinstance(payload, Mapping) else None
        code = None
        if isinstance(error, Mapping):
            message = str(error.get("message") or message)
            code = error.get("code") if type(error.get("code")) is int else None
        elif isinstance(payload, Mapping):
            message = str(payload.get("message") or payload.get("msg") or message)
            code = payload.get("code") if type(payload.get("code")) is int else None
        return ZhihuAPIError(message, code=code, http_status=getattr(response, "status_code", None))

    def _get(self, path: str, *, host: str = WWW_URL) -> dict:
        response = self._request("GET", path, host=host, headers=self._xsrf_header())
        payload = self._payload(response, "知乎网页读取接口")
        if response.status_code != 200:
            raise self._error("知乎网页读取失败", response, payload)
        if not isinstance(payload, dict) or "error" in payload:
            raise self._error("知乎网页响应格式异常", response, payload)
        return payload

    def _write(self, *, path: str, method: str, body: dict | None, host: str = WWW_URL):
        if method not in {"POST", "PATCH", "DELETE"}:
            raise ValueError("写入方法无效")
        headers = {"Accept": "application/json, text/plain, */*", **self._xsrf_header()}
        kwargs: dict[str, Any] = {"headers": headers}
        if body is not None:
            headers["Content-Type"] = "application/json"
            kwargs["json"] = body
        response = self._request(method, path, host=host, **kwargs)
        payload = self._payload(response, "知乎网页写入接口", allow_empty=True)
        if not 200 <= response.status_code < 300:
            raise self._error("知乎网页写入失败", response, payload)
        if isinstance(payload, dict) and "error" in payload:
            raise self._error("知乎网页写入业务失败", response, payload)
        return payload

    def search(self, query: str, *, offset: int = 0, limit: int = 20) -> dict:
        """网页综合搜索，返回原始 ``data`` 与 ``paging``。"""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query 不能为空")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset 必须是非负整数")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise ValueError("limit 范围为 1-20")
        path = "/api/v4/search_v3?" + urlencode(
            {"t": "general", "q": query.strip(), "offset": offset, "limit": limit, "search_source": "Normal"}
        )
        payload = self._get(path)
        if not isinstance(payload.get("data"), list) or not isinstance(payload.get("paging"), dict):
            raise ZhihuAPIError("知乎搜索响应缺少 data 或 paging", http_status=200)
        return payload

    def get_answer(self, answer_id: int | str) -> dict:
        """读取回答正文。"""
        identifier = self._numeric_id(answer_id)
        path = f"/api/v4/answers/{identifier}?include=content%2Cexcerpt%2Cquestion%2Cauthor"
        payload = self._get(path)
        if not isinstance(payload.get("content"), str):
            raise ZhihuAPIError("回答响应缺少 content", http_status=200)
        return payload

    def get_article(self, article_id: int | str) -> dict:
        """从专栏接口读取文章正文。"""
        identifier = self._numeric_id(article_id)
        payload = self._get(f"/api/articles/{identifier}", host=ZHUANLAN_URL)
        if not isinstance(payload.get("content"), str):
            raise ZhihuAPIError("文章响应缺少 content", http_status=200)
        return payload

    def get_item(self, content_url: str) -> dict:
        """支持回答、专栏文章和对应 API URL。"""
        if not isinstance(content_url, str):
            raise ValueError("需要知乎内容 URL")
        parsed = urlparse(content_url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
            raise ValueError("需要知乎 HTTPS 内容 URL")
        host, path = parsed.hostname, parsed.path
        if host == "www.zhihu.com":
            match = re.fullmatch(r"/question/\d+/answer/(\d+)/?", path)
            if match:
                return self.get_answer(match.group(1))
        if host == "zhuanlan.zhihu.com":
            match = re.fullmatch(r"/p/(\d+)/?", path)
            if match:
                return self.get_article(match.group(1))
        if host == "api.zhihu.com":
            match = re.fullmatch(r"/(answers|articles)/(\d+)/?", path)
            if match:
                if match.group(1) == "answers":
                    return self.get_answer(match.group(2))
                return self.get_article(match.group(2))
        raise ValueError("当前只支持回答或文章内容 URL")

    def draft_counts(self) -> dict[str, dict]:
        """读取回答和文章草稿计数。"""
        result = {}
        for kind, path in (
            ("answer", "/api/v4/answer-drafts/count"),
            ("article", "/api/v4/articles/my_drafts/count"),
        ):
            payload = self._get(path)
            if isinstance(payload.get("count"), bool) or not isinstance(payload.get("count"), int):
                raise ZhihuAPIError("草稿计数响应格式异常", http_status=200)
            result[kind] = payload
        return result

    def save_web_draft(self, title: str, html: str) -> dict[str, str]:
        """创建文章草稿、保存 HTML 并回读确认；不会公开发布。"""
        if not isinstance(title, str) or not title.strip():
            raise ValueError("草稿标题不能为空")
        if not isinstance(html, str) or not html.strip():
            raise ValueError("草稿正文不能为空")
        title = title.strip()
        created = self._write(
            path="/api/articles/drafts",
            host=ZHUANLAN_URL,
            method="POST",
            body={"title": title, "delta_time": 0, "can_reward": False},
        )
        if not isinstance(created, dict) or created.get("state") != "draft" or created.get("type") != "article_draft":
            raise ZhihuAPIError("知乎未确认创建文章草稿", http_status=200)
        identifier = self._numeric_id(created.get("id"))
        try:
            self._write(
                path=f"/api/articles/{identifier}/draft",
                host=ZHUANLAN_URL,
                method="PATCH",
                body={"content": html, "table_of_contents": False, "delta_time": 0, "can_reward": False},
            )
            saved = self._get(f"/api/articles/{identifier}/draft", host=ZHUANLAN_URL)
            if (
                saved.get("state") != "draft"
                or saved.get("type") != "article_draft"
                or str(saved.get("id")) != identifier
                or saved.get("title") != title
                or saved.get("content") != html
            ):
                raise ZhihuAPIError("草稿回读内容与提交内容不一致", http_status=200)
        except Exception as exc:
            raise ZhihuWebDraftSaveError("草稿已创建，但正文保存或回读失败；请检查草稿箱", draft_id=identifier) from exc
        return {"id": identifier, "state": "draft", "edit_url": f"{ZHUANLAN_URL}/p/{identifier}/edit"}

    def get_web_draft(self, draft_id: int | str) -> dict:
        """回读本人文章草稿。"""
        identifier = self._numeric_id(draft_id)
        payload = self._get(f"/api/articles/{identifier}/draft", host=ZHUANLAN_URL)
        if payload.get("state") != "draft" or payload.get("type") != "article_draft":
            raise ZhihuAPIError("知乎未返回文章草稿", http_status=200)
        return payload

    def delete_web_draft(self, draft_id: int | str) -> None:
        """删除指定文章草稿。"""
        identifier = self._numeric_id(draft_id)
        self._write(path=f"/api/v4/articles/{identifier}/draft", method="DELETE", body=None)

    @staticmethod
    def _numeric_id(value: int | str) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError("内容 ID 必须是数字")
        identifier = str(value)
        if not identifier.isascii() or not identifier.isdigit():
            raise ValueError("内容 ID 必须是数字")
        return identifier
