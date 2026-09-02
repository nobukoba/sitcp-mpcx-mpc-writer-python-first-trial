import unittest

from sitcp_mpc_writer.rbcp import RbcpClient


class TestRbcpHeader(unittest.TestCase):
    def test_read_header(self):
        c = RbcpClient("127.0.0.1")
        h = c._header(c.CMD_READ, 0x12345678, 4, 7)
        self.assertEqual(h, bytes.fromhex("ff c0 07 04 12 34 56 78"))

    def test_write_header(self):
        c = RbcpClient("127.0.0.1")
        h = c._header(c.CMD_WRITE, 0x89ABCDEF, 2, 1)
        self.assertEqual(h, bytes.fromhex("ff 80 01 02 89 ab cd ef"))


if __name__ == "__main__":
    unittest.main()
