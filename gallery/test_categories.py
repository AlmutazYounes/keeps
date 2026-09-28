import unittest

import categories


class CategoryTest(unittest.TestCase):
    def test_empty_caption_is_not_a_category(self):
        self.assertEqual(categories.kinds_for("Screenshot.png", ""), [])

    def test_screenshot_and_document_can_both_apply(self):
        text = "A screenshot of a receipt on a phone."
        self.assertEqual(categories.kinds_for("shot.png", text), ["screenshot"])
        paper = "A receipt is on the table."
        self.assertEqual(categories.kinds_for("scan.jpg", paper), ["document"])

    def test_filename_screenshot_needs_a_caption(self):
        self.assertEqual(
            categories.kinds_for("Screenshot_1.png", "A menu of food."),
            ["screenshot"],
        )

    def test_place_uses_a_saved_name_and_not_a_guess(self):
        names = {"42.654,-73.775": "Albany, NY"}
        self.assertEqual(categories.place_label(42.6541, -73.7752, names), "Albany, NY")
        self.assertEqual(categories.place_label(1, 2, {}), "1.000, 2.000")
        self.assertEqual(categories.search_names("1.000, 2.000"), [])
        self.assertIn("Albany", categories.search_names("Albany, NY"))

    def test_place_match_accepts_the_city(self):
        self.assertTrue(categories.place_matches("Albany, NY", "Albany"))
        self.assertFalse(categories.place_matches("", "Albany"))

    def test_mdls_pairs_keep_order(self):
        text = """
kMDItemLatitude  = 42.65
kMDItemLongitude = -73.77
kMDItemLatitude  = (null)
kMDItemLongitude = (null)
"""
        self.assertEqual(categories.parse_mdls(text), [(42.65, -73.77), (None, None)])


if __name__ == "__main__":
    unittest.main()
