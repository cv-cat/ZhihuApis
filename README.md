# ZhihuApis

知乎数据读取、网页会话接口、OAuth 和发布 OpenAPI 的 Python 客户端。所有
网页请求都由 `requests.Session` 发出，可在服务器或脚本中运行。

## 能力边界

| 模块 | 能力 | 认证材料 |
| --- | --- | --- |
| `apis.zhihu_http_auth.ZhihuHTTPAuth` | Cookie 会话、二维码 token、扫码状态、账号探针、官方验证码票据、短信/密码登录请求 | 本人 Cookie，或用户在知乎 App 扫码；短信和密码请求需要当前网页产生的 `zsEncrypt` body |
| `apis.zhihu_web_apis.ZhihuWebAPI` | 搜索、回答/文章详情、草稿计数、文章草稿创建/更新/回读/删除 | `ZhihuHTTPAuth` 的 `requests.Session` |
| `apis.zhihu_data_apis.ZhihuDataAPI` | 官方内容搜索、本人作品详情、本人作品列表、问题回答摘要 | 开发者中心 Access Secret；用户列表可附 OAuth token |
| `apis.zhihu_oauth.ZhihuOAuth` | OAuth 授权地址、回调校验、授权码换 token | 申请到的 `app_id`、`app_key`、注册回调地址 |
| `apis.zhihu_creator_apis.ZhihuCreatorAPI` | 官方 OpenAPI 发布文章、提问、想法 | Publish OpenAPI `app_key`、`app_secret` |
| `apis.zhihu_media.ZhihuMediaAPI` | 官方媒体云上传图片/视频 | Publish OpenAPI 凭证和可选 `requirements-media.txt` |

网页草稿接口只保存草稿，不公开发布。公开作品使用官方 `ZhihuCreatorAPI`
并显式传 `confirmed=True`。

## 安装

```bash
python -m pip install -r requirements.txt
# 需要媒体云上传时再安装
python -m pip install -r requirements-media.txt
```

## Cookie 会话、搜索和内容采集

从自己账号的请求头复制完整 Cookie，放入环境变量或进程内变量，不要提交到
Git。客户端只把 Cookie 放进内存中的 `requests.Session`。

```python
import os

from apis.zhihu_http_auth import ZhihuHTTPAuth
from apis.zhihu_web_apis import ZhihuWebAPI

cookie = os.environ["ZHIHU_COOKIE"]
with ZhihuHTTPAuth.from_cookie(cookie) as auth:
    state = auth.verify_account()
    if state.authenticated is not True:
        raise RuntimeError(f"账号状态未确认：{state.reason}")

    api = ZhihuWebAPI(auth)
    results = api.search("咖啡", limit=10)
    answer = api.get_item("https://www.zhihu.com/question/1/answer/2")
    article = api.get_item("https://zhuanlan.zhihu.com/p/123")
```

`verify_account()` 只在 `/api/v4/me` 返回 200 且 `user_type` 明确为非
`guest` 时报告 `authenticated=True`。401、403 或无法识别的响应会保留为
未知态，不会把 HTTP 成功误判成已登录。

## 二维码登录（纯 HTTP）

当前网页脚本使用以下请求：

1. `POST https://www.zhihu.com/udid` 获取本会话的 `x-du-bid`。
2. `POST /api/v3/account/api/login/qrcode` 获取 `token`、`link`、`expires_at`。
3. `GET /api/v3/account/api/login/qrcode/{token}/scan_info` 轮询扫码状态。

`link` 是二维码原文，可交给任意二维码渲染库或直接显示给用户；扫码和在
手机端确认登录由用户完成。

```python
from apis.zhihu_http_auth import HumanVerificationRequired, ZhihuHTTPAuth

auth = ZhihuHTTPAuth()
challenge = auth.begin_qr_login()
print("请使用知乎 App 扫描：", challenge.qr_text)
try:
    state = auth.wait_for_qr_login(challenge, timeout_seconds=180)
except HumanVerificationRequired:
    # 接口返回安全验证（当前实测为 HTTP 403 / code=40352）。
    # 在知乎官方页面完成人工验证后重新创建会话并轮询，不自动处理验证码。
    raise
print(state.authenticated, state.reason)
```

账号登录后的 Cookie 由知乎通过响应 `Set-Cookie` 写入同一个 `Session`，
最终仍以 `/api/v4/me` 作为登录闭环证据。若扫码状态接口返回安全验证，
客户端会抛出 `HumanVerificationRequired`，不会伪造票据或绕过挑战。

## 短信、密码和验证码

短信登录脚本目前会对 `phone_no`、验证码等字段生成动态 `zsEncrypt` body。
算法随网页版本变化，客户端不发送未经验证的明文替代请求。先请求官方验
证码信息并由用户完成验证，再把当前抓包得到的加密 body 传入：

```python
auth = ZhihuHTTPAuth()
captcha = auth.get_captcha(scene="digits_login")
# 用户完成知乎官方验证码后取得 ticket；不要在脚本中生成或绕过 ticket。
auth.validate_captcha(ticket, scene="digits_login")
auth.request_sms_code(
    "13800000000",
    captcha_ticket=ticket,
    encrypted_body=current_zs_encrypt_body,
)
auth.validate_sms_code(
    "13800000000",
    sms_code,
    encrypted_body=current_validate_zs_encrypt_body,
)
```

也可以给构造函数注入经过验证的 `body_encryptor`，其签名为
`Mapping -> (encrypted_body, extra_headers)`。未提供加密 body 时方法会明确
抛出 `UnsupportedCapabilityError`，避免把看似成功的明文请求当成协议实现。

## 网页草稿

```python
with ZhihuHTTPAuth.from_cookie(cookie) as auth:
    api = ZhihuWebAPI(auth)
    result = api.save_web_draft("临时标题", "<p>正文</p>")
    draft = api.get_web_draft(result["id"])
    api.delete_web_draft(result["id"])
```

保存流程按顺序执行 `POST /api/articles/drafts`、`PATCH
/api/articles/{id}/draft` 和回读；中间失败会抛出
`ZhihuWebDraftSaveError`，其中保留已创建的 `draft_id`，便于清理残留草稿。

## 官方数据与发布接口

```python
from apis.zhihu_data_apis import ZhihuDataAPI
from apis.zhihu_creator_apis import ZhihuCreatorAPI

data = ZhihuDataAPI(os.environ["ZHIHU_ACCESS_SECRET"])
print(data.search("Python", count=10))
print(data.list_user_contents(content_type="article", limit=20))

creator = ZhihuCreatorAPI(
    os.environ["ZHIHU_OPENAPI_APP_KEY"],
    os.environ["ZHIHU_OPENAPI_APP_SECRET"],
)
creator.publish_article("标题", "<p>正文</p>", confirmed=True)
creator.publish_question("问题", confirmed=True)
creator.publish_pin("<p>想法</p>", confirmed=True)
```

发布接口会检查官方响应中的业务 `status`，而不只看 HTTP 200。回答发布不
在当前 Publish OpenAPI 文档范围内，调用会抛出
`UnsupportedCapabilityError`。媒体上传单独使用知乎官方媒体云 SDK。

## 测试与已知限制

```bash
python -m unittest discover -s tests -q
python -m compileall -q .
```

测试使用假的 `requests.Session` 验证 URL、方法、Cookie、Header、请求体、
错误码和草稿回读，不访问真实账号。当前实测的二维码状态请求在受限环境
返回 HTTP 403、错误码 40352，代码会将其报告为人工安全验证；这不是可自动
完成的登录成功证据。短信和密码的 `zsEncrypt` 仍必须由当前网页版本产生
的加密 body 提供。
