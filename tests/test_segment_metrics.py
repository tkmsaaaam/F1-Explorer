import unittest

from visualizations.segment_metrics import (
    deltas_to_reference,
    rank_segment_durations,
    segment_durations,
)


class SegmentMetricsTests(unittest.TestCase):
    def test_segment_durations_use_end_minus_start_and_preserve_missing(self):
        boundaries = {
            "A": [10.0, 12.5, 11.0, None, 15.0],
            "B": [None, 3.0, 5.0],
        }

        self.assertEqual(
            {
                "A": [2.5, -1.5, None, None],
                "B": [None, 2.0],
            },
            segment_durations(boundaries),
        )

    def test_segment_durations_accept_one_sequence(self):
        self.assertEqual([1.25, 2.75], segment_durations([0.0, 1.25, 4.0]))

    def test_ranks_exclude_missing_and_equal_values_share_rank(self):
        durations = {
            "A": [2.0, None],
            "B": [1.0, 4.0],
            "C": [1.0, 3.0],
            "D": [None, 2.0],
        }

        self.assertEqual(
            {
                "A": [3, None],
                "B": [1, 3],
                "C": [1, 2],
                "D": [None, 1],
            },
            rank_segment_durations(durations),
        )

    def test_deltas_are_driver_minus_reference(self):
        durations = {
            "reference": [2.0, None, 5.0],
            "faster": [1.5, 3.0, 5.5],
            "slower": [2.25, 4.0],
        }

        self.assertEqual(
            {
                "reference": [0.0, None, 0.0],
                "faster": [-0.5, None, 0.5],
                "slower": [0.25, None],
            },
            deltas_to_reference(durations, "reference"),
        )

    def test_empty_inputs(self):
        self.assertEqual({}, segment_durations({}))
        self.assertEqual([], segment_durations([]))
        self.assertEqual({}, rank_segment_durations({}))
        self.assertEqual({}, deltas_to_reference({}, "reference"))


if __name__ == "__main__":
    unittest.main()
