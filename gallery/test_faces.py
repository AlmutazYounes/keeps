import tempfile
import unittest
from pathlib import Path

import faces_db


class FacePageTests(unittest.TestCase):
    def test_the_face_card_can_rename_in_place(self):
        html = (Path(__file__).parent / "static" / "faces.html").read_text()
        self.assertIn('aria-label="Rename"', html)
        self.assertIn('href="/?person=', html)
        self.assertIn('"/api/people/" + id', html)
        self.assertIn("Escape", html)
        self.assertIn("Unnamed", html)
        self.assertNotIn("\u2014", html)


class FaceNameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.old_db = faces_db.DB_PATH
        self.old_meta = faces_db.META_PATH
        faces_db.DB_PATH = root / "faces.sqlite"
        faces_db.META_PATH = root / "image_faces.json"
        conn = faces_db.connect()
        conn.execute("INSERT INTO people(id, name) VALUES (1, 'Sam'), (2, '')")
        conn.execute(
            """
            INSERT INTO faces(id, relpath, x1, y1, x2, y2, score, person_id)
            VALUES (1, 'a.jpg', 0, 0, 1, 1, 1, 1),
                   (2, 'b.jpg', 0, 0, 1, 1, 1, 2)
            """
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        faces_db.DB_PATH = self.old_db
        faces_db.META_PATH = self.old_meta
        self.tmp.cleanup()

    def test_the_same_name_merges_and_an_empty_name_clears(self):
        merged = faces_db.set_name(2, "  Sam  ")
        self.assertEqual(merged, 1)
        conn = faces_db.connect()
        try:
            people = conn.execute("SELECT id, name FROM people ORDER BY id").fetchall()
            owners = conn.execute("SELECT id, person_id FROM faces ORDER BY id").fetchall()
        finally:
            conn.close()
        self.assertEqual(people, [(1, "Sam")])
        self.assertEqual(owners, [(1, 1), (2, 1)])
        self.assertIsNone(faces_db.set_name(1, "   "))
        conn = faces_db.connect()
        try:
            name = conn.execute("SELECT name FROM people WHERE id = 1").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(name, "")


if __name__ == "__main__":
    unittest.main()
