import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = (
    "index.html",
    "faces.html",
    "categories.html",
    "review.html",
    "settings.html",
)


class NameTests(unittest.TestCase):
    def test_every_page_uses_the_keeps_wordmark(self):
        static = ROOT / "gallery" / "static"
        for name in PAGES:
            html = (static / name).read_text()
            self.assertIn("Keeps</h1>", html, name)
            self.assertNotIn(">Photos</h1>", html, name)
            self.assertIn(">Photos</a>", html, name)

    def test_the_home_title_is_keeps(self):
        html = (ROOT / "gallery" / "static" / "index.html").read_text()
        self.assertIn("<title>Keeps</title>", html)

    def test_the_readme_and_repo_use_keeps(self):
        readme = (ROOT / "README.md").read_text()
        context = (ROOT / "docs" / "context.md").read_text()
        server = (ROOT / "gallery" / "server.py").read_text()
        self.assertTrue(readme.startswith("# Keeps\n"))
        self.assertIn("https://github.com/AlmutazYounes/keeps", context)
        self.assertIn("Keeps/1.0 (personal photo library)", server)
        self.assertNotIn("local-photos", context)
        self.assertNotIn("LocalPhotos", server)


if __name__ == "__main__":
    unittest.main()
