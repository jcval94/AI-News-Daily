import unittest

from pipeline.local.resolve_api import probe_connected_resolve


class FakeManager:
    pass


class FakeResolve:
    AUDIO_SYNC_MODE = 1
    AUDIO_SYNC_WAVEFORM = 2

    def GetVersionString(self):
        return "21.0-test"

    def GetProjectManager(self):
        return FakeManager()


class LocalResolveProbeTests(unittest.TestCase):
    def test_connected_probe_is_feature_based(self):
        result = probe_connected_resolve(FakeResolve())
        self.assertTrue(result["connected"])
        self.assertEqual(result["version"], "21.0-test")
        self.assertTrue(result["audio_sync_api"])


if __name__ == "__main__":
    unittest.main()
