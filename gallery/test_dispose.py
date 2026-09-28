import unittest

import dispose_lib


class DisposeTest(unittest.TestCase):
    def test_strength_rises_when_the_frame_is_dull(self):
        sharp, spread = dispose_lib.normalize(20, 8)
        self.assertGreater(dispose_lib.strength_for(sharp, spread), 80)
        sharp, spread = dispose_lib.normalize(800, 60)
        self.assertLess(dispose_lib.strength_for(sharp, spread), 40)

    def test_careful_hides_a_named_person(self):
        self.assertFalse(dispose_lib.visible("careful", 90, named=True, caption_flag=True))
        self.assertTrue(dispose_lib.visible("careful", 90, named=False, caption_flag=False))
        self.assertFalse(dispose_lib.visible("careful", 40, named=False, caption_flag=True))

    def test_aggressive_can_include_a_weak_named_photo(self):
        self.assertFalse(dispose_lib.visible("normal", 90, named=True, caption_flag=True))
        self.assertTrue(dispose_lib.visible("aggressive", 80, named=True, caption_flag=False))
        self.assertFalse(dispose_lib.visible("aggressive", 50, named=True, caption_flag=True))

    def test_a_caption_alone_is_not_enough_on_careful(self):
        self.assertTrue(dispose_lib.visible("normal", 20, named=False, caption_flag=True))
        self.assertEqual(dispose_lib.reason_for(30, 80, ""), "Blurry frame")
        self.assertEqual(dispose_lib.reason_for(90, 10, ""), "Flat color")
        self.assertEqual(dispose_lib.reason_for(90, 80, "Screenshot"), "Screenshot")

    def test_a_missing_caption_can_still_be_junk(self):
        self.assertTrue(dispose_lib.visible("careful", 85, named=False, caption_flag=False))
        self.assertTrue(dispose_lib.visible("aggressive", 40, named=False, caption_flag=False))


if __name__ == "__main__":
    unittest.main()
