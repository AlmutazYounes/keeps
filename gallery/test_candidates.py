import unittest

import candidates


class CandidateTest(unittest.TestCase):
    def test_screenshot_without_a_face(self):
        self.assertEqual(
            candidates.reason_for("IMG.jpg", "A screenshot of a menu.", False),
            "Screenshot",
        )

    def test_missing_caption_is_not_junk(self):
        self.assertEqual(candidates.reason_for("Screenshot.png", "", False), "")

    def test_a_face_is_kept(self):
        self.assertEqual(
            candidates.reason_for("IMG.jpg", "A screenshot of a menu.", True),
            "",
        )

    def test_blurry_person_is_kept(self):
        self.assertEqual(
            candidates.reason_for("IMG.jpg", "A blurry image of a person's face.", False),
            "",
        )

    def test_blurry_surface_is_a_candidate(self):
        self.assertEqual(
            candidates.reason_for("IMG.jpg", "A blurry image of a white surface.", False),
            "Blurry",
        )

    def test_document_phrase(self):
        self.assertEqual(
            candidates.reason_for("scan.jpg", "A receipt is on the table.", False),
            "Document",
        )

    def test_paper_in_a_scene_is_kept(self):
        text = "A bunch of lockers are lined up. There is a piece of paper on the lockers."
        self.assertEqual(candidates.reason_for("lockers.jpg", text, False), "")


if __name__ == "__main__":
    unittest.main()
