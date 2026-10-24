"""Presentation tests for CLI styling. Plain mode must keep the original text."""

import os
import unittest

from contexta_app.cli_style import color_enabled, format_banner, format_log_line, format_saved


class TestCliStyle(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("NO_COLOR", None)
        os.environ.pop("CONTEXTA_COLOR", None)

    def test_plain_output_matches_the_unstyled_messages(self):
        os.environ["NO_COLOR"] = "1"
        os.environ.pop("CONTEXTA_COLOR", None)
        self.assertFalse(color_enabled())
        self.assertEqual(format_log_line("Scanning project structure...", "info"), "Scanning project structure...")
        self.assertEqual(format_saved("/tmp/contexta-out/pack.md"), "\nSaved: /tmp/contexta-out/pack.md")
        self.assertEqual(format_banner("2.0.0", "sample-app", "onboarding"), "")

    def test_forced_color_keeps_the_message_and_adds_markup(self):
        os.environ["CONTEXTA_COLOR"] = "always"
        os.environ.pop("NO_COLOR", None)
        line = format_log_line("Insight layer ready.", "ok")
        self.assertIn("Insight layer ready.", line)
        self.assertIn("\033", line)
        self.assertTrue(format_banner("2.0.0", "sample-app", "onboarding"))


if __name__ == "__main__":
    unittest.main()
