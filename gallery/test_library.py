import tempfile
import unittest
from pathlib import Path

import library_actions


class LibraryActionsTest(unittest.TestCase):
    def test_photo_file_stays_inside_the_library(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            photo = root / "2025" / "09-September" / "one.jpg"
            photo.parent.mkdir(parents=True)
            photo.write_bytes(b"jpg")
            found = library_actions.photo_file(root, "2025/09-September/one.jpg")
            self.assertEqual(found, photo.resolve())

    def test_photo_file_rejects_a_path_outside_the_library(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root.mkdir(exist_ok=True)
            with self.assertRaises(ValueError):
                library_actions.photo_file(root, "../secret.jpg")

    def test_missing_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                library_actions.photo_file(folder, "gone.jpg")

    def test_drop_photos_removes_ids_and_empty_groups(self):
        library = {
            "count": 2,
            "by_id": {
                1: {"id": 1, "rel": "a.jpg"},
                2: {"id": 2, "rel": "b.jpg"},
            },
            "groups": [
                {"label": "Fri, Sep 25", "items": [[1, "a.jpg", "image", "2025-09-25"]]},
                {"label": "Thu, Sep 24", "items": [[2, "b.jpg", "image", "2025-09-24"]]},
            ],
        }
        removed = library_actions.drop_photos(library, [1, "nope", 1])
        self.assertEqual([photo["id"] for photo in removed], [1])
        self.assertEqual(list(library["by_id"]), [2])
        self.assertEqual(len(library["groups"]), 1)
        self.assertEqual(library["groups"][0]["items"][0][0], 2)
        self.assertEqual(library["count"], 1)


if __name__ == "__main__":
    unittest.main()
