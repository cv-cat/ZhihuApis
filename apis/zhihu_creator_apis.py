"""知乎官方 Publish OpenAPI。

协议：https://github.com/zhihu/ZhihuPublisher/blob/main/zhihu-publish/reference/publish-openapi.md
只支持官方已文档化的文章、提问和想法；回答发布未开放在此协议中。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid
from collections.abc import Callable, Sequence

import requests

from apis.errors import ConfirmationRequiredError, UnsupportedCapabilityError, ZhihuAPIError


class ZhihuCreatorAPI:
    BASE_URL = "https://openapi.zhihu.com"
    PUBLISH_PATH = "/openapi/publish"
    ARTICLE_COMMENT_PERMISSIONS = frozenset({"all", "nobody", "followee", "censor", "follower"})
    PIN_COMMENT_PERMISSIONS = frozenset({"all", "nobody", "followee", "censor", "follower_n_days"})
    ARTICLE_STATEMENTS = frozenset(
        {"spoiler", "medical_advice", "fictional_creation", "contain_finance", "ai_creation"}
    )

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        *,
        session: requests.Session | None = None,
        timeout: float = 30,
        timestamp: Callable[[], float] = time.time,
        log_id: Callable[[], str] = lambda: f"zhihu-apis-{uuid.uuid4().hex}",
        base_url: str = BASE_URL,
    ) -> None:
        if not app_key or not app_secret:
            raise ValueError("发布需要 ZHIHU_OPENAPI_APP_KEY 和 ZHIHU_OPENAPI_APP_SECRET")
        self._app_key = app_key
        self._app_secret = app_secret
        self._session = session or requests.Session()
        self._timeout = timeout
        self._timestamp = timestamp
        self._log_id = log_id
        self._base_url = base_url.rstrip("/")

    def close(self) -> None:
        self._session.close()

    def _auth_headers(self) -> dict[str, str]:
        ts = str(int(self._timestamp()))
        log_id = self._log_id()
        extra_info = ""
        sign_string = f"app_key:{self._app_key}|ts:{ts}|logid:{log_id}|extra_info:{extra_info}"
        signature = base64.b64encode(
            hmac.new(
                self._app_secret.encode("utf-8"),
                sign_string.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("ascii")
        return {
            "Content-Type": "application/json",
            "X-App-Key": self._app_key,
            "X-Timestamp": ts,
            "X-Log-Id": log_id,
            "X-Extra-Info": extra_info,
            "X-Sign": signature,
        }

    @staticmethod
    def _topics(tokens: Sequence[str] | None, maximum: int) -> list[dict[str, str]] | None:
        if tokens is None:
            return None
        result = []
        seen = set()
        for token in tokens:
            value = str(token)
            if not value.isdigit():
                raise ValueError("话题需传知乎话题链接中的数字 token")
            if value not in seen:
                result.append({"topic_id": "", "topic_token": value, "topic_name": ""})
                seen.add(value)
        if len(result) > maximum:
            raise ValueError(f"最多支持 {maximum} 个话题")
        return result or None

    def _publish(self, content_type: str, content: dict, *, confirmed: bool) -> dict:
        if not confirmed:
            raise ConfirmationRequiredError("请先确认预览，再以 confirmed=True 提交发布")
        body = {
            "type": content_type,
            "confirmed": True,
            "confirm_note": "confirmed by user after local preview",
            "content": content,
        }
        response = self._session.request(
            "POST",
            self._base_url + self.PUBLISH_PATH,
            headers=self._auth_headers(),
            json=body,
            timeout=self._timeout,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ZhihuAPIError("发布接口返回非 JSON 响应", http_status=response.status_code) from exc
        if not isinstance(payload, dict):
            raise ZhihuAPIError("发布接口返回格式异常", http_status=response.status_code)
        status = payload.get("status")
        if response.status_code >= 400 or type(status) is not int or status != 0:
            raise ZhihuAPIError(
                str(payload.get("msg") or "知乎发布失败"),
                code=status if type(status) is int else None,
                http_status=response.status_code,
            )
        data = payload.get("data")
        if not isinstance(data, dict) or not data.get("url") or not data.get("content_token"):
            raise ZhihuAPIError("发布成功响应缺少作品链接或 token", code=0, http_status=response.status_code)
        return payload

    def publish_article(
        self,
        title: str,
        html: str,
        *,
        confirmed: bool = False,
        comment_permission: str = "all",
        table_of_contents_enabled: bool = False,
        creation_statement: str | None = None,
        topic_tokens: Sequence[str] | None = None,
    ) -> dict:
        if not title or not html:
            raise ValueError("文章标题和 HTML 正文不能为空")
        if comment_permission not in self.ARTICLE_COMMENT_PERMISSIONS:
            raise ValueError("文章评论权限无效")
        if creation_statement is not None and creation_statement not in self.ARTICLE_STATEMENTS:
            raise ValueError("文章创作声明无效")
        content: dict = {
            "title": title,
            "html": html,
            "comment_permission": comment_permission,
            "table_of_contents_enabled": bool(table_of_contents_enabled),
        }
        if creation_statement:
            content["creation_statement"] = creation_statement
        topics = self._topics(topic_tokens, 3)
        if topics:
            content["topics"] = topics
        return self._publish("article", content, confirmed=confirmed)

    def publish_question(
        self,
        title: str,
        html: str = "",
        *,
        confirmed: bool = False,
        topic_tokens: Sequence[str] | None = None,
    ) -> dict:
        if not title:
            raise ValueError("问题标题不能为空")
        content: dict = {"title": title, "html": html}
        topics = self._topics(topic_tokens, 5)
        if topics:
            content["topics"] = topics
        return self._publish("question", content, confirmed=confirmed)

    def publish_pin(
        self,
        html: str,
        *,
        confirmed: bool = False,
        title: str | None = None,
        image_urls: Sequence[str] | None = None,
        linkcard: dict | None = None,
        ring_id: str | None = None,
        comment_permission: str = "all",
        ai_creation: bool = False,
    ) -> dict:
        if not html:
            raise ValueError("想法 HTML 正文不能为空")
        if comment_permission not in self.PIN_COMMENT_PERMISSIONS:
            raise ValueError("想法评论权限无效")
        if image_urls and linkcard:
            raise ValueError("单条想法不能同时包含独立图片和链接卡片")
        content: dict = {"html": html, "comment_permission": comment_permission}
        if title:
            content["title"] = title
        if image_urls:
            if any(not url for url in image_urls):
                raise ValueError("图片 URL 不能为空")
            content["images"] = [{"url": url} for url in image_urls]
        if linkcard:
            if not linkcard.get("url"):
                raise ValueError("linkcard.url 不能为空")
            content["linkcard"] = {
                "data_content_type": linkcard.get("data_content_type", "common_url"),
                "data_content_id": linkcard.get("data_content_id", "0"),
                "url": linkcard["url"],
                "data_draft_title": linkcard.get("data_draft_title", ""),
                "data_draft_cover": linkcard.get("data_draft_cover", ""),
                "is_from_forward": linkcard.get("is_from_forward", False),
            }
        if ring_id is not None:
            if not ring_id.isdigit():
                raise ValueError("ring_id 必须为数字字符串")
            content["ring"] = {"ring_id": ring_id, "ring_name": ""}
        if ai_creation:
            content["creation_statement"] = "ai_creation"
        return self._publish("pin", content, confirmed=confirmed)

    def publish_answer(self, *args, **kwargs) -> dict:
        raise UnsupportedCapabilityError(
            "官方 Publish OpenAPI 目前只文档化 article、question、pin；未文档化 answer 发布"
        )
