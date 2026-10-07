"""知乎网页接口纯 HTTP 请求契约测试。"""

import unittest
from urllib.parse import parse_qs, urlparse

from apis.errors import ZhihuAPIError
from apis.zhihu_http_auth import ZhihuHTTPAuth
from apis.zhihu_web_apis import ZHUANLAN_URL, ZhihuWebAPI, ZhihuWebDraftSaveError


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self.payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self.payload


class CookieJar(dict):
    def get(self, name, default=None):
        return super().get(name, default)


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}
        self.cookies = CookieJar({"_xsrf": "csrf"})

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError(f"unexpected request: {method} {url}")
        response = self.responses.pop(0)
        return response(method, url, kwargs) if callable(response) else response


def web_client(responses):
    session = FakeSession(responses)
    auth = ZhihuHTTPAuth(session=session)
    return ZhihuWebAPI(auth), session


class WebApiTests(unittest.TestCase):
    def test_search_uses_http_get_and_offset(self):
        payload = {"data": [{"type": "search_result"}], "paging": {"is_end": False}}
        client, session = web_client([FakeResponse(payload)])
        self.assertEqual(client.search(" 咖啡 ", offset=2, limit=5), payload)
        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(urlparse(url).path, "/api/v4/search_v3")
        self.assertEqual(parse_qs(urlparse(url).query)["q"], ["咖啡"])
        self.assertEqual(kwargs["headers"]["X-Xsrftoken"], "csrf")
        with self.assertRaises(ValueError):
            client.search("咖啡", limit=21)

    def test_answer_item_requires_content(self):
        client, session = web_client([FakeResponse({"type": "answer", "content": "<p>text</p>"})])
        item = client.get_item("https://www.zhihu.com/question/8/answer/42")
        self.assertEqual(item["content"], "<p>text</p>")
        self.assertEqual(urlparse(session.calls[0][1]).path, "/api/v4/answers/42")

        client, _ = web_client([FakeResponse({"type": "answer"})])
        with self.assertRaises(ZhihuAPIError):
            client.get_item("https://api.zhihu.com/answers/42")

    def test_article_item_uses_zhuanlan_http_endpoint(self):
        client, session = web_client([FakeResponse({"type": "article", "content": "<p>article</p>"})])
        item = client.get_item("https://api.zhihu.com/articles/77")
        self.assertEqual(item["content"], "<p>article</p>")
        self.assertEqual(session.calls[0][1], f"{ZHUANLAN_URL}/api/articles/77")

    def test_draft_counts_use_observed_paths(self):
        client, session = web_client([
            FakeResponse({"count": 1, "scheduled_count": 0}),
            FakeResponse({"count": 2, "scheduled_count": 0}),
        ])
        self.assertEqual(client.draft_counts()["article"]["count"], 2)
        self.assertEqual([urlparse(call[1]).path for call in session.calls], [
            "/api/v4/answer-drafts/count", "/api/v4/articles/my_drafts/count"
        ])
        self.assertEqual(ZhihuWebAPI.DRAFT_URLS["answer"], "https://www.zhihu.com/draft?type=answer")

    def test_rejects_unverified_item_routes_and_http_errors(self):
        client, session = web_client([])
        for url in (
            "http://www.zhihu.com/question/1/answer/2",
            "https://evil.zhihu.com/question/1/answer/2",
            "https://www.zhihu.com/question/1",
        ):
            with self.assertRaises(ValueError):
                client.get_item(url)
        self.assertEqual(session.calls, [])

        client, _ = web_client([FakeResponse({"error": {"code": 100}}, 401)])
        with self.assertRaises(ZhihuAPIError) as caught:
            client.get_answer(42)
        self.assertEqual(caught.exception.http_status, 401)

    def test_save_article_draft_create_patch_and_read_back(self):
        title, html = "temporary title", "<p>temporary body</p>"
        client, session = web_client([
            FakeResponse({"id": "77", "state": "draft", "type": "article_draft"}),
            FakeResponse(None, 200, text=""),
            FakeResponse({"id": "77", "state": "draft", "type": "article_draft", "title": title, "content": html}),
        ])
        result = client.save_web_draft(title, html)
        self.assertEqual(result["id"], "77")
        self.assertEqual(result["state"], "draft")
        self.assertEqual([call[0] for call in session.calls], ["POST", "PATCH", "GET"])
        self.assertEqual(session.calls[0][1], f"{ZHUANLAN_URL}/api/articles/drafts")
        self.assertEqual(session.calls[0][2]["json"], {"title": title, "delta_time": 0, "can_reward": False})
        self.assertEqual(session.calls[1][2]["json"], {
            "content": html, "table_of_contents": False, "delta_time": 0, "can_reward": False
        })

    def test_partial_save_exposes_draft_id_for_cleanup(self):
        client, session = web_client([
            FakeResponse({"id": "77", "state": "draft", "type": "article_draft"}),
            FakeResponse({"error": {"code": 403}}, 403),
        ])
        with self.assertRaises(ZhihuWebDraftSaveError) as caught:
            client.save_web_draft("title", "<p>body</p>")
        self.assertEqual(caught.exception.draft_id, "77")
        self.assertEqual([call[0] for call in session.calls], ["POST", "PATCH"])

    def test_read_and_delete_explicit_article_draft(self):
        draft = {"id": "77", "state": "draft", "type": "article_draft", "content": "<p>body</p>"}
        client, session = web_client([FakeResponse(draft), FakeResponse(None, 204, text="")])
        self.assertEqual(client.get_web_draft(77), draft)
        client.delete_web_draft(77)
        self.assertEqual(session.calls[-1][0:2], ("DELETE", "https://www.zhihu.com/api/v4/articles/77/draft"))
        with self.assertRaises(ValueError):
            client.delete_web_draft("77/../../1")


if __name__ == "__main__":
    unittest.main()
