import unittest

from separan.browser import BrowserAutomationUnavailable, BrowserProfile, browser_open


class BrowserBoundaryTests(unittest.TestCase):
    def test_profile_is_explicit_and_validated(self):
        profile = BrowserProfile(engine="firefox", screen_width=1920, screen_height=1080, language="ja-JP")
        self.assertEqual((profile.engine, profile.language), ("firefox", "ja-JP"))
        with self.assertRaises(ValueError): BrowserProfile(engine="pretend-chrome")
        with self.assertRaises(ValueError): BrowserProfile(screen_width=0)

    def test_no_http_fallback_pretends_to_be_a_browser(self):
        with self.assertRaisesRegex(BrowserAutomationUnavailable, "No browser engine adapter"):
            browser_open("https://example.com")

    def test_adapter_receives_profile_without_http_client_coupling(self):
        class Adapter:
            def open(self, url, profile): return url, profile
        url, profile = browser_open("https://example.com", adapter=Adapter())
        self.assertEqual(url, "https://example.com")
        self.assertIsInstance(profile, BrowserProfile)


if __name__ == "__main__": unittest.main()
