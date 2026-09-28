import struct
import tempfile
import unittest
import zlib
from pathlib import Path

import edits


def write_png(path, width, height):
    raw = b"".join(b"\x00" + bytes([255, 0, 0]) * width for _ in range(height))
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw))
    png += chunk(b"IEND", b"")
    Path(path).write_bytes(png)


class EditMathTests(unittest.TestCase):
    def test_degrees_keep_quarter_turns_and_a_small_tilt(self):
        self.assertEqual(edits.degrees_for(1, 2), 92)
        self.assertEqual(edits.degrees_for(4, 0), 0)
        self.assertEqual(edits.degrees_for(0, 40), 15)
        self.assertEqual(edits.degrees_for(0, -40), -15)

    def test_crop_box_uses_fractions_of_the_rotated_picture(self):
        top, left, height, width = edits.crop_box(100, 80, {"x": 0.1, "y": 0.25, "w": 0.5, "h": 0.5})
        self.assertEqual((top, left, height, width), (20, 10, 40, 50))
        with self.assertRaises(ValueError):
            edits.crop_box(100, 80, {"x": 0.8, "y": 0, "w": 0.5, "h": 0.2})

    def test_copy_name_skips_a_name_that_already_exists(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "day copy.jpg").write_bytes(b"x")
            self.assertEqual(edits.copy_name(root, "day.jpg"), "day copy 2.jpg")


class EditFileTests(unittest.TestCase):
    def test_rotate_writes_a_new_file_and_leaves_the_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            src = root / "shot.png"
            dest = root / "shot copy.png"
            write_png(src, 30, 10)
            before = src.read_bytes()
            edits.render_edit(src, dest, turns=1)
            self.assertEqual(src.read_bytes(), before)
            width, height = edits.pixel_size(dest)
            self.assertEqual((width, height), (10, 30))

    def test_crop_shrinks_the_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            src = root / "shot.png"
            dest = root / "shot copy.png"
            write_png(src, 40, 20)
            edits.render_edit(src, dest, crop={"x": 0, "y": 0, "w": 0.5, "h": 0.5})
            width, height = edits.pixel_size(dest)
            self.assertEqual((width, height), (20, 10))
            self.assertTrue(src.exists())


class ViewerPageTests(unittest.TestCase):
    def test_the_viewer_keeps_one_share_and_one_delete(self):
        html = (Path(__file__).parent / "static" / "index.html").read_text()
        self.assertEqual(html.count('id="lb-share"'), 1)
        self.assertEqual(html.count('id="lb-delete"'), 1)
        self.assertIn('id="lb-bar"', html)
        self.assertIn("Save a copy", html)
        self.assertIn("Add face", html)
        self.assertIn('"/api/edit"', html)
        self.assertIn('"/api/faces"', html)
        self.assertNotIn("\u2014", html)


if __name__ == "__main__":
    unittest.main()
