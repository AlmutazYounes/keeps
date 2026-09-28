import tempfile
import unittest
from pathlib import Path

import model_choices


class ModelChoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.old_models = model_choices.MODELS
        self.old_choices = model_choices.CHOICES
        model_choices.MODELS = root / "models"
        model_choices.CHOICES = root / "jobs" / "model_choices.json"
        models = model_choices.MODELS
        (models / "10g_bnkps.onnx").parent.mkdir(parents=True)
        (models / "10g_bnkps.onnx").write_bytes(b"det")
        (models / "arcface_w600k_r50_batch.onnx").write_bytes(b"rec")
        for name in ("florence2", "other-caption"):
            folder = models / name
            (folder / "onnx").mkdir(parents=True)
            (folder / "tokenizer.json").write_text("{}", encoding="utf-8")
            for rel in model_choices.CAPTION_FILES:
                if rel == "tokenizer.json":
                    continue
                (folder / rel).write_bytes(b"onnx")

    def tearDown(self):
        model_choices.MODELS = self.old_models
        model_choices.CHOICES = self.old_choices
        self.tmp.cleanup()

    def test_the_installed_models_are_the_choices(self):
        roles = {role["id"]: role for role in model_choices.view()}
        self.assertEqual(roles["faces_detect"]["selected"], "10g_bnkps")
        self.assertEqual(roles["faces_embed"]["selected"], "arcface_w600k_r50")
        self.assertEqual(
            [option["id"] for option in roles["captions"]["options"]],
            ["florence2", "other-caption"],
        )
        self.assertEqual(model_choices.model_file("faces_detect").name, "10g_bnkps.onnx")
        self.assertEqual(model_choices.caption_dir().name, "florence2")

    def test_a_saved_caption_model_is_the_one_the_job_loads(self):
        model_choices.save_choices({
            "faces_detect": "10g_bnkps",
            "faces_embed": "arcface_w600k_r50",
            "captions": "other-caption",
        })
        self.assertEqual(model_choices.caption_dir().name, "other-caption")

    def test_a_missing_model_cannot_be_saved(self):
        with self.assertRaises(ValueError):
            model_choices.save_choices({"faces_detect": "missing"})

    def test_settings_lists_each_model_job(self):
        html = (Path(__file__).parent / "static" / "settings.html").read_text()
        self.assertIn(">Models</h2>", html)
        self.assertIn('"/api/models"', html)
        self.assertIn("The next start uses these models.", html)
        self.assertNotIn("\u2014", html)


if __name__ == "__main__":
    unittest.main()
