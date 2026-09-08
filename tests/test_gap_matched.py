import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rebuild_evidence as a
from reanalyse_revision import gap_matched_legacy


class WindowTests(unittest.TestCase):
    def test_time_window_inclusive_edge_and_reset(self):
        starts, segments, resets = a.window_bounds([0., .3, 1.1, 2., 2.01, 6.], 2., 1.5)
        self.assertEqual(starts, [0, 0, 0, 0, 1, 5])
        self.assertEqual(resets, [False, False, False, False, False, True])
        self.assertEqual(segments[-1], 1)

    def test_sample_history_resets_without_changing_channel_gate(self):
        t = [i / 10 for i in range(25)] + [10., 10.1]
        data = a.SessionData("TEST", "0", Path("synthetic.csv"), t, [9.8]*27,
                             [0.1]*25+[2., .2], list(range(27)), [0.]*27, [0.]*27)
        qc = a.qc_row(data)
        result = gap_matched_legacy(data, qc)
        self.assertEqual(result[24]["window_start_index"], 4)
        self.assertEqual(result[25]["window_start_index"], 25)
        self.assertEqual(result[25]["window_sample_count"], 1)
        self.assertTrue(result[25]["gap_reset"])
        self.assertTrue(result[25]["euler_channel_usable"])
        self.assertEqual(result[26]["window_sample_count"], 2)


if __name__ == "__main__":
    unittest.main()
