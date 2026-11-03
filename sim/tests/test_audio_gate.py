import unittest

import numpy as np

from v9_audio import AudioGateError, analyze_and_select


class AudioGateTests(unittest.TestCase):
    def test_failure_exposes_measured_metrics(self):
        quiet = np.full((480, 2), 0.01, dtype=np.float32)
        speech = np.full((480, 2), 0.01, dtype=np.float32)
        config = {
            "minimum_speech_over_quiet_db": 6.0,
            "minimum_speech_rms_dbfs": -55.0,
            "maximum_clip_percent": 0.1,
        }
        with self.assertRaises(AudioGateError) as caught:
            analyze_and_select(quiet, speech, config)
        self.assertIn("speech_over_quiet_db", caught.exception.metrics)
        self.assertIn("语音相对底噪", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
