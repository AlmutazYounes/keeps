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

    def test_categories_map_asks_for_the_carto_key(self):
        html = (server.APP / "static" / "categories.html").read_text(encoding="utf-8")
        self.assertIn('style = dark ? "dark_all" : "rastertiles/voyager"', html)
        self.assertIn("/{z}/{x}/{y}{r}.png?key=%%CARTO_KEY%%", html)
        body = server.categories_page().decode()
        key = server.read_carto_key()
        self.assertTrue(key)
        self.assertNotIn("%%CARTO_KEY%%", body)
        self.assertIn("png?key=" + key, body)

    def test_categories_page_inserts_the_carto_key(self):
        with tempfile.TemporaryDirectory() as folder:
            page = Path(folder) / "categories.html"
            key = Path(folder) / "carto.key"
            page.write_text("tiles?key=%%CARTO_KEY%%", encoding="utf-8")
            key.write_text("abc\n", encoding="utf-8")
            body = server.categories_page(page, key).decode()
        self.assertEqual(body, "tiles?key=abc")

    def test_categories_page_omits_a_missing_carto_key(self):
        with tempfile.TemporaryDirectory() as folder:
            page = Path(folder) / "categories.html"
            missing = Path(folder) / "carto.key"
            page.write_text("tiles?key=%%CARTO_KEY%%", encoding="utf-8")
            body = server.categories_page(page, missing).decode()
        self.assertEqual(body, "tiles?key=")

    def test_leaves_the_original_alone_when_the_browser_left(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "1.jpg"
            photo = {"id": 1, "rel": "2024/01-January/one.jpg", "kind": "image"}
            self.assertIsNone(server.ensure_jpeg(photo, dest, 480, still=lambda: False))
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
