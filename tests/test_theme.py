"""Contrast checks for the shared dark and light palettes."""

import unittest

from contexta_app.theme import DARK, LIGHT, contrast_ratio, readable_fg


class TestThemeContrast(unittest.TestCase):
    def test_body_and_caption_text_clear_wcag_aa(self):
        pairs = (
            ("text", "bg"),
            ("text", "card"),
            ("text2", "card"),
            ("text3", "card"),
            ("text3", "bg"),
            ("tag_fg", "tag_bg"),
            ("red", "danger_soft"),
            ("amber", "warn_soft"),
            ("green", "ok_soft"),
        )
        for palette in (DARK, LIGHT):
            for fg_key, bg_key in pairs:
                ratio = contrast_ratio(palette[fg_key], palette[bg_key])
                self.assertGreaterEqual(
                    ratio,
                    4.5,
                    f"{palette['mode']} {fg_key} on {bg_key} is {ratio:.2f}",
                )

    def test_bright_fills_pick_a_readable_label(self):
        for palette in (DARK, LIGHT):
            # readable_fg uses the active theme ink/white. Compare both candidates directly.
            for fill in ("accent", "red"):
                background = palette[fill]
                ink = contrast_ratio(palette["ink"], background)
                white = contrast_ratio(palette["white"], background)
                self.assertGreaterEqual(max(ink, white), 4.5, palette["mode"] + " " + fill)
                # The helper must agree once that palette is active.
        from contexta_app.theme import C, apply_theme

        for palette in (DARK, LIGHT):
            apply_theme(palette)
            for fill in ("accent", "red", "green"):
                self.assertGreaterEqual(contrast_ratio(readable_fg(C[fill]), C[fill]), 4.5)
        apply_theme(DARK)


if __name__ == "__main__":
    unittest.main()
