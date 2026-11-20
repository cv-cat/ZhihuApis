"""Contract tests for Zhihu direct-message endpoints (inbox / thread / send)."""

from __future__ import annotations

import unittest

from apis.errors import ZhihuAPIError
from apis.zhihu_web_apis import ZhihuWebAPI


class _FakeSession:
    def __init__(self):
        self.headers: dict[str, str] = {}
        self.cookies = _FakeCookies({"_xsrf": "token123"})
        self.requests: list[tuple[str, str, dict]] = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return _FakeResponse()


def _bind(session, payload):
    """Freeze a payload onto the fake session and still record requests."""
    def _request(method, url, **kwargs):
        session.requests.append((method, url, kwargs))
        return _FakeResponse(payload)
    session.request = _request


class _FakeCookies(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _FakeResponse:
    status_code = 200

    def __init__(self, payload=None):
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


def _api() -> tuple[ZhihuWebAPI, _FakeSession]:
    session = _FakeSession()
    return ZhihuWebAPI(session), session


class InboxTests(unittest.TestCase):
    def test_list_inbox_requests_inbox_with_limit(self):
        api, session = _api()
        _bind(session, {"data": []})
        payload = api.list_inbox(limit=5)
        self.assertEqual(payload, {"data": []})
        method, url, kwargs = session.requests[-1]
        self.assertEqual(method, "GET")
        self.assertIn("/api/v4/inbox?limit=5", url)

    def test_list_inbox_rejects_bad_limit(self):
        api, _ = _api()
        with self.assertRaises(ValueError):
            api.list_inbox(limit=0)
        with self.assertRaises(ValueError):
            api.list_inbox(limit=51)

    def test_list_inbox_requires_data_list(self):
        api, session = _api()
        _bind(session, {"data": {}})
        with self.assertRaises(ZhihuAPIError):
            api.list_inbox()


class ThreadTests(unittest.TestCase):
    def test_list_messages_targets_api_host(self):
        api, session = _api()
        _bind(session, {"data": []})
        api.list_messages("12345", limit=3)
        method, url, kwargs = session.requests[-1]
        self.assertEqual(method, "GET")
        self.assertTrue(url.startswith("https://api.zhihu.com/messages?"))
        self.assertIn("sender_id=12345", url)

    def test_list_messages_rejects_non_numeric_sender(self):
        api, _ = _api()
        with self.assertRaises(ValueError):
            api.list_messages("abc")

    def test_list_messages_accepts_negative_hidden_id(self):
        api, session = _api()
        _bind(session, {"data": []})
        api.list_messages("-10037")
        self.assertIn("sender_id=-10037", session.requests[-1][1])


class SendChatTests(unittest.TestCase):
    def test_send_posts_chat_with_xsrf_and_text_body(self):
        api, session = _api()
        _bind(session, {"info": {"id": "42", "text": "hi"}, "receiver": {}, "sender": {}})
        result = api.send_chat_message("12345", "你好")
        self.assertEqual(result["info"]["id"], "42")
        method, url, kwargs = session.requests[-1]
        self.assertEqual((method, url), ("POST", "https://www.zhihu.com/api/v4/chat"))
        self.assertEqual(kwargs["json"], {"content_type": "text", "receiver_id": "12345", "text": "你好"})
        self.assertEqual(kwargs["headers"]["x-xsrftoken"], "token123")

    def test_send_requires_xsrf_cookie(self):
        api, session = _api()
        session.cookies.clear()
        with self.assertRaises(ZhihuAPIError):
            api.send_chat_message("12345", "你好")

    def test_send_rejects_empty_text_and_bad_receiver(self):
        api, _ = _api()
        with self.assertRaises(ValueError):
            api.send_chat_message("12345", "   ")
        with self.assertRaises(ValueError):
            api.send_chat_message("not-an-id", "你好")

    def test_send_rejects_oversized_text(self):
        api, _ = _api()
        with self.assertRaises(ValueError):
            api.send_chat_message("12345", "x" * 2001)

    def test_send_requires_info_envelope(self):
        api, session = _api()
        _bind(session, {"unexpected": True})
        with self.assertRaises(ZhihuAPIError):
            api.send_chat_message("12345", "你好")


if __name__ == "__main__":
    unittest.main()
