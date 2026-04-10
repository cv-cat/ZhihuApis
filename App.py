import uvicorn
from apis.zhihu_apis import ZhiHu_Apis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

apis = ZhiHu_Apis()
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


"""
    获取文章的全部评论
    :json article_id: 文章的id
    :json cookies_str: cookies
"""
@app.post("/get_article_all_comment")
def get_article_all_comment(data: dict):
    try:
        article_id = data["article_id"]
        cookies_str = data["cookies_str"]
        success, msg, res = apis.get_article_all_comment(article_id, cookies_str)
        if success:
            return {"code": 200, "message": msg, "data": res}
        else:
            return {"code": 400, "message": msg, "data": None}
    except Exception as e:
        return {"code": 400, "message": str(e), "data": None}

"""
    获取回答的全部评论
    :json answer_id: 文章的id
    :json cookies_str: cookies
"""
@app.post("/get_answer_all_comment")
def get_answer_all_comment(data: dict):
    try:
        answer_id = data["answer_id"]
        cookies_str = data["cookies_str"]
        success, msg, res = apis.get_answer_all_comment(answer_id, cookies_str)
        if success:
            return {"code": 200, "message": msg, "data": res}
        else:
            return {"code": 400, "message": msg, "data": None}
    except Exception as e:
        return {"code": 400, "message": str(e), "data": None}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5007, forwarded_allow_ips='*')
