from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from geosynq.verifiers import verify_candidate


class VerifierTests(unittest.TestCase):
    def test_synthetic_equivalent_candidate_passes(self) -> None:
        logic = [
            "Triangle(A,B,C)",
            "Midpoint(D,BC)",
            "Value(BD,3)",
            "Target(Length(BC))",
        ]
        result = verify_candidate(
            original_text="Point D bisects BC in triangle ABC. If BD = 3, find BC.",
            candidate_text="In triangle ABC, D is the midpoint of BC and BD = 3. Determine the length of BC.",
            original_logic_forms=logic,
            candidate_logic_forms=logic,
            original_answer_text="Answer: 6",
            candidate_answer_text="Answer: 6",
        )
        self.assertTrue(result.predicate_consistent)
        self.assertTrue(result.no_new_points)
        self.assertTrue(result.numeric_consistent)
        self.assertIs(result.target_consistent, True)
        self.assertTrue(result.term_preserved)
        self.assertIs(result.answer_consistent, True)

    def test_number_change_is_detected(self) -> None:
        result = verify_candidate(
            original_text="In triangle ABC, BD = 3. Find BC.",
            candidate_text="In triangle ABC, BD = 4. Find BC.",
        )
        self.assertFalse(result.numeric_consistent)

    def test_new_point_is_detected(self) -> None:
        result = verify_candidate(
            original_text="In triangle ABC, find BC.",
            candidate_text="In triangle ABC with point D, find BC.",
        )
        self.assertFalse(result.no_new_points)

    def test_target_change_is_detected(self) -> None:
        result = verify_candidate(
            original_text="In triangle ABC, find BC.",
            candidate_text="In triangle ABC, find AB.",
        )
        self.assertIs(result.target_consistent, False)


if __name__ == "__main__":
    unittest.main()
