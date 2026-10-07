# ZhihuApis

知乎 Python API 客户端。保留旧版文章、回答评论采集类 `ZhiHu_Apis`；新增官方数据开放平台、OAuth 登录、创作者发布和媒体云上传客户端。

## 能力状态

| 能力 | 入口 | 状态与范围 |
| --- | --- | --- |
| 本人网页扫码登录 | `ZhihuBrowserAuth.open_login()` / `verify_account()` | 可见浏览器展示知乎自己的二维码；本人扫码。会话保存在内存或独立浏览器配置中；只读核验账号态，不生成 OAuth token。 |
| 网页综合搜索 | `ZhihuWebAPI.search()` | 已登录网页的 `/api/v4/search_v3` 实测返回 200；混合结果，实测 `offset` 翻页。属于网页接口，可能随站点调整。 |
| 网页 Item | `ZhihuWebAPI.get_item()` | 已实测回答和专栏文章返回 `content`；支持网页 URL 与搜索结果中的 `api.zhihu.com` URL。受内容权限和截断规则影响。 |
| 网页草稿计数 | `ZhihuWebAPI.draft_counts()` | 只读读取回答、文章草稿计数；网页草稿入口为 `/draft?type=answer` 和 `/draft?type=article`。 |
| 网页文章草稿 | `ZhihuWebAPI.save_web_draft()` / `get_web_draft()` / `delete_web_draft()` | 已实测创建、更新、回读及删除一篇文章草稿；只处理草稿，不公开发布。网页协议可能变动。 |
| 知乎第三方登录 | `ZhihuOAuth.authorization_url()` / `exchange_code()` | 官方 OAuth 授权码流程；需申请应用凭证。 |
| 站内搜索 | `ZhihuDataAPI.search()` | 官方数据开放平台；单次最多 10 条，当前无连续分页。 |
| item 全文 | `ZhihuDataAPI.get_item()` | 官方“我的创作全文”；仅当前 Access Secret 所属账号的已发布作品。 |
| 用户作品列表 | `ZhihuDataAPI.list_user_contents()` | 本人，或另行获得 OAuth 授权的用户；返回摘要。 |
| 问题回答列表 | `ZhihuDataAPI.question_answers()` | 回答摘要与分页，不是全文或发布。 |
| 发布文章 / 提问 / 想法 | `ZhihuCreatorAPI.publish_article/question/pin()` | 官方 Publish OpenAPI；需创作者发布凭证和明确的 `confirmed=True`。 |
| 发布回答 | `ZhihuCreatorAPI.publish_answer()` | 官方 Publish OpenAPI 未文档化 `answer` 类型；调用会显式抛出 `UnsupportedCapabilityError`。 |
| 图片 / 视频上传 | `ZhihuMediaAPI.upload_image/video()` | 复用知乎官方媒体云 SDK。媒体上传成功不代表作品发布；当前发布规范未提供视频作品发布流程。 |
| 文章 / 回答评论 | `ZhiHu_Apis` 与旧 FastAPI 路由 | 保留原有 Cookie + `x-zse-96` 实现与三元组返回契约。 |

## 安装

Python 3.10+：

```bash
pip install -r requirements.txt
```

本人网页扫码登录助手另装 Playwright：

```bash
pip install -r requirements-browser.txt
```

默认启动本机 Chrome 的可见窗口；运行环境还需安装 Chrome。`channel="chromium"` 可改用 Playwright Chromium，需先运行 `python -m playwright install chromium`。浏览器使用专属配置目录，不要指向日常 Chrome 的用户数据目录。

媒体上传另装官方 SDK：

```bash
pip install -r requirements-media.txt
```

`requirements-media.txt` 固定到已核对的官方仓库提交。旧评论签名还需 Node.js 运行时：

```bash
npm install
```

复制 `.env.example` 到本机 `.env` 后填写所需凭证。示例显式调用 `load_dotenv()`；库本身不会自动读取 `.env`，已有的进程环境变量也不会被覆盖。不要提交真实 Cookie、Access Secret、OAuth app_key 或发布密钥。

### 网页会话与三类官方鉴权

网页扫码登录仅供本人在可见浏览器里建立知乎网页会话。它无需开发者凭证，也不会生成数据平台 Access Secret、第三方 OAuth token 或创作者发布签名凭证。下列三类官方鉴权分别申请：

1. **数据读取**：在[知乎数据开放平台个人中心](https://developer.zhihu.com/profile)获取 Access Secret。请求用 Bearer 和 `X-Request-Timestamp`。
2. **OAuth 第三方登录**：依[知乎 OAuth 文档](https://developer.zhihu.com/docs?key=zhihu_oauth_integrated)向 `openplatform@zhihu.com` 申请 `app_id`、`app_key` 和 `redirect_uri`。授权完成后回调参数为 `authorization_code`；后端换取用户 OAuth token。只有对应权限获批且用户授权后，才能读其公开内容。
3. **创作者发布和媒体云**：知乎个人主页 `/people/<token>` 中的 token 用作 `ZHIHU_OPENAPI_APP_KEY`；在[发布平台申请页](https://www.zhihu.com/playground/zhihu-publisher)申请 `ZHIHU_OPENAPI_APP_SECRET`。当前为内测能力，账号需获准。发布请求使用 `X-App-Key` 等 Header 和 HMAC-SHA256 签名。它与数据 Access Secret、OAuth app_key 不互换。

## 最小示例

本人网页扫码与只读账号态核验：

```python
from apis.zhihu_browser_auth import ZhihuBrowserAuth
from apis.zhihu_web_apis import ZhihuWebAPI

with ZhihuBrowserAuth(profile_dir=".zhihu-browser-profile") as login:
    login.open_login()  # 知乎页面展示二维码；请本人用知乎 App 扫码
    input("扫码完成后按回车核验账号态：")
    state = login.verify_account()
    print("已确认登录：", state.authenticated is True, "核验结果：", state.reason)
    if state.authenticated is True:
        web = ZhihuWebAPI(login)
        results = web.search("咖啡", limit=5)
        print("网页搜索结果数：", len(results["data"]))
        for result in results["data"]:
            item = result.get("object") or {}
            if item.get("type") in {"answer", "article"} and item.get("url"):
                detail = web.get_item(item["url"])
                print("内容类型和正文长度：", detail["type"], len(detail["content"]))
                break
        counts = web.draft_counts()  # 只读；含 answer / article 计数
```

`verify_account()` 只打开知乎首页并读取浏览器内 `/api/v4/me` 的状态与用户类型；不会返回个人资料或 Cookie。`authenticated=True` 表示响应明确识别为非访客；`False` 表示明确识别为访客；`None` 表示请求被拒或响应未能识别，需要在浏览器内人工确认。已有登录的 Chrome 中实测 `/api/v4/me` 返回 200、`user_type=people`；独立 `ZhihuBrowserAuth` 可见窗口也已实际扫码确认，并完成一次登录 → 搜索 → 回答详情调用。`profile_dir=None` 则仅在当前进程内保留会话；示例配置目录已被 Git 忽略，其中可能包含敏感会话数据，请妥善保管。关闭浏览器后，持久配置可供下一次运行继续使用，具体登录有效期由知乎决定。这里不实现二维码 HTTP 协议，也不把网页会话传给下文的官方 API 客户端。

若要用本人已登录 Chrome 的 Cookie 在仓库代码中验收，可以通过隐藏输入导入临时浏览器上下文。`import_cookie_header()` 仅允许 `profile_dir=None`，不将 Cookie 写入项目文件，也不在异常中回显。关闭上下文即清除临时会话。不要把 Cookie 放进命令参数、源码、日志或聊天消息。

```python
from getpass import getpass
from apis.zhihu_browser_auth import ZhihuBrowserAuth
from apis.zhihu_web_apis import ZhihuWebAPI

with ZhihuBrowserAuth(headless=True) as login:
    cookie_header = getpass("本人 Cookie（隐藏输入）：")
    login.import_cookie_header(cookie_header)
    del cookie_header
    if login.verify_account().authenticated is not True:
        raise RuntimeError("登录态未确认")
    web = ZhihuWebAPI(login)
    results = web.search("咖啡", limit=5)
    print("结果数：", len(results["data"]))
```

这条临时 Cookie 导入链已通过离线契约测试；独立可见窗口的真实仓库级回答调用已联调。专栏文章详情使用新标签，网络请求和导航均有超时；若站点保持导航任务，调用会返回有界错误而不会长期阻塞。

网页搜索、Item 和草稿计数方法调用的接口均为 GET；整个客户端不导出 Cookie。打开文章页面会运行站点脚本，可能产生站点自己的埋点或浏览记录请求。网页综合搜索可能混入用户、热词、广告和内容，`paging.next` 由知乎返回；已验证通过 `offset=0`、`offset=2` 读取，长链路分页尚未验收。回答读取使用 `/api/v4/answers/{id}?include=content,...`；专栏文章在同一浏览器配置的新标签请求 `zhuanlan.zhihu.com/api/articles/{id}`，完成后关闭该标签。接口返回的 `content` 可能受付费、权限或截断限制。当前代码支持的 Item 只有回答与文章。`DRAFT_URLS` 给出已观察到的网页草稿入口。

创作菜单的“写文章”打开 `https://zhuanlan.zhihu.com/write`。已用中性临时内容实测：`POST zhuanlan.zhihu.com/api/articles/drafts` 创建标题草稿，`PATCH /api/articles/{id}/draft` 保存 HTML 正文，`GET /api/articles/{id}/draft` 回读为 `state=draft`；`DELETE www.zhihu.com/api/v4/articles/{id}/draft` 返回 200，刷新草稿列表后临时草稿消失。`save_web_draft()` 按此顺序创建并回读核验。如果创建后更新或回读失败，会抛出 `ZhihuWebDraftSaveError`，其 `draft_id` 可用于检查并清理残留草稿。网页接口可能变更，先用临时内容验收自己的账号。

```python
from apis.zhihu_browser_auth import ZhihuBrowserAuth
from apis.zhihu_web_apis import ZhihuWebAPI

with ZhihuBrowserAuth(profile_dir=".zhihu-browser-profile") as login:
    login.open_login()
    input("本人扫码后按回车核验：")
    if login.verify_account().authenticated is not True:
        raise RuntimeError("账号态未确认，请在浏览器中检查")
    web = ZhihuWebAPI(login)
    draft = web.save_web_draft("待修改的标题", "<p>待修改的正文</p>")
    print("草稿状态：", draft["state"])
    # 需要清理这篇草稿时，明确调用：web.delete_web_draft(draft["id"])
```

网页写入目前仅覆盖文章草稿。没有实测网页图片/视频上传、回答或想法草稿、公开发布请求，因此没有对应方法。正式发布使用下文已文档化的官方 Publish OpenAPI，并取得发布凭证。

```python
import os
from dotenv import load_dotenv
from apis.zhihu_data_apis import ZhihuDataAPI

load_dotenv()
data = ZhihuDataAPI(os.environ["ZHIHU_ACCESS_SECRET"])
items = data.search("咖啡", count=5)["Items"]
owned = data.list_user_contents(content_type="article", limit=1)
if owned["Items"]:
    own_article = data.get_item(owned["Items"][0]["Url"])
    print(own_article["Title"])
# 翻页时可把 owned["Paging"]["NextOffset"] 字符串直接传给 offset。
data.close()
```

第三方登录单独使用已获批的 OAuth 应用凭证。授权回调携带的是 `authorization_code`，不要把回调 URL 或 token 发到聊天或写入仓库：

```python
import os
from dotenv import load_dotenv
from apis.zhihu_data_apis import ZhihuDataAPI
from apis.zhihu_oauth import ZhihuOAuth

load_dotenv()
oauth = ZhihuOAuth(
    os.environ["ZHIHU_OAUTH_APP_ID"],
    os.environ["ZHIHU_OAUTH_APP_KEY"],
    os.environ["ZHIHU_OAUTH_REDIRECT_URI"],
)
print(oauth.authorization_url())  # 在本机浏览器打开，并同意所申请的权限
callback_url = input("在本机粘贴授权后的完整回调地址：").strip()
code = oauth.authorization_code_from_callback(callback_url)
user_token = oauth.exchange_code(code)["access_token"]
oauth.close()

data = ZhihuDataAPI(os.environ["ZHIHU_ACCESS_SECRET"])
authorized = data.list_user_contents(oauth_token=user_token, limit=1)
print("授权用户内容条数：", len(authorized["Items"]))
data.close()
```

OAuth 验收需同时具备数据开放平台 Access Secret，且应用已获批“公开内容”权限。此示例只验证授权用户作品列表；`get_item()` 仍只读取 Access Secret 所属账号本人的全文。没有已发布内容时，空列表也可能是正常结果，需结合账号与授权范围判断。

发布凭证获批后再构造发布客户端。应用展示并核对标题、HTML 正文及发布设置后，才提交：

```python
import os
from dotenv import load_dotenv
from apis.zhihu_creator_apis import ZhihuCreatorAPI

load_dotenv()
creator = ZhihuCreatorAPI(os.environ["ZHIHU_OPENAPI_APP_KEY"], os.environ["ZHIHU_OPENAPI_APP_SECRET"])
# result = creator.publish_article("标题", "<p>正文</p>", confirmed=True)
# print(result["data"]["url"])
```

`publish_question(title, html="", confirmed=True)` 发布提问；`publish_pin(html, confirmed=True, image_urls=[...])` 发布想法。`confirmed=False` 时不发送网络请求。成功以响应 JSON 的 `status == 0` 为准。发布前应按[知乎官方发布规范](https://github.com/zhihu/ZhihuPublisher)完成内容校验与本地预览。频率、审核和权限以账号实际返回为准。

媒体上传示例：

```python
import os
from dotenv import load_dotenv
from apis.zhihu_media import ZhihuMediaAPI

load_dotenv()
media = ZhihuMediaAPI(os.environ["ZHIHU_OPENAPI_APP_KEY"], os.environ["ZHIHU_OPENAPI_APP_SECRET"])
upload = media.upload_image(scene_name="article", file_path=r"C:\path\to\photo.png")
print(upload.media_key, upload.is_success)
```

想法发布的独立图片字段需要可用图片 URL。媒体云返回 `media_key` 时，按官方图片处理结果取得 URL；不要直接用 `media_key` 拼 URL。文章、提问的正文图片应放进已校验的 HTML。

## 旧评论接口兼容

原 `apis.zhihu_apis.ZhiHu_Apis` 方法名、参数、`(success, msg, result)` 返回形式保留。`App.py` 的 `POST /get_article_all_comment`、`POST /get_answer_all_comment` 路由保留。运行：

```bash
python App.py
```

服务默认 `http://localhost:5007/docs`。旧评论接口仍需登录 Cookie 字符串，包含 `d_c0`；`static/zhihu.js` 用于计算原有签名。新官方客户端不会用这些 Cookie。

## 测试与资料

```bash
python -m unittest discover -s tests -v
```

测试用模拟 HTTP 验证官方接口的路径、参数、鉴权 Header、签名、请求体和业务错误；浏览器助手使用模拟 Playwright 验证可见窗口、会话目录、网页读写请求和错误处理。测试本身不启动 Chrome。网页搜索、回答和文章详情、草稿计数已在已登录的 Chrome 中用客户端实际浏览器 GET 函数验证；文章草稿的 UI 自动保存及同源直接创建、更新、回读、删除均实测成功，临时草稿已清理。Python Playwright 浏览器生命周期仍需在独立配置完成扫码后端到端验收。OAuth、上传和发布需具备对应账号权限后单独联调。

官方来源：[数据开放平台文档](https://developer.zhihu.com/docs)、[官方 Publish OpenAPI 协议](https://github.com/zhihu/ZhihuPublisher/blob/main/zhihu-publish/reference/publish-openapi.md)、[官方媒体云 SDK](https://github.com/zhihu/zhihu-mediacloud-uploader)。
