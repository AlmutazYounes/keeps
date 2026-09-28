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
        self.assertIn("## What this is\n\nA private gallery for a Google Photos takeout.", readme)
        self.assertIn("## Who it is for", readme)
        self.assertIn("## Install", readme)
        self.assertIn("## Use", readme)
        self.assertNotIn("img.shields.io", readme)
        for name in ("logo.png", "home.png", "faces.png", "settings.png"):
            self.assertIn(f"docs/images/{name}", readme)
        self.assertIn("https://github.com/AlmutazYounes/keeps", context)
        self.assertIn("Keeps/1.0 (personal photo library)", server)
        self.assertNotIn("local-photos", context)
        self.assertNotIn("LocalPhotos", server)

    def test_the_changelog_has_an_unreleased_entry(self):
        changelog = (ROOT / "CHANGELOG.md").read_text()
        self.assertTrue(changelog.startswith("# Changelog\n"))
        self.assertIn("## Unreleased", changelog)


if __name__ == "__main__":
    unittest.main()
