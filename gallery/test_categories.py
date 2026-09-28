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
            categories.kinds_for("Screenshot_1.png", "A phone menu."),
            ["screenshot"],
        )

    def test_new_kinds_need_a_caption_and_can_overlap(self):
        self.assertEqual(categories.kinds_for("dog.jpg", ""), [])
        self.assertEqual(
            categories.kinds_for("pet.jpg", "A dog sits in a car."),
            ["animal", "vehicle"],
        )
        self.assertEqual(categories.kinds_for("seat.jpg", "A child is in a car seat."), [])
        self.assertEqual(categories.kinds_for("lunch.jpg", "A hot dog is on a plate."), ["food"])
        self.assertIn("nature", categories.kinds_for("view.jpg", "A beach at sunset."))
        self.assertIn("food", categories.kinds_for("menu.png", "A screenshot of a menu of food."))

    def test_map_groups_coordinates_and_picks_the_nearest(self):
        points = categories.map_points([
            (42.6541, -73.7752, "Albany, NY"),
            (42.6544, -73.7754, "42.654, -73.775"),
            (32.538, 35.834, "32.538, 35.834"),
        ])
        albany = next(point for point in points if point["label"] == "Albany, NY")
        self.assertEqual(albany["count"], 2)
        picked = categories.nearest_place(points, 42.66, -73.77, limit_km=40)
        self.assertEqual(picked["label"], "Albany, NY")
        self.assertIsNone(categories.nearest_place(points, 0, 0, limit_km=40))

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
