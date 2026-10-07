# ZhihuApis

知乎 Python API 客户端。保留旧版文章、回答评论采集类 `ZhiHu_Apis`；新增官方数据开放平台、OAuth 登录、创作者发布和媒体云上传客户端。

## 能力状态

| 能力 | 入口 | 状态与范围 |
| --- | --- | --- |
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

媒体上传另装官方 SDK：

```bash
pip install -r requirements-media.txt
```

`requirements-media.txt` 固定到已核对的官方仓库提交。旧评论签名还需 Node.js 运行时：

```bash
npm install
```

复制 `.env.example` 到本机 `.env` 后填写所需凭证。示例显式调用 `load_dotenv()`；库本身不会自动读取 `.env`，已有的进程环境变量也不会被覆盖。不要提交真实 Cookie、Access Secret、OAuth app_key 或发布密钥。

### 三类鉴权分别申请

1. **数据读取**：在[知乎数据开放平台个人中心](https://developer.zhihu.com/profile)获取 Access Secret。请求用 Bearer 和 `X-Request-Timestamp`。
2. **OAuth 第三方登录**：依[知乎 OAuth 文档](https://developer.zhihu.com/docs?key=zhihu_oauth_integrated)向 `openplatform@zhihu.com` 申请 `app_id`、`app_key` 和 `redirect_uri`。授权完成后回调参数为 `authorization_code`；后端换取用户 OAuth token。只有对应权限获批且用户授权后，才能读其公开内容。
3. **创作者发布和媒体云**：知乎个人主页 `/people/<token>` 中的 token 用作 `ZHIHU_OPENAPI_APP_KEY`；在[发布平台申请页](https://www.zhihu.com/playground/zhihu-publisher)申请 `ZHIHU_OPENAPI_APP_SECRET`。当前为内测能力，账号需获准。发布请求使用 `X-App-Key` 等 Header 和 HMAC-SHA256 签名。它与数据 Access Secret、OAuth app_key 不互换。

## 最小示例

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

测试用模拟 HTTP 验证路径、参数、鉴权 Header、签名、请求体和业务错误，不调用知乎线上接口。真实搜索、OAuth、上传和发布需具备对应账号权限后单独联调。

官方来源：[数据开放平台文档](https://developer.zhihu.com/docs)、[官方 Publish OpenAPI 协议](https://github.com/zhihu/ZhihuPublisher/blob/main/zhihu-publish/reference/publish-openapi.md)、[官方媒体云 SDK](https://github.com/zhihu/zhihu-mediacloud-uploader)。
