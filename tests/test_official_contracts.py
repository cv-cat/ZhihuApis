"""只验证已公开的请求契约，不触及真实账号或发布。"""

import base64
import hashlib
import hmac
import unittest
from urllib.parse import parse_qs, urlparse

from apis.errors import ConfirmationRequiredError, UnsupportedCapabilityError, ZhihuAPIError
from apis.zhihu_creator_apis import ZhihuCreatorAPI
from apis.zhihu_data_apis import ZhihuDataAPI
from apis.zhihu_media import ZhihuMediaAPI
from apis.zhihu_oauth import ZhihuOAuth


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response

    def close(self):
        pass


class DataContractTests(unittest.TestCase):
    def test_search_uses_bearer_and_documented_query(self):
        session = FakeSession(FakeResponse({"Code": 0, "Message": "success", "Data": {"Items": []}}))
        client = ZhihuDataAPI("data-secret", session=session, timestamp=lambda: 1730000000)
        result = client.search("咖啡", count=5, sort_by="VoteUpCount:desc:(10,)")
        self.assertEqual(result, {"Items": []})
        method, url, kwargs = session.calls[0]
        self.assertEqual((method, url), ("GET", "https://developer.zhihu.com/api/v1/content/zhihu_search"))
        self.assertEqual(kwargs["params"], {"Query": "咖啡", "Count": 5, "SortBy": "VoteUpCount:desc:(10,)"})
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer data-secret")
        self.assertEqual(kwargs["headers"]["X-Request-Timestamp"], "1730000000")
        self.assertNotIn("X-App-Key", kwargs["headers"])

    def test_item_is_own_content_api_and_oauth_token_only_on_user_listing(self):
        session = FakeSession(FakeResponse({"Code": 0, "Data": {"Body": "<p>x</p>"}}))
        client = ZhihuDataAPI("data-secret", session=session)
        client.get_item("https://zhuanlan.zhihu.com/p/123")
        self.assertEqual(session.calls[0][1], "https://developer.zhihu.com/api/v1/user/content_detail")
        self.assertEqual(session.calls[0][2]["params"], {"ContentUrl": "https://zhuanlan.zhihu.com/p/123"})
        self.assertNotIn("X-OAuth-Token", session.calls[0][2]["headers"])
        client.list_user_contents(content_type="article", oauth_token="user-oauth")
        self.assertEqual(session.calls[1][2]["headers"]["X-OAuth-Token"], "user-oauth")

    def test_business_error_is_not_success(self):
        session = FakeSession(FakeResponse({"Code": 20001, "Message": "auth failed", "Data": {}}, 200))
        client = ZhihuDataAPI("data-secret", session=session)
        with self.assertRaises(ZhihuAPIError) as ctx:
            client.search("test")
        self.assertEqual(ctx.exception.code, 20001)

    def test_user_contents_accepts_documented_next_offset_string(self):
        session = FakeSession(FakeResponse({"Code": 0, "Data": {"Items": [], "Paging": {"NextOffset": "20"}}}))
        client = ZhihuDataAPI("data-secret", session=session)
        client.list_user_contents(offset="20", oauth_token="user-oauth")
        self.assertEqual(session.calls[0][2]["params"]["Offset"], "20")
        self.assertEqual(session.calls[0][2]["headers"]["X-OAuth-Token"], "user-oauth")
        with self.assertRaises(ValueError):
            client.list_user_contents(offset="20x")
        self.assertEqual(len(session.calls), 1)


class OAuthContractTests(unittest.TestCase):
    def test_authorization_code_flow_does_not_use_data_secret(self):
        session = FakeSession(FakeResponse({"access_token": "user-token", "token_type": "Bearer", "expires_in": 3600}))
        oauth = ZhihuOAuth("app-id", "oauth-app-key", "https://example.test/callback", session=session)
        parsed = urlparse(oauth.authorization_url())
        self.assertEqual(parsed.path, "/authorize")
        self.assertEqual(parse_qs(parsed.query), {
            "redirect_uri": ["https://example.test/callback"],
            "app_id": ["app-id"],
            "response_type": ["code"],
        })
        self.assertEqual(oauth.exchange_code("auth-code")["access_token"], "user-token")
        method, url, kwargs = session.calls[0]
        self.assertEqual((method, url), ("POST", "https://openapi.zhihu.com/access_token"))
        self.assertEqual(kwargs["data"]["app_key"], "oauth-app-key")
        self.assertEqual(kwargs["data"]["grant_type"], "authorization_code")
        self.assertNotIn("Authorization", kwargs["headers"])

    def test_callback_code_is_extracted_only_from_registered_redirect(self):
        oauth = ZhihuOAuth("app-id", "oauth-app-key", "https://example.test/callback?tenant=1")
        callback = "https://example.test/callback?tenant=1&authorization_code=abc%2B123"
        self.assertEqual(oauth.authorization_code_from_callback(callback), "abc+123")
        for invalid in (
            "https://other.test/callback?tenant=1&authorization_code=abc",
            "https://example.test/callback?authorization_code=abc",
            "https://example.test/callback?tenant=1&authorization_code=a&authorization_code=b",
        ):
            with self.assertRaises(ValueError):
                oauth.authorization_code_from_callback(invalid)
        with self.assertRaises(ZhihuAPIError):
            oauth.authorization_code_from_callback("https://example.test/callback?tenant=1&error=access_denied")

    def test_exchange_rejects_non_string_access_token(self):
        oauth = ZhihuOAuth(
            "app-id", "oauth-app-key", "https://example.test/callback",
            session=FakeSession(FakeResponse({"access_token": 123})),
        )
        with self.assertRaises(ZhihuAPIError):
            oauth.exchange_code("auth-code")


class PublishContractTests(unittest.TestCase):
    def make_client(self, response=None):
        session = FakeSession(response or FakeResponse({
            "status": 0, "msg": "success", "data": {"content_token": "123", "url": "https://zhuanlan.zhihu.com/p/123"}
        }))
        client = ZhihuCreatorAPI(
            "url-token", "publish-secret", session=session,
            timestamp=lambda: 1730000000, log_id=lambda: "fixed-log",
        )
        return client, session

    def test_publish_article_signs_exact_official_header_contract(self):
        client, session = self.make_client()
        client.publish_article("题目", "<p>内容</p>", confirmed=True, topic_tokens=["19555547"])
        method, url, kwargs = session.calls[0]
        self.assertEqual((method, url), ("POST", "https://openapi.zhihu.com/openapi/publish"))
        self.assertEqual(kwargs["json"], {
            "type": "article", "confirmed": True,
            "confirm_note": "confirmed by user after local preview",
            "content": {
                "title": "题目", "html": "<p>内容</p>",
                "comment_permission": "all", "table_of_contents_enabled": False,
                "topics": [{"topic_id": "", "topic_token": "19555547", "topic_name": ""}],
            },
        })
        headers = kwargs["headers"]
        sign_string = "app_key:url-token|ts:1730000000|logid:fixed-log|extra_info:"
        expected_sign = base64.b64encode(hmac.new(b"publish-secret", sign_string.encode(), hashlib.sha256).digest()).decode()
        self.assertEqual(headers["X-Sign"], expected_sign)
        self.assertEqual(headers["X-Extra-Info"], "")
        self.assertNotIn("Authorization", headers)

    def test_publish_requires_explicit_confirmation(self):
        client, session = self.make_client()
        with self.assertRaises(ConfirmationRequiredError):
            client.publish_article("题目", "<p>内容</p>")
        self.assertEqual(session.calls, [])

    def test_topic_limit_applies_after_ordered_deduplication(self):
        client, session = self.make_client()
        client.publish_article(
            "题目", "<p>内容</p>", confirmed=True,
            topic_tokens=["19555547", "2", "19555547", "3"],
        )
        self.assertEqual(
            session.calls[0][2]["json"]["content"]["topics"],
            [
                {"topic_id": "", "topic_token": value, "topic_name": ""}
                for value in ("19555547", "2", "3")
            ],
        )
        with self.assertRaisesRegex(ValueError, "最多支持 3 个话题"):
            client.publish_article(
                "题目", "<p>内容</p>", confirmed=True,
                topic_tokens=["1", "2", "2", "3", "4"],
            )
        self.assertEqual(len(session.calls), 1)

    def test_question_and_pin_payloads(self):
        client, session = self.make_client()
        client.publish_question("为什么？", confirmed=True, topic_tokens=["19555547"])
        self.assertEqual(session.calls[-1][2]["json"]["content"], {
            "title": "为什么？", "html": "",
            "topics": [{"topic_id": "", "topic_token": "19555547", "topic_name": ""}],
        })
        client.publish_pin("<p>想法</p>", confirmed=True, image_urls=["https://pic.zhimg.com/x.jpg"], ai_creation=True)
        self.assertEqual(session.calls[-1][2]["json"]["content"], {
            "html": "<p>想法</p>", "comment_permission": "all",
            "images": [{"url": "https://pic.zhimg.com/x.jpg"}],
            "creation_statement": "ai_creation",
        })

    def test_business_failure_and_unsupported_answer(self):
        client, session = self.make_client(FakeResponse({"status": 1, "msg": "rate limit exceeded", "data": None}, 200))
        with self.assertRaises(ZhihuAPIError) as ctx:
            client.publish_article("题目", "<p>内容</p>", confirmed=True)
        self.assertEqual(ctx.exception.code, 1)
        count = len(session.calls)
        with self.assertRaises(UnsupportedCapabilityError):
            client.publish_answer("123", "<p>内容</p>", confirmed=True)
        self.assertEqual(len(session.calls), count)


class MediaAdapterTests(unittest.TestCase):
    def test_delegates_to_official_uploader(self):
        calls = []

        class Uploader:
            def __init__(self, **kwargs):
                calls.append(("init", kwargs))

            def upload_image(self, **kwargs):
                calls.append(("image", kwargs))
                return {"media_key": "v2-test"}

        media = ZhihuMediaAPI("url-token", "publish-secret", uploader_factory=Uploader)
        self.assertEqual(media.upload_image(scene_name="article", file_path="C:/tmp/a.png"), {"media_key": "v2-test"})
        self.assertEqual(calls[0], ("init", {"app_key": "url-token", "app_secret": "publish-secret"}))
        self.assertEqual(calls[1][1]["scene_name"], "article")
        with self.assertRaises(ValueError):
            media.upload_image(scene_name="article", file_path="C:/tmp/a.png", url="https://example.test/a.png")


if __name__ == "__main__":
    unittest.main()
