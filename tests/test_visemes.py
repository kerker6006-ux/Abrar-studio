from __future__ import annotations

import unittest

from abrar_studio.visemes import viseme_shape


class KoreanVisemeTests(unittest.TestCase):
    def test_pause_closes_mouth(self):
        self.assertEqual(viseme_shape("가 나", 0.45, 0.9), "closed")

    def test_wide_vowel_uses_wide_shape(self):
        self.assertEqual(viseme_shape("아", 0.5, 0.9), "wide")

    def test_round_vowel_uses_round_shape(self):
        self.assertEqual(viseme_shape("우", 0.5, 0.9), "round")

    def test_low_energy_closes(self):
        self.assertEqual(viseme_shape("아", 0.5, 0.01), "closed")
