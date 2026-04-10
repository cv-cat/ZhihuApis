import re

import requests
from urllib.parse import urlparse, parse_qs

from utils.zhihu_utils import get_comment_headers, trans_cookies, get_x_zse_96


class ZhiHu_Apis():

    """
        获取文章的外部评论
        :param id: 文章id
        :param offset: 偏移量
        :param cookies_str: cookies字符串
        返回文章的外部评论
    """
    def get_article_outer_comment(self, id, offset, cookies_str):
        success = True
        msg = "成功"
        res_json = None
        try:
            headers = get_comment_headers()
            url = f"https://www.zhihu.com/api/v4/comment_v5/articles/{id}/root_comment"
            params = {
                "order_by": "score",
                "limit": "20",
                "offset": offset
            }
            cookies = trans_cookies(cookies_str)
            x_zse_96 = get_x_zse_96(url, params, cookies['d_c0'])
            headers['x-zse-96'] = x_zse_96
            response = requests.get(url, headers=headers, cookies=cookies, params=params)
            res_json = response.json()
        except Exception as e:
            success = False
            msg = str(e)
        return success, msg, res_json

    """
        获取文章的全部外部评论
        :param id: 文章id
        :param cookies_str: cookies字符串
        返回文章的全部外部评论
    """
    def get_article_all_outer_comment(self, id, cookies_str):
        success = True
        msg = "成功"
        comments = []
        offset = ""
        try:
            while True:
                success, msg, res_json = self.get_article_outer_comment(id, offset, cookies_str)
                if not success:
                    break
                comments.extend(res_json['data'])
                if res_json['paging']['is_end']:
                    break
                url = res_json['paging']['next']
                offset = parse_qs(urlparse(url).query)['offset'][0]
        except Exception as e:
            success = False
            msg = str(e)
        return success, msg, comments


    """
        获取文章的内部评论
        :param id: 文章id
        :param offset: 偏移量
        :param cookies_str: cookies字符串
        返回文章的外部评论
    """
    def get_article_inner_comment(self, commentid, offset, cookies_str):
        success = True
        msg = "成功"
        res_json = None
        try:
            headers = get_comment_headers()
            url = f"https://www.zhihu.com/api/v4/comment_v5/comment/{commentid}/child_comment"
            params = {
                "order_by": "score",
                "limit": "20",
                "offset": offset
            }
            cookies = trans_cookies(cookies_str)
            x_zse_96 = get_x_zse_96(url, params, cookies['d_c0'])
            headers['x-zse-96'] = x_zse_96
            response = requests.get(url, headers=headers, cookies=cookies, params=params)
            res_json = response.json()
        except Exception as e:
            success = False
            msg = str(e)
        return success, msg, res_json

    """
        获取文章的全部内部评论
        :param id: 文章id
        :param cookies_str: cookies字符串
        返回文章的全部内部评论
    """
    def get_article_all_inner_comment(self, commentid, offset, cookies_str):
        success = True
        msg = "成功"
        comments = []
        try:
            while True:
                success, msg, res_json = self.get_article_inner_comment(commentid, offset, cookies_str)
                if not success:
                    break
                comments.extend(res_json['data'])
                if res_json['paging']['is_end']:
                    break
                url = res_json['paging']['next']
                offset = parse_qs(urlparse(url).query)['offset'][0]
        except Exception as e:
            success = False
            msg = str(e)
        return success, msg, comments


    """
        获取文章的评论
        :param id: 文章id
        :param cookies_str: cookies字符串
        返回文章的评论
    """
    def get_article_all_comment(self, id, cookies_str):
        success = True
        msg = "成功"
        comments = None
        try:
            success, msg, comments = self.get_article_all_outer_comment(id, cookies_str)
            if not success:
                return success, msg, comments
            for outer_comment in comments:
                child_comment_next_offset = outer_comment['child_comment_next_offset']
                if child_comment_next_offset != None:
                    success, msg, inner_comments = self.get_article_all_inner_comment(outer_comment['id'], child_comment_next_offset, cookies_str)
                    if not success:
                        return success, msg, comments
                    outer_comment['child_comments'].extend(inner_comments)
        except Exception as e:
            success = False
            msg = str(e)
        return success, msg, comments

    """
        获取回答的外部评论
        :param id: 文章id
        :param offset: 偏移量
        :param cookies_str: cookies字符串
        返回回答的外部评论
    """
    def get_answer_outer_comment(self, id, offset, cookies_str):
        success = True
        msg = "成功"
        res_json = None
        try:
            headers = get_comment_headers()
            url = f"https://www.zhihu.com/api/v4/comment_v5/answers/{id}/root_comment"
            params = {
                "order_by": "score",
                "limit": "20",
                "offset": offset
            }
            cookies = trans_cookies(cookies_str)
            x_zse_96 = get_x_zse_96(url, params, cookies['d_c0'])
            headers['x-zse-96'] = x_zse_96
            response = requests.get(url, headers=headers, cookies=cookies, params=params)
            res_json = response.json()
        except Exception as e:
            success = False
            msg = str(e)
        return success, msg, res_json

    """
        获取回答的全部外部评论
        :param id: 文章id
        :param cookies_str: cookies字符串
        返回回答的全部外部评论
    """
    def get_answer_all_outer_comment(self, id, cookies_str):
        success = True
        msg = "成功"
        comments = []
        offset = ""
        try:
            while True:
                success, msg, res_json = self.get_answer_outer_comment(id, offset, cookies_str)
                if not success:
                    break
                comments.extend(res_json['data'])
                if res_json['paging']['is_end']:
                    break
                url = res_json['paging']['next']
                offset = parse_qs(urlparse(url).query)['offset'][0]
        except Exception as e:
            success = False
            msg = str(e)
        return success, msg, comments

    """
        获取回答的内部评论
        :param id: 文章id
        :param offset: 偏移量
        :param cookies_str: cookies字符串
        返回回答的外部评论
    """
    def get_answer_inner_comment(self, commentid, offset, cookies_str):
        success = True
        msg = "成功"
        res_json = None
        try:
            headers = get_comment_headers()
            url = f"https://www.zhihu.com/api/v4/comment_v5/comment/{commentid}/child_comment"
            params = {
                "order_by": "score",
                "limit": "20",
                "offset": offset
            }
            cookies = trans_cookies(cookies_str)
            x_zse_96 = get_x_zse_96(url, params, cookies['d_c0'])
            headers['x-zse-96'] = x_zse_96
            response = requests.get(url, headers=headers, cookies=cookies, params=params)
            res_json = response.json()
        except Exception as e:
            success = False
            msg = str(e)
        return success, msg, res_json

    """
        获取回答的全部内部评论
        :param id: 文章id
        :param cookies_str: cookies字符串
        返回回答的全部内部评论
    """
    def get_answer_all_inner_comment(self, commentid, cookies_str):
        success = True
        msg = "成功"
        comments = []
        try:
            offset = ""
            while True:
                success, msg, res_json = self.get_answer_inner_comment(commentid, offset, cookies_str)
                if not success:
                    break
                comments.extend(res_json['data'])
                if res_json['paging']['is_end']:
                    break
                url = res_json['paging']['next']
                offset = parse_qs(urlparse(url).query)['offset'][0]
        except Exception as e:
            success = False
            msg = str(e)
        return success, msg, comments

    """
        获取回答的评论
        :param id: 文章id
        :param cookies_str: cookies字符串
        返回回答的评论
    """
    def get_answer_all_comment(self, id, cookies_str):
        success = True
        msg = "成功"
        comments = None
        try:
            success, msg, comments = self.get_answer_all_outer_comment(id, cookies_str)
            if not success:
                return success, msg, comments
            for outer_comment in comments:
                child_comment_count = outer_comment['child_comment_count']
                if child_comment_count != 0:
                    success, msg, inner_comments = self.get_answer_all_inner_comment(outer_comment['id'], cookies_str)
                    if not success:
                        return success, msg, comments
                    outer_comment['child_comments'] = inner_comments
        except Exception as e:
            success = False
            msg = str(e)
        return success, msg, comments

if __name__ == '__main__':
    # orderby ts 时间
    zhihu_apis = ZhiHu_Apis()
    cookie_str = r''
    # 获取文章的全部评论
    # success, msg, comments = zhihu_apis.get_article_all_comment('685931722',  cookie_str)
    # index = 0
    # print(success, msg, comments)
    # for comment in comments:
    #     print(f'{comment["author"]["name"]}评论：{comment["content"]}')
    #     index += 1
    #     print('============================')
    #     for child_comment in comment['child_comments']:
    #         print(f'{child_comment["author"]["name"]}评论：{child_comment["content"]}')
    #         index += 1
    #         print('-------------------------------')
    # print(index)


    # 获取回答的全部评论
    success, msg, comments = zhihu_apis.get_answer_all_comment('3333952807',  cookie_str)
    index = 0
    print(success, msg)
    for comment in comments:
        print(f'{comment["author"]["name"]}评论：{comment["content"]}')
        index += 1
        print('============================')
        for child_comment in comment['child_comments']:
            print(f'{child_comment["author"]["name"]}评论：{child_comment["content"]}')
            index += 1
            print('-------------------------------')
    print(index)