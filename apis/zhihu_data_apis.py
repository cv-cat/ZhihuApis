"""知乎数据开放平台的读取接口。

文档：https://developer.zhihu.com/console/api/v3/docs
此客户端只用 Access Secret；OAuth 用户令牌仅在已授权用户内容接口作为附加身份。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from urllib.parse import urlparse

import requests

from apis.errors import ZhihuAPIError


class ZhihuDataAPI:
    BASE_URL = "https://developer.zhihu.com"
    CONTENT_TYPES = frozenset({"all", "answer", "article", "zvideo", "pin", "question"})

    def __init__(
        self,
        access_secret: str,
        *,
        session: requests.Session | None = None,
        timeout: float = 20,
        timestamp: Callable[[], float] = time.time,
    ) -> None:
        if not access_secret or not access_secret.strip():
            raise ValueError("access_secret 不能为空")
        self._access_secret = access_secret.strip()
        self._session = session or requests.Session()
        self._timeout = timeout
        self._timestamp = timestamp

    def close(self) -> None:
        self._session.close()

    def _get(self, path: str, *, params: dict[str, object], oauth_token: str | None = None) -> dict:
        headers = {
            "Authorization": f"Bearer {self._access_secret}",
            "X-Request-Timestamp": str(int(self._timestamp())),
            "Content-Type": "application/json",
        }
        if oauth_token:
            headers["X-OAuth-Token"] = oauth_token
        response = self._session.request(
            "GET", self.BASE_URL + path, params=params, headers=headers, timeout=self._timeout
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ZhihuAPIError("知乎返回非 JSON 响应", http_status=response.status_code) from exc
        if not isinstance(payload, dict):
            raise ZhihuAPIError("知乎返回格式异常", http_status=response.status_code)
        code = payload.get("Code")
        if response.status_code >= 400 or code != 0:
            raise ZhihuAPIError(
                str(payload.get("Message") or "知乎数据接口请求失败"),
                code=code if isinstance(code, int) else None,
                http_status=response.status_code,
            )
        data = payload.get("Data")
        if not isinstance(data, dict):
            raise ZhihuAPIError("知乎响应缺少 Data", code=0, http_status=response.status_code)
        return data

    @staticmethod
    def _check_zhihu_url(value: str) -> None:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not (parsed.hostname == "zhihu.com" or (parsed.hostname or "").endswith(".zhihu.com")):
            raise ValueError("需要知乎 HTTPS 内容链接")

    def search(self, query: str, *, count: int = 10, sort_by: str | None = None) -> dict:
        """站内搜索。官方单次最多返回 10 项，当前 HasMore 固定为 false。"""
        if not query or not query.strip():
            raise ValueError("query 不能为空")
        if not 1 <= count <= 10:
            raise ValueError("count 范围为 1-10")
        params: dict[str, object] = {"Query": query, "Count": count}
        if sort_by is not None:
            params["SortBy"] = sort_by
        return self._get("/api/v1/content/zhihu_search", params=params)

    def get_item(self, content_url: str) -> dict:
        """获取当前 Access Secret 所属账号的已发布创作全文。"""
        self._check_zhihu_url(content_url)
        return self._get("/api/v1/user/content_detail", params={"ContentUrl": content_url})

    def list_user_contents(
        self,
        *,
        content_type: str = "all",
        offset: int = 0,
        limit: int = 20,
        oauth_token: str | None = None,
        sort_field: str = "ts",
        sort_order: str = "desc",
    ) -> dict:
        """列出本人或 OAuth 已授权用户公开范围的创作摘要。"""
        if content_type not in self.CONTENT_TYPES:
            raise ValueError("content_type 不在官方支持范围")
        if offset < 0 or not 1 <= limit <= 50:
            raise ValueError("offset 或 limit 超出范围")
        if sort_field not in {"ts", "like_count"} or sort_order not in {"asc", "desc"}:
            raise ValueError("排序参数无效")
        return self._get(
            "/api/v1/user/contents",
            params={
                "ContentType": content_type,
                "Offset": offset,
                "Limit": limit,
                "SortField": sort_field,
                "SortOrder": sort_order,
            },
            oauth_token=oauth_token,
        )

    def question_answers(self, question_url: str, *, offset: int = 0, limit: int = 20) -> dict:
        """获取问题下的回答摘要；不是回答全文或发布接口。"""
        self._check_zhihu_url(question_url)
        if "/question/" not in urlparse(question_url).path:
            raise ValueError("需要知乎问题链接")
        if offset < 0 or not 1 <= limit <= 50:
            raise ValueError("offset 或 limit 超出范围")
        return self._get(
            "/api/v1/content/question_answers",
            params={"QuestionUrl": question_url, "Offset": offset, "Limit": limit},
        )
