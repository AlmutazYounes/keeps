import socket
import tempfile
import unittest
from pathlib import Path

import server


class ThumbRequestTest(unittest.TestCase):
    def test_open_socket_is_still_connected(self):
        left, right = socket.socketpair()
        try:
            self.assertFalse(server.client_gone(left))
        finally:
            left.close()
            right.close()

    def test_closed_socket_counts_as_gone(self):
        left, right = socket.socketpair()
        right.close()
        try:
            self.assertTrue(server.client_gone(left))
        finally:
            left.close()

    def test_missing_socket_counts_as_gone(self):
        self.assertTrue(server.client_gone(None))

    def test_leaves_the_original_alone_when_the_browser_left(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "1.jpg"
            photo = {"id": 1, "rel": "2024/01-January/one.jpg", "kind": "image"}
            self.assertIsNone(server.ensure_jpeg(photo, dest, 480, still=lambda: False))
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
