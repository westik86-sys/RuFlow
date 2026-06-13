#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runner import normalize_text


class NormalizeTextTests(unittest.TestCase):
    def test_adds_missing_space_before_dash(self) -> None:
        self.assertEqual(normalize_text("Пример— это бла бла бла"), "Пример — это бла бла бла")

    def test_adds_missing_space_after_dash(self) -> None:
        self.assertEqual(normalize_text("Пример —это бла бла бла"), "Пример — это бла бла бла")

    def test_adds_missing_spaces_around_dash(self) -> None:
        self.assertEqual(normalize_text("Пример—это бла бла бла"), "Пример — это бла бла бла")

    def test_keeps_leading_dialogue_dash_at_start(self) -> None:
        self.assertEqual(normalize_text("— Пример"), "— Пример")


if __name__ == "__main__":
    unittest.main()
