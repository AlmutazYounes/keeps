import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import library_root


class LibraryRootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_config = library_root.CONFIG
        library_root.CONFIG = Path(self.tmp.name) / "library.json"

    def tearDown(self):
        library_root.CONFIG = self.old_config
        self.tmp.cleanup()

    def test_the_default_is_the_folder_keeps_lives_in(self):
        self.assertEqual(library_root.library_root(), library_root.code_root())
        view = library_root.describe(library_root.code_root())
        self.assertFalse(view["custom"])
        self.assertFalse(view["restart"])
        self.assertFalse(view["missing"])
        self.assertEqual(view["active"], str(library_root.code_root()))

    def test_a_saved_folder_is_used_on_the_next_read(self):
        chosen = Path(self.tmp.name) / "library"
        chosen.mkdir()
        (chosen / "Photos").mkdir()
        library_root.save_root(chosen)
        self.assertEqual(library_root.library_root(), chosen.resolve())
        view = library_root.describe(library_root.code_root())
        self.assertTrue(view["custom"])
        self.assertTrue(view["restart"])
        self.assertTrue(view["photos"])
        self.assertEqual(view["saved"], str(chosen.resolve()))

    def test_a_missing_folder_falls_back_to_the_program_folder(self):
        gone = Path(self.tmp.name) / "gone"
        library_root.CONFIG.write_text(json.dumps({"root": str(gone)}))
        self.assertEqual(library_root.library_root(), library_root.code_root())
        view = library_root.describe(library_root.code_root())
        self.assertTrue(view["missing"])
        self.assertFalse(view["custom"])

    def test_a_file_is_not_a_library_folder(self):
        file_path = Path(self.tmp.name) / "notes.txt"
        file_path.write_text("nope")
        with self.assertRaises(ValueError):
            library_root.save_root(file_path)

    def test_choose_folder_saves_the_dialog_result(self):
        chosen = Path(self.tmp.name) / "picked"
        chosen.mkdir()

        class Done:
            returncode = 0
            stdout = str(chosen) + "\n"

        with patch("library_root.subprocess.run", return_value=Done()):
            saved = library_root.choose_folder()
        self.assertEqual(saved, chosen.resolve())
        self.assertEqual(library_root.library_root(), chosen.resolve())

    def test_a_cancelled_dialog_does_not_change_the_folder(self):
        class Done:
            returncode = 1
            stdout = ""

        with patch("library_root.subprocess.run", return_value=Done()):
            with self.assertRaises(ValueError):
                library_root.choose_folder()
        self.assertFalse(library_root.CONFIG.is_file())

    def test_settings_explains_each_library_folder_state(self):
        html = (Path(__file__).resolve().parent / "static" / "settings.html").read_text()
        for sentence in (
            "Reading the library folder.",
            "Could not read the library folder.",
            "This is the folder Keeps lives in.",
            "No Photos folder there yet.",
            "That folder is missing. Keeps is using the folder it lives in.",
            "Keeps cannot read that folder.",
            "Saving the folder.",
            "Saved. Start Keeps again to open this folder.",
            "Saved. This run is already using that folder.",
        ):
            self.assertIn(sentence, html)
        self.assertIn('"/api/library-root"', html)

    def test_the_drive_path_is_not_in_the_published_files(self):
        root = Path(__file__).resolve().parents[1]
        for rel in (
            "README.md",
            "docs/guide.md",
            "gallery/server.py",
            "gallery/library_root.py",
            "sort_photos.py",
        ):
            self.assertNotIn("SamsungT7", (root / rel).read_text(), rel)
