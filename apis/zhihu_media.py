"""调用知乎官方 zhihu-mediacloud-uploader SDK。"""

from __future__ import annotations

from collections.abc import Callable


class ZhihuMediaAPI:
    def __init__(self, app_key: str, app_secret: str, *, uploader_factory: Callable | None = None) -> None:
        if not app_key or not app_secret:
            raise ValueError("媒体云上传需要发布 OpenAPI 凭证")
        if uploader_factory is None:
            try:
                from mediacloud_uploader import MediaCloudUploader
            except ImportError as exc:
                raise RuntimeError("请先安装 requirements-media.txt 中的知乎官方媒体云 SDK") from exc
            uploader_factory = MediaCloudUploader
        self._uploader = uploader_factory(app_key=app_key, app_secret=app_secret)

    @staticmethod
    def _check_source(file_path: str | None, url: str | None) -> None:
        if bool(file_path) == bool(url):
            raise ValueError("file_path 与 url 必须且只能提供一个")

    def upload_image(
        self,
        *,
        scene_name: str,
        file_path: str | None = None,
        url: str | None = None,
        content_type: str = "",
    ):
        self._check_source(file_path, url)
        if scene_name not in {"answer", "question", "pin", "article"}:
            raise ValueError("scene_name 无效")
        return self._uploader.upload_image(
            scene_name=scene_name, file_path=file_path, url=url, content_type=content_type
        )

    def upload_video(
        self,
        *,
        scene_name: str = "pin",
        file_path: str | None = None,
        url: str | None = None,
        content_type: str = "",
    ):
        """媒体云可上传视频；当前 Publish OpenAPI 文档未定义视频作品发布。"""
        self._check_source(file_path, url)
        return self._uploader.upload_video(
            scene_name=scene_name, file_path=file_path, url=url, content_type=content_type
        )
