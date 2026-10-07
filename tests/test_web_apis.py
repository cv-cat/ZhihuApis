"""已登录网页只读接口的离线请求契约测试。"""

import unittest
from urllib.parse import parse_qs, urlparse

from apis.errors import ZhihuAPIError
from apis.zhihu_browser_auth import ZhihuBrowserAuth
from apis.zhihu_web_apis import ZhihuWebAPI, ZhihuWebDraftSaveError


class FakePage:
    def __init__(self, url, responses):
        self.url = url
        self.responses = responses
        self.paths = []
        self.scripts = []
        self.arguments = []
        self.navigations = []
        self.closed = False

    def evaluate(self, script, argument):
        self.scripts.append(script)
        self.arguments.append(argument)
        path = argument["path"] if isinstance(argument, dict) else argument
        method = argument["method"] if isinstance(argument, dict) else "GET"
        self.paths.append(path)
        return self.responses.get((method, path), self.responses.get(path, {"status": 404, "data": {"error": {}}}))

    def goto(self, url, **kwargs):
        self.navigations.append((url, kwargs))
        self.url = url

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, article_page):
        self.article_page = article_page
        self.pages_created = 0

    def new_page(self):
        self.pages_created += 1
        return self.article_page


class FakeResponse:
    status = 200

    @staticmethod
    def json():
        return {"id": "77", "type": "article", "content": "<p>request article</p>"}


class FakeRequestContext:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


class FakeContextWithRequest(FakeContext):
    def __init__(self, article_page):
        super().__init__(article_page)
        self.request = FakeRequestContext()


def web_client(www_responses=None, article_responses=None):
    www = FakePage("https://www.zhihu.com/", www_responses or {})
    article = FakePage("about:blank", article_responses or {})
    context = FakeContext(article)
    auth = object.__new__(ZhihuBrowserAuth)
    auth._page = www
    auth._context = context
    return ZhihuWebAPI(auth), www, article, context


class WebApiTests(unittest.TestCase):
    def test_search_uses_logged_in_browser_get_and_offset(self):
        payload = {"data": [{"type": "search_result"}], "paging": {"is_end": False, "next": "https://api.zhihu.com/search_v3"}}
        expected_path = "/api/v4/search_v3?t=general&q=%E5%92%96%E5%95%A1&offset=2&limit=5&search_source=Normal"
        client, www, _, _ = web_client({expected_path: {"status": 200, "data": payload}})

        self.assertEqual(client.search(" 咖啡 ", offset=2, limit=5), payload)
        self.assertEqual(www.paths, [expected_path])
        self.assertEqual(parse_qs(urlparse(www.paths[0]).query)["q"], ["咖啡"])
        self.assertIn("method: 'GET'", www.scripts[0])
        self.assertNotIn("document.cookie", www.scripts[0])
        with self.assertRaises(ValueError):
            client.search("咖啡", limit=21)

    def test_answer_item_requires_content(self):
        path = "/api/v4/answers/42?include=content%2Cexcerpt%2Cquestion%2Cauthor"
        client, www, _, _ = web_client({path: {"status": 200, "data": {"type": "answer", "content": "<p>text</p>"}}})
        item = client.get_item("https://www.zhihu.com/question/8/answer/42")
        self.assertEqual(item["content"], "<p>text</p>")
        self.assertEqual(www.paths, [path])

        client, _, _, _ = web_client({path: {"status": 200, "data": {"type": "answer"}}})
        with self.assertRaises(ZhihuAPIError):
            client.get_item("https://api.zhihu.com/answers/42")

    def test_article_item_uses_same_context_and_closes_probe_tab(self):
        client, www, article, context = web_client(article_responses={
            "/api/articles/77": {"status": 200, "data": {"type": "article", "content": "<p>article</p>"}}
        })
        item = client.get_item("https://api.zhihu.com/articles/77")
        self.assertEqual(item["content"], "<p>article</p>")
        self.assertEqual(context.pages_created, 1)
        self.assertEqual(article.navigations, [("https://zhuanlan.zhihu.com/p/77", {"wait_until": "domcontentloaded"})])
        self.assertEqual(article.paths, ["/api/articles/77"])
        self.assertTrue(article.closed)
        self.assertEqual(www.paths, [])

    def test_article_item_prefers_context_request(self):
        www = FakePage("https://www.zhihu.com/", {})
        article = FakePage("about:blank", {})
        context = FakeContextWithRequest(article)
        auth = object.__new__(ZhihuBrowserAuth)
        auth._page = www
        auth._context = context
        client = ZhihuWebAPI(auth)

        item = client.get_item("https://api.zhihu.com/articles/77")

        self.assertEqual(item["content"], "<p>request article</p>")
        self.assertEqual(context.pages_created, 0)
        self.assertEqual(context.request.calls[0][0], "https://zhuanlan.zhihu.com/api/articles/77")

    def test_draft_counts_use_observed_read_only_paths(self):
        client, www, _, _ = web_client({
            "/api/v4/answer-drafts/count": {"status": 200, "data": {"count": 1, "scheduled_count": 0}},
            "/api/v4/articles/my_drafts/count": {"status": 200, "data": {"count": 2, "scheduled_count": 0}},
        })
        self.assertEqual(client.draft_counts()["article"]["count"], 2)
        self.assertEqual(www.paths, ["/api/v4/answer-drafts/count", "/api/v4/articles/my_drafts/count"])
        self.assertEqual(ZhihuWebAPI.DRAFT_URLS["answer"], "https://www.zhihu.com/draft?type=answer")

    def test_rejects_unverified_item_routes_and_http_errors(self):
        client, www, _, _ = web_client()
        for url in (
            "http://www.zhihu.com/question/1/answer/2",
            "https://evil.zhihu.com/question/1/answer/2",
            "https://www.zhihu.com/question/1",
        ):
            with self.assertRaises(ValueError):
                client.get_item(url)
        self.assertEqual(www.paths, [])

        path = "/api/v4/answers/42?include=content%2Cexcerpt%2Cquestion%2Cauthor"
        client, _, _, _ = web_client({path: {"status": 401, "data": {"error": {"code": 100}}}})
        with self.assertRaises(ZhihuAPIError) as caught:
            client.get_answer(42)
        self.assertEqual(caught.exception.http_status, 401)

        client, _, article, _ = web_client(article_responses={
            "/api/articles/77": {"status": 403, "data": {"error": {"code": 403}}}
        })
        with self.assertRaises(ZhihuAPIError):
            client.get_article(77)
        self.assertTrue(article.closed)

        path = "/api/v4/search_v3?t=general&q=test&offset=0&limit=20&search_source=Normal"
        client, _, _, _ = web_client({path: {"status": 200, "data": {"error": {"code": 100}}}})
        with self.assertRaises(ZhihuAPIError):
            client.search("test")

    def test_save_article_draft_create_patch_and_read_back(self):
        title, html = "temporary title", "<p>temporary body</p>"
        client, _, editor, context = web_client(article_responses={
            ("POST", "/api/articles/drafts"): {
                "status": 200, "data": {"id": "77", "state": "draft", "type": "article_draft"}
            },
            ("PATCH", "/api/articles/77/draft"): {"status": 200, "data": None, "empty": True},
            "/api/articles/77/draft": {
                "status": 200,
                "data": {"id": "77", "state": "draft", "type": "article_draft", "title": title, "content": html},
            },
        })
        result = client.save_web_draft(title, html)
        self.assertEqual(result["id"], "77")
        self.assertEqual(result["state"], "draft")
        self.assertEqual(context.pages_created, 1)
        self.assertEqual(editor.navigations[0][0], ZhihuWebAPI.ARTICLE_EDITOR_URL)
        self.assertEqual(editor.paths, ["/api/articles/drafts", "/api/articles/77/draft", "/api/articles/77/draft"])
        self.assertEqual(editor.arguments[0]["body"], {"title": title, "delta_time": 0, "can_reward": False})
        self.assertEqual(editor.arguments[1]["body"], {
            "content": html, "table_of_contents": False, "delta_time": 0, "can_reward": False
        })
        self.assertEqual([arg["method"] for arg in editor.arguments[:2]], ["POST", "PATCH"])
        self.assertTrue(editor.closed)
        self.assertFalse(any("publish" in path for path in editor.paths))

    def test_partial_save_exposes_draft_id_for_cleanup(self):
        client, _, editor, _ = web_client(article_responses={
            ("POST", "/api/articles/drafts"): {
                "status": 200, "data": {"id": "77", "state": "draft", "type": "article_draft"}
            },
            ("PATCH", "/api/articles/77/draft"): {"status": 403, "data": {"error": {"code": 403}}},
        })
        with self.assertRaises(ZhihuWebDraftSaveError) as caught:
            client.save_web_draft("title", "<p>body</p>")
        self.assertEqual(caught.exception.draft_id, "77")
        self.assertTrue(editor.closed)
        self.assertEqual(editor.paths, ["/api/articles/drafts", "/api/articles/77/draft"])

    def test_read_and_delete_explicit_article_draft(self):
        draft = {"id": "77", "state": "draft", "type": "article_draft", "content": "<p>body</p>"}
        client, www, editor, _ = web_client(
            www_responses={("DELETE", "/api/v4/articles/77/draft"): {"status": 200, "data": None, "empty": True}},
            article_responses={"/api/articles/77/draft": {"status": 200, "data": draft}},
        )
        self.assertEqual(client.get_web_draft(77), draft)
        self.assertTrue(editor.closed)
        client.delete_web_draft(77)
        self.assertEqual(www.arguments[-1], {"path": "/api/v4/articles/77/draft", "method": "DELETE", "body": None})
        self.assertNotIn("document.cookie", www.scripts[-1])
        with self.assertRaises(ValueError):
            client.delete_web_draft("77/../../1")

        client, _, _, _ = web_client(www_responses={
            ("DELETE", "/api/v4/articles/77/draft"): {"status": 200, "data": None, "empty": False}
        })
        with self.assertRaises(ZhihuAPIError):
            client.delete_web_draft(77)


if __name__ == "__main__":
    unittest.main()
