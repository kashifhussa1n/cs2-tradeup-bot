"""Filler substitutions must not monopolize scarce live verification slots."""
from dataclasses import replace
import unittest
from src.search import Candidate, diverse
from test_pipeline import block


class ShortlistTests(unittest.TestCase):
    def test_dominant_skin_capped_across_fillers_and_wears(self):
        dominant = block("P90 | Glacier Mesh", "Vertigo")
        candidates = []
        for i in range(20):
            varied = replace(dominant, wear="Well-Worn" if i % 2 else "Field-Tested")
            filler = block(f"Filler {i}", f"Collection {i}")
            candidates.append(Candidate([(varied, 9), (filler, 1)], 10, 50, 30, 300, 1, 30-i*.1))
        alternative = Candidate([(block("P90 | Facility Negative", "Nuke"), 10)], 1.4, 1.77, .137, 9.8, .3, .23)
        selected = diverse(candidates+[alternative], 12)
        self.assertIn(alternative, selected)
        self.assertEqual(sum(any(b.name == dominant.name for b, _ in c.parts) for c in selected), 4)

    def test_balanced_mix_caps_both_major_dependencies(self):
        a = block("A", "A")
        candidates = [Candidate([(a, 5), (block(str(i), str(i)), 5)], 10, 20, 7.4, 74, 1, 10-i)
                      for i in range(8)]
        self.assertEqual(len(diverse(candidates, 12)), 4)

    def test_same_skin_multiple_wears_aggregated(self):
        a = block("A", "A")
        candidates = [Candidate([(a, 3), (replace(a, wear="Minimal Wear"), 3),
                                 (block(str(i), str(i)), 4)], 10, 20, 7.4, 74, 1, 10-i)
                      for i in range(8)]
        self.assertEqual(len(diverse(candidates, 12)), 4)
