"""知乎官方接口客户端共用错误。"""


class ZhihuAPIError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, http_status: int | None = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class ConfirmationRequiredError(ValueError):
    """发布前尚未确认内容。"""


class UnsupportedCapabilityError(NotImplementedError):
    """官方文档未覆盖的能力。"""
