"""旧导入路径兼容层。

实际实现位于 :mod:`apis.zhihu_http_auth`，这里只保留名称兼容，不启动
任何浏览器或页面自动化。新代码请直接导入 ``ZhihuHTTPAuth``。
"""

from apis.zhihu_http_auth import (
    BASE_URL,
    HOME_URL,
    ME_URL,
    SIGNIN_URL,
    HumanVerificationRequired,
    LoginState,
    QRLoginChallenge,
    QRLoginState,
    ZhihuHTTPAuth,
    classify_login_probe,
)

# 旧版本公开的类名仍可导入，但实现已经是 requests.Session。
ZhihuBrowserAuth = ZhihuHTTPAuth
BrowserLoginState = LoginState

__all__ = [
    "BASE_URL",
    "HOME_URL",
    "ME_URL",
    "SIGNIN_URL",
    "HumanVerificationRequired",
    "LoginState",
    "BrowserLoginState",
    "QRLoginChallenge",
    "QRLoginState",
    "ZhihuHTTPAuth",
    "ZhihuBrowserAuth",
    "classify_login_probe",
]
