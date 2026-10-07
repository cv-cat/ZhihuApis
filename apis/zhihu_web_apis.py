"""本人浏览器会话中的知乎网页只读接口；不导出 Cookie。"""

from __future__ import annotations

import re
from urllib.parse import urlencode, urlparse

from apis.errors import ZhihuAPIError
from apis.zhihu_browser_auth import ZhihuBrowserAuth


_READ_ONLY_GET = """async (path) => {
    const response = await fetch(path, {
        method: 'GET', credentials: 'include', cache: 'no-store'
    });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    return {status: response.status, data};
}"""


_JSON_WRITE = """async ({path, method, body}) => {
    const options = {method, credentials: 'include', cache: 'no-store'};
    if (body !== null) {
        options.headers = {'content-type': 'application/json'};
        options.body = JSON.stringify(body);
    }
    const response = await fetch(path, options);
    const raw = await response.text();
    let data = null;
    try { data = JSON.parse(raw); } catch (_) {}
    return {status: response.status, data, empty: raw.length === 0};
}"""


class ZhihuWebDraftSaveError(ZhihuAPIError):
    """创建已成功，但更新或回读失败；draft_id 可用于定位残留草稿。"""

    def __init__(self, message: str, *, draft_id: str) -> None:
        super().__init__(message)
        self.draft_id = draft_id


class ZhihuWebAPI:
    """借助已登录的 Playwright 页面访问实测的知乎网页接口。"""

    ARTICLE_EDITOR_URL = "https://zhuanlan.zhihu.com/write"
    DRAFT_URLS = {
        "answer": "https://www.zhihu.com/draft?type=answer",
        "article": "https://www.zhihu.com/draft?type=article",
    }

    def __init__(self, browser_auth: ZhihuBrowserAuth) -> None:
        if not isinstance(browser_auth, ZhihuBrowserAuth):
            raise TypeError("browser_auth 必须是 ZhihuBrowserAuth")
        self._auth = browser_auth

    def _www_page(self):
        page = self._auth._page
        if page is None or urlparse(getattr(page, "url", "")).netloc != "www.zhihu.com":
            raise RuntimeError("请先调用 browser_auth.open_login() 并完成扫码")
        return page

    @staticmethod
    def _get(page, path: str) -> dict:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("只允许站内相对路径")
        result = page.evaluate(_READ_ONLY_GET, path)
        if not isinstance(result, dict) or not isinstance(result.get("status"), int):
            raise ZhihuAPIError("知乎网页响应格式异常")
        status = result["status"]
        payload = result.get("data")
        if status != 200:
            raise ZhihuAPIError("知乎网页读取失败", http_status=status)
        if not isinstance(payload, dict) or "error" in payload:
            raise ZhihuAPIError("知乎网页响应格式异常", http_status=status)
        return payload

    @staticmethod
    def _write(page, *, path: str, method: str, body: dict | None) -> dict | None:
        if not path.startswith("/") or path.startswith("//") or method not in {"POST", "PATCH", "DELETE"}:
            raise ValueError("写入请求参数无效")
        result = page.evaluate(_JSON_WRITE, {"path": path, "method": method, "body": body})
        if not isinstance(result, dict) or not isinstance(result.get("status"), int):
            raise ZhihuAPIError("知乎网页写入响应格式异常")
        status = result["status"]
        payload = result.get("data")
        if status != 200:
            raise ZhihuAPIError("知乎网页写入失败", http_status=status)
        if payload is None and result.get("empty") is False:
            raise ZhihuAPIError("知乎网页写入返回非 JSON 响应", http_status=status)
        if isinstance(payload, dict) and "error" in payload:
            raise ZhihuAPIError("知乎网页写入业务失败", http_status=status)
        return payload

    def _zhuanlan_page(self):
        self._www_page()
        context = self._auth._context
        if context is None:
            raise RuntimeError("浏览器会话已关闭")
        page = context.new_page()
        try:
            page.goto(self.ARTICLE_EDITOR_URL, wait_until="domcontentloaded")
        except Exception:
            page.close()
            raise
        return page

    def search(self, query: str, *, offset: int = 0, limit: int = 20) -> dict:
        """网页综合搜索，返回原始 data 与 paging；当前实测 offset 分页。"""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query 不能为空")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset 必须是非负整数")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise ValueError("limit 范围为 1-20")
        path = "/api/v4/search_v3?" + urlencode(
            {"t": "general", "q": query.strip(), "offset": offset, "limit": limit, "search_source": "Normal"}
        )
        payload = self._get(self._www_page(), path)
        if not isinstance(payload.get("data"), list) or not isinstance(payload.get("paging"), dict):
            raise ZhihuAPIError("知乎搜索响应缺少 data 或 paging", http_status=200)
        return payload

    def get_answer(self, answer_id: int | str) -> dict:
        """读取公开回答网页接口当前返回的 content 字段。"""
        identifier = self._numeric_id(answer_id)
        path = f"/api/v4/answers/{identifier}?include=content%2Cexcerpt%2Cquestion%2Cauthor"
        payload = self._get(self._www_page(), path)
        if not isinstance(payload.get("content"), str):
            raise ZhihuAPIError("回答响应缺少 content", http_status=200)
        return payload

    def get_article(self, article_id: int | str) -> dict:
        """在同一浏览器配置的新标签读取专栏文章网页接口。"""
        self._www_page()
        identifier = self._numeric_id(article_id)
        context = self._auth._context
        if context is None:
            raise RuntimeError("浏览器会话已关闭")
        page = context.new_page()
        try:
            page.goto(f"https://zhuanlan.zhihu.com/p/{identifier}", wait_until="domcontentloaded")
            payload = self._get(page, f"/api/articles/{identifier}")
        finally:
            page.close()
        if not isinstance(payload.get("content"), str):
            raise ZhihuAPIError("文章响应缺少 content", http_status=200)
        return payload

    def get_item(self, content_url: str) -> dict:
        """支持实测的网页回答/文章 URL，以及搜索结果中的 api.zhihu.com URL。"""
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
                return self.get_answer(match.group(2)) if match.group(1) == "answers" else self.get_article(match.group(2))
        raise ValueError("当前只支持回答或文章内容 URL")

    def draft_counts(self) -> dict[str, dict]:
        """只读获取回答和文章草稿计数，不打开或修改草稿。"""
        page = self._www_page()
        result = {}
        for kind, path in (
            ("answer", "/api/v4/answer-drafts/count"),
            ("article", "/api/v4/articles/my_drafts/count"),
        ):
            payload = self._get(page, path)
            if isinstance(payload.get("count"), bool) or not isinstance(payload.get("count"), int):
                raise ZhihuAPIError("草稿计数响应格式异常", http_status=200)
            result[kind] = payload
        return result

    def save_web_draft(self, title: str, html: str) -> dict[str, str]:
        """创建文章草稿、保存 HTML，并回读确认；不会公开发布。"""
        if not isinstance(title, str) or not title.strip():
            raise ValueError("草稿标题不能为空")
        if not isinstance(html, str) or not html.strip():
            raise ValueError("草稿正文不能为空")
        title = title.strip()
        page = self._zhuanlan_page()
        try:
            created = self._write(
                page,
                path="/api/articles/drafts",
                method="POST",
                body={"title": title, "delta_time": 0, "can_reward": False},
            )
            if not isinstance(created, dict) or created.get("state") != "draft" or created.get("type") != "article_draft":
                raise ZhihuAPIError("知乎未确认创建文章草稿", http_status=200)
            identifier = self._numeric_id(created.get("id"))
            try:
                self._write(
                    page,
                    path=f"/api/articles/{identifier}/draft",
                    method="PATCH",
                    body={"content": html, "table_of_contents": False, "delta_time": 0, "can_reward": False},
                )
                saved = self._get(page, f"/api/articles/{identifier}/draft")
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
            return {"id": identifier, "state": "draft", "edit_url": f"https://zhuanlan.zhihu.com/p/{identifier}/edit"}
        finally:
            page.close()

    def get_web_draft(self, draft_id: int | str) -> dict:
        """只读回读本人文章草稿。"""
        identifier = self._numeric_id(draft_id)
        page = self._zhuanlan_page()
        try:
            payload = self._get(page, f"/api/articles/{identifier}/draft")
        finally:
            page.close()
        if payload.get("state") != "draft" or payload.get("type") != "article_draft":
            raise ZhihuAPIError("知乎未返回文章草稿", http_status=200)
        return payload

    def delete_web_draft(self, draft_id: int | str) -> None:
        """删除指定文章草稿；仅接受显式传入的数字 ID。"""
        identifier = self._numeric_id(draft_id)
        self._write(
            self._www_page(), path=f"/api/v4/articles/{identifier}/draft", method="DELETE", body=None
        )

    @staticmethod
    def _numeric_id(value: int | str) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError("内容 ID 必须是数字")
        identifier = str(value)
        if not identifier.isascii() or not identifier.isdigit():
            raise ValueError("内容 ID 必须是数字")
        return identifier
