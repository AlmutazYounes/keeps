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

    def test_add_photo_keeps_existing_ids(self):
        library = {
            "count": 1,
            "by_id": {5: {"id": 5, "name": "old.jpg"}},
            "groups": [{"year": "2024", "month": "07-July", "label": "July 2024", "items": [[5, "old.jpg", "image", ""]]}],
        }
        added = library_actions.add_photo(library, {
            "name": "new.jpg",
            "kind": "image",
            "date": "2024-07-02",
            "year": "2024",
            "month": "07-July",
        })
        self.assertEqual(added["id"], 6)
        self.assertEqual(library["by_id"][5]["name"], "old.jpg")
        self.assertEqual(library["groups"][0]["items"][0][0], 6)
        self.assertEqual(library["count"], 2)


if __name__ == "__main__":
    unittest.main()
