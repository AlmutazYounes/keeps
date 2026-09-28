import unittest
from pathlib import Path


PAGES = (
    "index.html",
    "faces.html",
    "categories.html",
    "review.html",
    "settings.html",
)

MARK = """<rect x="2" y="2" width="16" height="16" rx="3.5" fill="#e53935"></rect>
      <rect x="8" y="8" width="16" height="16" rx="3.5" fill="#1a73e8"></rect>
      <rect x="14" y="14" width="16" height="16" rx="3.5" fill="#f9ab00"></rect>"""


class LogoTest(unittest.TestCase):
    def test_pages_use_the_stacked_squares(self):
        root = Path(__file__).parent / "static"
        for name in PAGES:
            html = (root / name).read_text()
            self.assertIn(MARK, html, name)
            self.assertNotIn("<polygon", html, name)


if __name__ == "__main__":
    unittest.main()
