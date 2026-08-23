from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reproduce_aggregate_metrics.py"
SPEC = importlib.util.spec_from_file_location("reproduce_aggregate_metrics", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AggregateMetricTests(unittest.TestCase):
    def setUp(self) -> None:
        self.counts = json.loads((ROOT / "results" / "paper_aggregate_counts.json").read_text(encoding="utf-8"))
        self.metrics = MODULE.compute_metrics(self.counts)

    def test_primary_endpoint_uses_planned_denominator(self) -> None:
        self.assertTrue(math.isclose(self.metrics["main.strict_primary_endpoint"], 428 / 512))

    def test_conditional_metric_uses_accepted_denominator(self) -> None:
        self.assertTrue(math.isclose(self.metrics["main.accepted_strict_yes_conditional"], 428 / 430))

    def test_challenge_accuracy_uses_determinate_gold(self) -> None:
        self.assertTrue(math.isclose(self.metrics["challenge60.accuracy"], 31 / 57))

    def test_external_acceptance(self) -> None:
        self.assertEqual(self.metrics["external.formal_acceptance"], 0.99)


if __name__ == "__main__":
    unittest.main()
