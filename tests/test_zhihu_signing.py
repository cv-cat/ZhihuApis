import hashlib
import unittest

from apis.zhihu_signing import ZSE93, ZhihuWebSigner


class ZhihuSigningTests(unittest.TestCase):
    def test_source_preserves_path_query_body_and_optional_fields(self):
        source = ZhihuWebSigner.source(
            "https://www.zhihu.com/api/v4/search_v3?q=%E5%92%96%E5%95%A1&offset=0",
            d_c0="dc0-value",
            body="a=1&b=2",
            x_zst_81="zst-value",
        )
        self.assertEqual(
            source,
            "101_3_3.0+/api/v4/search_v3?q=%E5%92%96%E5%95%A1&offset=0+dc0-value+a=1&b=2+zst-value",
        )

    def test_body_over_4096_bytes_is_excluded(self):
        source = ZhihuWebSigner.source("https://www.zhihu.com/api", d_c0="d", body="x" * 4097)
        self.assertEqual(source, "101_3_3.0+/api+d")

    def test_injected_encryptor_returns_versioned_header_and_source(self):
        seen = []

        def encryptor(value):
            seen.append(value)
            return "encrypted"

        signer = ZhihuWebSigner(encryptor=encryptor)
        value, source = signer.sign("https://www.zhihu.com/api?q=1", d_c0="d", body="x")
        self.assertEqual(value, "2.0_encrypted")
        self.assertEqual(source, "101_3_3.0+/api?q=1+d+x")
        self.assertEqual(seen, [hashlib.md5(source.encode()).hexdigest()])
        self.assertEqual(signer.headers("https://www.zhihu.com/api", d_c0="d")["x-zse-93"], ZSE93)


if __name__ == "__main__":
    unittest.main()
