import tempfile
import unittest
from pathlib import Path

import captions_db
import faces_db
import jobs_db
import server


class SyncControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.old = {
            "jobs": jobs_db.DB_PATH,
            "faces": faces_db.DB_PATH,
            "meta": faces_db.META_PATH,
            "captions": captions_db.DB_PATH,
            "popen": server.subprocess.Popen,
            "running": server.script_running,
            "stop": server.stop_indexer,
            "venv": server.VENV_PYTHON,
            "counts": server.job_counts,
            "ready": server.LIBRARY["ready"],
        }
        jobs_db.DB_PATH = root / "jobs.sqlite"
        faces_db.DB_PATH = root / "faces.sqlite"
        faces_db.META_PATH = root / "image_faces.json"
        captions_db.DB_PATH = root / "captions.sqlite"
        self.started = []
        server.subprocess.Popen = lambda *args, **kwargs: self.started.append(args)
        server.script_running = lambda script: False
        server.stop_indexer = lambda script: True
        server.VENV_PYTHON = root / "python"
        server.VENV_PYTHON.write_text("x", encoding="utf-8")
        server.job_counts = lambda name: (1, 4, 5)
        server.LIBRARY["ready"] = True

    def tearDown(self):
        jobs_db.DB_PATH = self.old["jobs"]
        faces_db.DB_PATH = self.old["faces"]
        faces_db.META_PATH = self.old["meta"]
        captions_db.DB_PATH = self.old["captions"]
        server.subprocess.Popen = self.old["popen"]
        server.script_running = self.old["running"]
        server.stop_indexer = self.old["stop"]
        server.VENV_PYTHON = self.old["venv"]
        server.job_counts = self.old["counts"]
        server.LIBRARY["ready"] = self.old["ready"]
        self.tmp.cleanup()

    def test_pause_is_kept_and_a_progress_beat_cannot_clear_it(self):
        server.control_sync("captions", "pause")
        jobs_db.beat("captions", "still working")
        row = jobs_db.read("captions")
        view = server.job_view("captions")
        self.assertEqual(row["state"], "paused")
        self.assertEqual(view["label"], "Paused")
        self.assertTrue(view["paused"])
        self.assertFalse(view["running"])
        self.assertEqual(self.started, [])

    def test_continue_starts_only_the_photos_that_are_left(self):
        jobs_db.beat("faces", "Paused.", state="paused")
        server.control_sync("faces", "continue")
        self.assertEqual(len(self.started), 1)
        self.assertIn("index_faces.py", self.started[0][0])
        self.assertEqual(jobs_db.read("faces")["state"], "running")

    def test_continue_does_not_start_a_finished_job(self):
        jobs_db.beat("faces", "Paused.", state="paused")
        server.job_counts = lambda name: (5, 0, 5)
        server.control_sync("faces", "continue")
        self.assertEqual(self.started, [])
        self.assertEqual(jobs_db.read("faces")["state"], "idle")

    def test_a_paused_job_is_not_started_on_resume(self):
        jobs_db.beat("captions", "Paused.", state="paused")
        jobs_db.beat("faces", "done", state="idle")
        server.resume_jobs()
        scripts = [args[0] for args in self.started]
        self.assertEqual(scripts, [[str(server.VENV_PYTHON), "-u", "index_faces.py"]])

    def test_rewrite_clears_the_face_database_and_starts_again(self):
        conn = faces_db.connect()
        conn.execute("INSERT INTO people(id, name) VALUES (1, 'Sam')")
        conn.execute(
            """
            INSERT INTO faces(relpath, x1, y1, x2, y2, score, person_id)
            VALUES ('a.jpg', 0, 0, 1, 1, 1, 1)
            """
        )
        conn.execute("INSERT INTO scanned(relpath) VALUES ('a.jpg')")
        conn.commit()
        conn.close()
        server.control_sync("faces", "rewrite")
        conn = faces_db.connect()
        people = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
        faces = conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
        scanned = conn.execute("SELECT COUNT(*) FROM scanned").fetchone()[0]
        conn.close()
        self.assertEqual((people, faces, scanned), (0, 0, 0))
        self.assertIn("index_faces.py", self.started[0][0])

    def test_rewrite_clears_saved_descriptions(self):
        conn = captions_db.connect()
        conn.execute(
            "INSERT INTO captions(relpath, caption, mtime, ok) VALUES ('a.jpg', 'A dog.', 1, 1)"
        )
        conn.commit()
        conn.close()
        server.control_sync("captions", "rewrite")
        self.assertEqual(captions_db.saved_times(), {})
        self.assertIn("index_captions.py", self.started[0][0])

    def test_settings_offers_pause_continue_and_rewrite(self):
        html = (Path(__file__).parent / "static" / "settings.html").read_text()
        self.assertIn('data-action="pause"', html)
        self.assertIn('data-action="continue"', html)
        self.assertIn('data-action="rewrite"', html)
        self.assertIn('"/api/sync"', html)
        self.assertIn("Rewrite faces? This clears saved faces and the names you typed", html)
        self.assertIn("Rewrite descriptions? This clears the saved sentences", html)
        self.assertNotIn("\u2014", html)


if __name__ == "__main__":
    unittest.main()
