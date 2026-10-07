"""知乎网页端 ``x-zse-96`` 签名。

签名链来自当前网页脚本中的 ``tv`` 函数：

``101_3_3.0 + pathname?query + d_c0 + body(<=4096) + x-zst-81``

各非空字段用 ``+`` 连接，再以网页内置的 3.0 加密器对
``md5(source)`` 做编码。默认使用从当前静态脚本提取的纯 Python SM4/CBC
实现，不创建浏览器页面，也不访问网络。需要核对脚本版本时可显式设置
``use_pure=False``；调用方也可以注入 ``encryptor`` 做单测。
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from apis.zhihu_zse_pure import encrypt_source


ZSE93 = "101_3_3.0"
SIGNATURE_VERSION = "2.0"


def _body_text(body: Any) -> str:
    """按浏览器 ``BodyInit`` 的字符串化规则取签名 body。"""

    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", "replace")
    if isinstance(body, str):
        return body
    if isinstance(body, Mapping):
        # requests 对 data 映射会产生表单；调用方需要在 prepare 前传入
        # 已编码 body 才能保留和浏览器一样的字段顺序。这个分支用于
        # 直接调用 signer 时给出稳定的 JSON 预览，不伪装成表单编码。
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    return str(body)


class ZhihuWebSigner:
    """生成当前网页使用的 ``x-zse-96``。

    ``encryptor`` 接收网页脚本中 ``md5(source)`` 的十六进制字符串，
    返回加密后的签名正文。默认走 ``apis.zhihu_zse_pure``；设置
    ``use_pure=False`` 时才懒加载仓库内 ``static/zhihu.js`` 做脚本对照。
    """

    def __init__(
        self,
        *,
        encryptor: Callable[[str], str] | None = None,
        script_path: str | os.PathLike[str] | None = None,
        use_pure: bool = True,
    ) -> None:
        self._encryptor = encryptor
        self._use_pure = bool(use_pure)
        self._script_path = Path(script_path) if script_path is not None else Path(__file__).resolve().parent.parent / "static" / "zhihu.js"
        self._ctx = None

    def _load_encryptor(self) -> Callable[[str], str]:
        if self._encryptor is not None:
            return self._encryptor
        if self._ctx is None:
            try:
                import execjs
            except ImportError as exc:  # pragma: no cover - optional runtime
                raise RuntimeError("需要 PyExecJS 才能加载知乎网页签名脚本") from exc
            source = self._script_path.read_text(encoding="utf-8")
            # ``other.js`` 注册 webpack 的 1514 加密模块。使用绝对路径
            # 让调用方从任意工作目录启动时仍能加载同一份脚本。
            other_path = self._script_path.parent / "other.js"
            source = source.replace(
                "const zc =  require('./static/other')",
                "const zc = require(" + json.dumps(str(other_path)) + ")",
            )
            node_modules = self._script_path.parent.parent / "node_modules"
            jsdom_path = node_modules / "jsdom"
            if jsdom_path.exists():
                source = source.replace(
                    'const jsdom = require("jsdom")',
                    "const jsdom = require(" + json.dumps(str(jsdom_path)) + ")",
                )
            previous = os.environ.get("NODE_PATH")
            if node_modules.exists():
                os.environ["NODE_PATH"] = str(node_modules)
            try:
                # tv 是静态脚本暴露的顶层函数；它会调用 webpack 模块
                # 1514 中的本地加密器。追加一个稳定名字给 Python 调用。
                source += "\nvar tr = function(value){ return Buffer.byteLength(String(value), 'utf8'); };\nfunction __zhihu_tv(url, body, d0, zst){ return tv(url, body, {zse93:'101_3_3.0', dc0:d0, xZst81:zst}, ''); }\n"
                self._ctx = execjs.compile(source)
            finally:
                if previous is None:
                    os.environ.pop("NODE_PATH", None)
                else:
                    os.environ["NODE_PATH"] = previous
        return lambda digest: str(self._ctx.call("__zhihu_encrypt", digest))

    @staticmethod
    def source(
        url: str,
        *,
        d_c0: str | None = None,
        body: Any = None,
        x_zst_81: str | None = None,
    ) -> str:
        parsed = urlsplit(str(url))
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        body_text = _body_text(body)
        parts = [ZSE93, path]
        if d_c0:
            parts.append(str(d_c0))
        if body_text and len(body_text.encode("utf-8")) <= 4096:
            parts.append(body_text)
        if x_zst_81:
            parts.append(str(x_zst_81))
        return "+".join(parts)

    def sign(
        self,
        url: str,
        *,
        d_c0: str | None = None,
        body: Any = None,
        x_zst_81: str | None = None,
    ) -> tuple[str, str]:
        """返回 ``(x-zse-96, signature_source)``。"""

        body_text = _body_text(body)
        if self._encryptor is None and self._use_pure:
            source = self.source(url, d_c0=d_c0, body=body_text, x_zst_81=x_zst_81)
            encrypted = encrypt_source(source)
            return f"{SIGNATURE_VERSION}_{encrypted}", source
        if self._encryptor is None:
            if self._ctx is None:
                self._load_encryptor()
            result = self._ctx.call("__zhihu_tv", str(url), body_text, d_c0, x_zst_81)
            if not isinstance(result, Mapping):
                raise ValueError("知乎网页脚本未返回签名对象")
            encrypted = str(result.get("signature") or "")
            source = str(result.get("source") or "")
            if not encrypted:
                raise ValueError("知乎网页加密器返回空签名")
            return f"{SIGNATURE_VERSION}_{encrypted}", source
        source = self.source(url, d_c0=d_c0, body=body_text, x_zst_81=x_zst_81)
        digest = hashlib.md5(source.encode("utf-8")).hexdigest()
        encrypted = self._load_encryptor()(digest)
        if not encrypted:
            raise ValueError("知乎网页加密器返回空签名")
        return f"{SIGNATURE_VERSION}_{encrypted}", source

    def headers(
        self,
        url: str,
        *,
        d_c0: str | None = None,
        body: Any = None,
        x_zst_81: str | None = None,
    ) -> dict[str, str]:
        value, _ = self.sign(url, d_c0=d_c0, body=body, x_zst_81=x_zst_81)
        return {"x-zse-93": ZSE93, "x-zse-96": value}


__all__ = ["SIGNATURE_VERSION", "ZSE93", "ZhihuWebSigner"]
