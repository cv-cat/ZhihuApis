import hashlib
import unittest

from apis.zhihu_zse_pure import encrypt_md5_hex, encrypt_source, sm4_encrypt_block


class ZhihuPureZseTests(unittest.TestCase):
    SOURCE = "101_3_3.0+/api/v4/search_v3?t=general&q=%E5%92%96%E5%95%A1&offset=0&limit=5&search_source=Normal+d_c0_TEST"
    DIGEST = "a986d432e6481ddfa4e30c4050cf6f02"
    # Captured from the checked-in static/zhihu.js with Math.random() fixed
    # to 0.1 before module 1514 initialisation.  This makes the random first
    # byte reproducible while retaining the browser's exact 68-char output.
    EXPECTED = "Htjgpc=l6=RH0hZ5NBGy9qbYMBnswsV9cO7WAu/uOHCNcRrTcB0DarvLzA2QAf=e"

    def test_source_digest_and_fixed_random_vector(self):
        self.assertEqual(hashlib.md5(self.SOURCE.encode()).hexdigest(), self.DIGEST)
        self.assertEqual(encrypt_source(self.SOURCE, random_value=0.1), self.EXPECTED)
        self.assertEqual(encrypt_md5_hex(self.DIGEST, random_value=0.1), self.EXPECTED)

    def test_sm4_block_is_16_bytes(self):
        self.assertEqual(len(sm4_encrypt_block(bytes(16))), 16)

    def test_random_nonce_changes_signature(self):
        first = encrypt_source(self.SOURCE, random_value=0.1)
        second = encrypt_source(self.SOURCE, random_value=0.2)
        self.assertEqual(len(first), 64)
        self.assertEqual(len(second), 64)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
