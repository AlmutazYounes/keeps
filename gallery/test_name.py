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
        server = (ROOT / "gallery" / "server.py").read_text()
        self.assertTrue(readme.startswith("# Keeps\n\nA private gallery for a Google Photos takeout.\n"))
        self.assertIn("## What it does", readme)
        self.assertIn("## Install", readme)
        self.assertIn("## Example", readme)
        self.assertIn("python3 gallery/server.py", readme)
        self.assertIn("Scanning library...", readme)
        self.assertIn("Open http://127.0.0.1:8765", readme)
        self.assertNotIn("img.shields.io", readme)
        self.assertIn("Keeps/1.0 (personal photo library)", server)
        self.assertNotIn("LocalPhotos", server)

    def test_local_notes_are_ignored(self):
        ignore = (ROOT / ".gitignore").read_text()
        for path in (
            "docs/context.md",
            "docs/story.md",
            "docs/decisions",
            "AGENTS.md",
            ".cursor",
        ):
            self.assertIn(path, ignore.splitlines())

    def test_the_license_is_mit(self):
        readme = (ROOT / "README.md").read_text()
        license_text = (ROOT / "LICENSE").read_text()
        self.assertIn("## License", readme)
        self.assertIn("[MIT](LICENSE)", readme)
        self.assertIn("MIT License", license_text)
        self.assertIn("Copyright (c) 2026 Motaz Younes", license_text)

    def test_the_changelog_names_0_1_0(self):
        changelog = (ROOT / "CHANGELOG.md").read_text()
        self.assertTrue(changelog.startswith("# Changelog\n"))
        self.assertIn("## 0.1.0", changelog)
        self.assertIn("2026-09-28", changelog)


if __name__ == "__main__":
    unittest.main()
