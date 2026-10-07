"""纯 HTTP 登录流程的离线契约测试，不访问知乎真实账号。"""

import unittest

from apis.errors import UnsupportedCapabilityError
from apis.zhihu_http_auth import (
    CAPTCHA_URL,
    ME_URL,
    QR_STATUS_URL,
    QR_TOKEN_URL,
    SMS_CODE_URL,
    HumanVerificationRequired,
    ZhihuHTTPAuth,
    classify_login_probe,
)


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self.payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload


class CookieJar(dict):
    def set(self, name, value, **kwargs):
        self[name] = value


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}
        self.cookies = CookieJar()

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError(f"unexpected request: {method} {url}")
        item = self.responses.pop(0)
        return item(method, url, kwargs) if callable(item) else item

    def close(self):
        pass


class HttpAuthTests(unittest.TestCase):
    def test_login_state_requires_positive_account_evidence(self):
        self.assertIsNone(classify_login_probe(401, None).authenticated)
        self.assertFalse(classify_login_probe(200, "guest").authenticated)
        self.assertTrue(classify_login_probe(200, "people").authenticated)
        self.assertIsNone(classify_login_probe(200, None).authenticated)

    def test_cookie_header_is_imported_without_file_state(self):
        session = FakeSession([])
        ZhihuHTTPAuth(session=session, cookie_header="z_c0=token=part; _xsrf=csrf")
        self.assertEqual(session.cookies["z_c0"], "token=part")
        self.assertEqual(session.cookies["_xsrf"], "csrf")
        self.assertEqual(session.headers["Accept"], "application/json, text/plain, */*")

    def test_malformed_cookie_header_is_rejected(self):
        with self.assertRaises(ValueError):
            ZhihuHTTPAuth(session=FakeSession([]), cookie_header="missing-equals")
        with self.assertRaises(ValueError):
            ZhihuHTTPAuth(session=FakeSession([]), cookie_header="bad name=value")

    def test_qr_flow_posts_udid_then_token_and_returns_link(self):
        session = FakeSession([
            FakeResponse({}, 200, text="duid-value"),
            FakeResponse({"token": "token-1", "link": "https://www.zhihu.com/account/scan/login/token-1", "expires_at": 99}),
        ])
        auth = ZhihuHTTPAuth(session=session)
        challenge = auth.begin_qr_login()
        self.assertEqual(challenge.qr_text, challenge.link)
        self.assertEqual(session.calls[0][0:2], ("POST", "https://www.zhihu.com/udid"))
        self.assertEqual(session.calls[1][1], QR_TOKEN_URL)
        self.assertEqual(session.headers["x-du-bid"], "duid-value")

    def test_qr_poll_surfaces_human_verification(self):
        payload = {"error": {"code": 40352, "message": "需要安全验证"}}
        session = FakeSession([FakeResponse({}, 200, text="duid-value"), FakeResponse(payload, 403)])
        auth = ZhihuHTTPAuth(session=session)
        result = auth.poll_qr_login("token-1")
        self.assertTrue(result.verification_required)
        self.assertEqual(result.http_status, 403)
        self.assertEqual(session.calls[1][1], QR_STATUS_URL.format(token="token-1"))
        retry_session = FakeSession([FakeResponse({}, 200, text="duid-value"), FakeResponse(payload, 403)])
        with self.assertRaises(HumanVerificationRequired):
            ZhihuHTTPAuth(session=retry_session).wait_for_qr_login("token-1", timeout_seconds=0.01, poll_interval=0.01)

    def test_qr_poll_confirms_account_after_access_token(self):
        session = FakeSession([
            FakeResponse({}, 200, text="duid-value"),
            FakeResponse({"accessToken": "access", "status": 2}),
            FakeResponse({"user_type": "people"}, 200),
        ])
        auth = ZhihuHTTPAuth(session=session)
        result = auth.poll_qr_login("token-1")
        self.assertTrue(result.authenticated)
        self.assertEqual(result.status, 2)
        self.assertEqual(session.calls[1][1], QR_STATUS_URL.format(token="token-1"))
        self.assertEqual(session.calls[2][1], ME_URL)

    def test_captcha_get_and_validate_use_observed_http_contract(self):
        session = FakeSession([FakeResponse({"captcha_type": "slider"}), FakeResponse({"success": True})])
        auth = ZhihuHTTPAuth(session=session)
        self.assertEqual(auth.get_captcha()["captcha_type"], "slider")
        self.assertTrue(auth.validate_captcha("ticket-1")["success"])
        self.assertEqual(session.calls[0][1], CAPTCHA_URL)
        self.assertEqual(session.calls[0][2]["params"]["scene"], "digits_login")
        self.assertEqual(session.calls[1][2]["data"], {"ticket": "ticket-1", "scene": "digits_login"})

    def test_sms_requires_current_dynamic_encrypted_body(self):
        auth = ZhihuHTTPAuth(session=FakeSession([]))
        with self.assertRaises(UnsupportedCapabilityError):
            auth.request_sms_code("13800000000")

    def test_sms_sends_supplied_encrypted_body_and_captcha_ticket(self):
        session = FakeSession([FakeResponse({"success": True})])
        auth = ZhihuHTTPAuth(session=session)
        result = auth.request_sms_code("13800000000", encrypted_body="zsEncrypt=payload", captcha_ticket="ticket")
        self.assertTrue(result["success"])
        method, url, kwargs = session.calls[0]
        self.assertEqual((method, url), ("POST", SMS_CODE_URL))
        self.assertEqual(kwargs["data"], "zsEncrypt=payload")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/x-www-form-urlencoded")

    def test_login_state_accepts_non_json_unauthorized_response(self):
        session = FakeSession([FakeResponse(ValueError("html"), 401, text="<html>login</html>")])
        state = ZhihuHTTPAuth(session=session).login_state()
        self.assertIsNone(state.authenticated)
        self.assertEqual(state.reason, "unauthorized_or_rejected")

    def test_password_login_does_not_accept_plain_body(self):
        auth = ZhihuHTTPAuth(session=FakeSession([]))
        with self.assertRaises(UnsupportedCapabilityError):
            auth.login_with_password("user", "secret")


if __name__ == "__main__":
    unittest.main()
