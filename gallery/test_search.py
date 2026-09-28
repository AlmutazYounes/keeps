"""Parser and matcher tests. Fixtures stand in for saved people and captions."""

import unittest
from pathlib import Path

import search_lib

PEOPLE = [
    {"name": "Me", "ids": [1, 2]},
    {"name": "Yara", "ids": [3, 10]},
    {"name": "Haneen", "ids": [4]},
    {"name": "Omar Hamaza", "ids": [11]},
    {"name": "Omar Hamza", "ids": [5]},
    {"name": "Hamza", "ids": [6]},
]

IDS = {
    "me": {1, 2},
    "yara": {3, 10},
    "haneen": {4},
    "omar hamaza": {11},
    "omar hamza": {5},
    "hamza": {6},
}

CAPTIONS = {
    1: "A person is wearing a yellow dress.",
    2: "A person is wearing a yellow dress.",
    3: "A baby is sitting in a car seat.",
    10: "A baby is sleeping in a car seat.",
}

GROUPS = [
    {
        "year": "2025",
        "month": "06-June",
        "label": "June 2025",
        "items": [
            [1, "IMG_1.jpg", "image", "2025-06-02"],
            [2, "IMG_2.jpg", "image", "2024-01-09"],
            [3, "baby.jpg", "image", "2025-06-02"],
            [7, "VID_20141030.mp4", "video", "2025-06-02"],
            [8, "yara-carseat.mp4", "video", "2025-06-02"],
            [9, "clip.mp4", "video", "2025-06-02"],
            [10, "nap.mp4", "video", ""],
            [12, "scan.heic", "convert", "2025-09-25"],
        ],
    }
]


def parsed(text, people=None):
    return search_lib.parse_query(text, PEOPLE if people is None else people)


def hits(text, people=None):
    filters = parsed(text, people)
    groups = search_lib.filter_groups(GROUPS, filters, CAPTIONS, IDS)
    return [item[0] for group in groups for item in group["items"]]


class ParseTests(unittest.TestCase):
    def test_person_content_and_video(self):
        filters = parsed("yara in a carseat video")
        self.assertEqual(filters["person"], "Yara")
        self.assertEqual(filters["people"], ["Yara"])
        self.assertEqual(filters["kind"], "video")
        self.assertEqual(filters["words"], ["carseat"])
        self.assertIsNone(filters["year"])

    def test_wearing_is_not_a_content_word(self):
        filters = parsed("me wearing yellow")
        self.assertEqual(filters["person"], "Me")
        self.assertEqual(filters["words"], ["yellow"])
        self.assertNotIn("wearing", filters["words"])

    def test_person_and_year(self):
        filters = parsed("me in 2025")
        self.assertEqual(filters["person"], "Me")
        self.assertEqual(filters["year"], 2025)
        self.assertEqual(filters["words"], [])
        self.assertEqual(filters["kind"], "")

    def test_name_case_and_pronoun(self):
        self.assertEqual(parsed("ME WEARING YELLOW")["person"], "Me")
        self.assertEqual(parsed("meeting yara")["person"], "Yara")
        self.assertEqual(parsed("meeting yara")["words"], ["meeting"])
        unnamed = parsed("me wearing yellow", [{"name": "Yara"}])
        self.assertEqual(unnamed["person"], "")
        self.assertEqual(unnamed["words"], ["yellow"])

    def test_longest_saved_name_wins(self):
        filters = parsed("omar hamza in 2024")
        self.assertEqual(filters["people"], ["Omar Hamza"])
        self.assertEqual(filters["year"], 2024)
        self.assertEqual(filters["words"], [])
        both = parsed("omar hamza and hamza")
        self.assertEqual(both["people"], ["Omar Hamza", "Hamza"])

    def test_category_and_place_queries(self):
        shots = search_lib.parse_query("screenshots from 2024")
        self.assertEqual(shots["category"], "screenshot")
        self.assertEqual(shots["year"], 2024)
        self.assertEqual(shots["words"], [])
        docs = search_lib.parse_query("documents in 2025")
        self.assertEqual(docs["category"], "document")
        self.assertEqual(docs["year"], 2025)
        self.assertEqual(docs["words"], [])
        animals = search_lib.parse_query("animals in 2024")
        self.assertEqual(animals["category"], "animal")
        self.assertEqual(animals["year"], 2024)
        self.assertEqual(animals["words"], [])
        food = search_lib.parse_query("food in 2025")
        self.assertEqual(food["category"], "food")
        self.assertEqual(food["year"], 2025)
        placed = search_lib.parse_query("albany 2024", places=["Albany, NY"])
        self.assertEqual(placed["place"], "Albany, NY")
        self.assertEqual(placed["year"], 2024)
        self.assertEqual(placed["words"], [])

    def test_category_and_place_filters(self):
        item = [1, "map.jpg", "image", "2024-06-01"]
        self.assertTrue(search_lib.item_matches(
            item,
            {"category": "screenshot", "year": 2024},
            kinds=["screenshot"],
        ))
        self.assertFalse(search_lib.item_matches(
            item,
            {"category": "screenshot"},
            kinds=[],
        ))
        self.assertTrue(search_lib.item_matches(
            [2, "page.jpg", "image", "2025-01-02"],
            {"category": "document", "year": 2025, "place": "Albany, NY"},
            kinds=["document"],
            place="Albany, NY",
        ))
        self.assertFalse(search_lib.item_matches(
            [2, "page.jpg", "image", "2025-01-02"],
            {"place": "Albany, NY"},
            place="",
        ))

    def test_month_and_year_in_any_order(self):
        people = [{"name": "Me", "ids": [1]}]
        for text in ("me 2025 july", "july me 2025", "me july 2025", "2025 july me"):
            filters = search_lib.parse_query(text, people)
            self.assertEqual(filters["person"], "Me", text)
            self.assertEqual((filters["year"], filters["month"], filters["day"]), (2025, 7, None), text)
            self.assertEqual(filters["words"], [], text)
        month_only = search_lib.parse_query("july", people)
        self.assertEqual(month_only["month"], 7)
        self.assertIsNone(month_only["year"])
        day = search_lib.parse_query("2025 july 4", people)
        self.assertEqual((day["year"], day["month"], day["day"]), (2025, 7, 4))

    def test_month_and_day(self):
        month = parsed("September 2025")
        self.assertEqual((month["year"], month["month"], month["day"]), (2025, 9, None))
        day = parsed("Sep 25, 2025")
        self.assertEqual((day["year"], day["month"], day["day"]), (2025, 9, 25))
        spoken = parsed("25 September 2025")
        self.assertEqual((spoken["year"], spoken["month"], spoken["day"]), (2025, 9, 25))

    def test_year_phrases_and_bounds(self):
        self.assertEqual(parsed("from 2024")["year"], 2024)
        self.assertEqual(parsed("during 2009")["year"], 2009)
        self.assertEqual(parsed("in 2026")["year"], 2026)
        early = parsed("in 2008")
        self.assertIsNone(early["year"])
        self.assertEqual(early["words"], ["2008"])
        late = parsed("in 2027")
        self.assertIsNone(late["year"])
        self.assertEqual(late["words"], ["2027"])

    def test_invalid_day_keeps_the_year(self):
        filters = parsed("Sep 31, 2025")
        self.assertEqual(filters["year"], 2025)
        self.assertIsNone(filters["day"])

    def test_media_words(self):
        self.assertEqual(parsed("pictures of yellow")["kind"], "photo")
        self.assertEqual(parsed("pictures of yellow")["words"], ["yellow"])
        self.assertEqual(parsed("videos that are photos")["kind"], "photo")
        self.assertEqual(parsed("photos that are videos")["kind"], "video")

    def test_empty_query(self):
        filters = parsed("")
        self.assertEqual(filters["person"], "")
        self.assertIsNone(filters["year"])
        self.assertEqual(filters["words"], [])


class MatchTests(unittest.TestCase):
    def test_examples_against_fixtures(self):
        self.assertEqual(hits("me wearing yellow"), [1, 2])
        self.assertEqual(hits("me in 2025"), [1])
        self.assertEqual(hits("yara in a carseat video"), [8, 10])
        self.assertNotIn(3, hits("yara in a carseat video"))
        self.assertNotIn(7, hits("yara in a carseat video"))
        self.assertNotIn(9, hits("yara in a carseat video"))

    def test_carseat_spacing_and_filename(self):
        filters = parsed("carseat")
        self.assertTrue(search_lib.item_matches(
            [3, "baby.jpg", "image", "2025-06-02"],
            filters,
            caption="A baby is sitting in a car seat.",
        ))
        self.assertTrue(search_lib.item_matches(
            [8, "CAR_SEAT.JPG", "image", "2025-06-02"],
            filters,
            caption="",
        ))
        self.assertFalse(search_lib.item_matches(
            [7, "VID_20141030.mp4", "video", "2025-06-02"],
            filters,
            caption="",
        ))

    def test_photo_query_skips_videos_and_keeps_stills(self):
        found = hits("yellow photo")
        self.assertIn(1, found)
        self.assertNotIn(8, found)
        self.assertIn(12, hits("sep 25, 2025 pictures"))

    def test_item_date_beats_the_folder_year(self):
        filters = parsed("in 2025")
        self.assertFalse(search_lib.item_matches(
            [2, "IMG_2.jpg", "image", "2024-01-09"],
            filters,
            group_year="2025",
            group_month="06-June",
        ))
        self.assertTrue(search_lib.item_matches(
            [2, "IMG_2.jpg", "image", "2024-01-09"],
            parsed("in 2024"),
            group_year="2025",
            group_month="01-January",
        ))

    def test_missing_item_date_uses_the_folder(self):
        filters = parsed("in 2025")
        self.assertTrue(search_lib.item_matches(
            [10, "nap.mp4", "video", ""],
            filters,
            group_year="2025",
            group_month="06-June",
        ))
        self.assertFalse(search_lib.item_matches(
            [10, "nap.mp4", "video", ""],
            parsed("sep 25, 2025"),
            group_year="2025",
            group_month="06-June",
        ))

    def test_person_id_or_filename(self):
        filters = parsed("yara")
        self.assertTrue(search_lib.item_matches(
            [3, "baby.jpg", "image", "2025-06-02"],
            filters,
            ids_by_person=IDS,
        ))
        self.assertTrue(search_lib.item_matches(
            [8, "yara-carseat.mp4", "video", "2025-06-02"],
            filters,
        ))
        self.assertFalse(search_lib.item_matches(
            [7, "VID_20141030.mp4", "video", "2025-06-02"],
            filters,
            ids_by_person=IDS,
        ))
        self.assertFalse(search_lib.item_matches(
            [13, "camera.jpg", "image", "2025-06-02"],
            parsed("me"),
            ids_by_person=IDS,
        ))

    def test_string_ids_still_match(self):
        self.assertTrue(search_lib.item_matches(
            [3, "baby.jpg", "image", "2025-06-02"],
            parsed("yara"),
            ids_by_person={"Yara": ["3"]},
        ))

    def test_two_people_are_both_required(self):
        self.assertEqual(hits("yara and haneen"), [])

    def test_filter_groups_drops_empty_months(self):
        groups = search_lib.filter_groups(GROUPS, parsed("haneen"), CAPTIONS, IDS)
        self.assertEqual(groups, [])

    def test_small_person_list_is_not_dropped(self):
        people = [{"name": "Sam", "ids": [20]}]
        filters = search_lib.parse_query("sam in 2025", people)
        self.assertEqual(filters["person"], "Sam")
        self.assertTrue(search_lib.item_matches(
            [20, "IMG.jpg", "image", "2025-02-02"],
            filters,
            ids_by_person={"sam": {20}},
        ))


class PageCopyTests(unittest.TestCase):
    def test_server_imports_the_search_module(self):
        source = (Path(__file__).parent / "server.py").read_text()
        self.assertIn("import search_lib", source)
        self.assertNotIn("faces_lib", source)
        self.assertNotIn("caption_lib", source)

    def test_the_photo_page_has_no_help_button(self):
        html = (Path(__file__).parent / "static" / "index.html").read_text()
        self.assertNotIn('id="search-help"', html)
        self.assertNotIn(">Help</button>", html)
        self.assertNotIn("Loading library", html)
        self.assertIn('id="placeholders"', html)
        faces = (Path(__file__).parent / "static" / "faces.html").read_text()
        categories = (Path(__file__).parent / "static" / "categories.html").read_text()
        self.assertNotIn("Loading faces", faces)
        self.assertNotIn("Loading categories", categories)
        self.assertIn('class="bone"', faces)
        self.assertIn('class="bone"', categories)
        self.assertNotIn("\u2014", html)

    def test_readme_uses_placeholder_names(self):
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
        self.assertIn("alex in a carseat video", readme)
        self.assertIn("sam wearing yellow", readme)
        self.assertIn("sam in 2025", readme)
        self.assertIn("screenshots from 2024", readme)
        self.assertIn("documents in 2025", readme)
        self.assertNotIn("Yara", readme)
        self.assertNotIn("Haneen", readme)
        self.assertNotIn("\u2014", readme)


if __name__ == "__main__":
    unittest.main()
