<div align="center">
    <a href="https://www.python.org/">
        <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
    </a>
    <a href="https://nodejs.org/zh-cn/">
        <img src="https://img.shields.io/badge/nodejs-20%2B-green" alt="NodeJS 20+">
    </a>
    <a href="https://fastapi.tiangolo.com/">
        <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688" alt="FastAPI">
    </a>
</div>

# 💬 Zhihu Platform

**✨ 专业的知乎评论数据采集解决方案，支持文章与回答的全量评论抓取**

当你需要让 AI Agent 感知知乎内容生态——自动采集评论舆论、分析用户观点、驱动内容运营策略——第一道墙往往不是模型能力，而是**平台数据获取能力的缺失**。

本项目做的事很简单：把这道墙拆掉。

**⚠️ 严禁用于爬取用户隐私、违规商业用途！本项目仅供学习与技术研究使用，后果自负。**

## 🌟 功能特性

- ✅ **评论全量采集**
  - 支持**文章**（专栏）评论抓取
  - 支持**回答**评论抓取
  - 自动翻页，递归获取所有楼中楼（子评论）
- 🔐 **x-zse-96 签名自动计算**
  - 内嵌 JS 运行时，自动生成知乎鉴权签名参数
  - 适配知乎最新 `x-zse-96` / `x-zse-93` 接口鉴权
- 🚀 **高性能服务**
  - 基于 FastAPI + Uvicorn 异步服务
  - 支持 Docker 一键部署

## 🛠️ 快速开始

### ⛳ 运行环境

- Python 3.10+
- Node.js 20+

### 🎯 本地安装

```bash
pip install -r requirements.txt
npm install
```

### 🚀 运行项目

```bash
python App.py
```

服务启动后访问 http://localhost:5007/docs 查看交互式 API 文档。

### 🎨 Cookie 配置

在浏览器中打开 [www.zhihu.com](https://www.zhihu.com)，**登录账号**后按 `F12` 打开开发者工具，点击「网络」→ 找任意一个 API 请求 → 复制请求头中的 `Cookie` 字段值。

> ⚠️ 注意：必须登录后获取的 Cookie 才有效，其中 `d_c0` 字段用于 x-zse-96 签名计算，缺失将导致请求失败。

将获取到的 Cookie 字符串作为 `cookies_str` 参数传入接口，格式如下：

```
_zap=xxx; d_c0=xxx; z_c0=xxx; ...
```

## 📡 接口说明

### POST `/get_article_all_comment`

获取知乎**专栏文章**的全部评论（含所有楼中楼子评论）。

**请求参数**

| 字段          | 类型  | 必填 | 说明               |
|-------------|-----|----|------------------|
| article_id  | str | 是  | 文章 ID（URL 中的数字部分）|
| cookies_str | str | 是  | 知乎登录 Cookie 字符串  |

**请求示例**

```bash
curl -X POST http://localhost:5007/get_article_all_comment \
  -H "Content-Type: application/json" \
  -d '{
    "article_id": "685931722",
    "cookies_str": "_zap=xxx; d_c0=xxx; z_c0=xxx"
  }'
```

**响应示例**

```json
{
  "code": 200,
  "message": "成功",
  "data": [
    {
      "id": 123456789,
      "author": {
        "name": "用户昵称",
        "avatar_url": "https://..."
      },
      "content": "评论内容",
      "like_count": 42,
      "child_comment_count": 3,
      "child_comments": [
        {
          "id": 987654321,
          "author": { "name": "回复用户" },
          "content": "子评论内容"
        }
      ]
    }
  ]
}
```

---

### POST `/get_answer_all_comment`

获取知乎**回答**的全部评论（含所有楼中楼子评论）。

**请求参数**

| 字段          | 类型  | 必填 | 说明               |
|-------------|-----|----|------------------|
| answer_id   | str | 是  | 回答 ID（URL 中的数字部分）|
| cookies_str | str | 是  | 知乎登录 Cookie 字符串  |

**请求示例**

```bash
curl -X POST http://localhost:5007/get_answer_all_comment \
  -H "Content-Type: application/json" \
  -d '{
    "answer_id": "3333952807",
    "cookies_str": "_zap=xxx; d_c0=xxx; z_c0=xxx"
  }'
```

**响应示例**

```json
{
  "code": 200,
  "message": "成功",
  "data": [
    {
      "id": 111222333,
      "author": {
        "name": "用户昵称"
      },
      "content": "评论内容",
      "child_comment_count": 2,
      "child_comments": [
        {
          "id": 444555666,
          "author": { "name": "回复用户" },
          "content": "子评论内容"
        }
      ]
    }
  ]
}
```

## 🐳 Docker 部署

```bash
docker build -t zhihu-platform .
docker run -d -p 5007:5007 zhihu-platform
```

## 🍥 日志

| 日期       | 说明                               |
|----------|------------------------------------|
| 26/04/10 | 项目初始化，完成文章与回答评论全量抓取 API 封装 |


## 🤝 欢迎贡献 PR

本项目欢迎任何形式的贡献！如果你有新功能想法、Bug 修复或文档改进，欢迎提交 PR。

- Fork 本仓库并在新分支上开发
- 保持代码风格与现有代码一致
- PR 描述中请简要说明改动内容和目的
- 也欢迎通过 [Issue](https://github.com/cv-cat/ZhihuApis/issues) 提出建议或报告问题

## 🧸 额外说明
1. 感谢 star⭐ 和 follow📰！不时更新
2. 作者的联系方式在主页里，有问题可以随时联系我
3. 可以关注下作者的其他项目，欢迎 PR 和 issue
4. 感谢赞助！如果此项目对您有帮助，请作者喝一杯奶茶~~ （开心一整天😊😊）
5. thank you~~~


## 📈 Star 趋势
<a href="https://www.star-history.com/#cv-cat/ZhihuApis&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=cv-cat/ZhihuApis&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=cv-cat/ZhihuApis&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=cv-cat/ZhihuApis&type=Date" />
 </picture>
</a>


## 🍔 交流群
如果你对爬虫和 AI Agent 感兴趣，请加作者主页 wx 通过邀请加入群聊

ps: 群123已超过wx限制人数500，请加群4

![06f69d67ff814b84e122bb32d123075b](https://github.com/cv-cat/Spider_XHS/blob/master/author/group4_2026_04_08)
