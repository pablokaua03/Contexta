"""
tests/test_ui.py - Focused tests for UI helpers.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from ui import (
    SCROLL_TARGET_ATTR,
    _window_icon_source,
    can_scroll_target,
    estimate_selected_files,
    estimate_tokens_for_preview,
    normalize_mousewheel_units,
    resolve_pack_focus,
    resolve_scroll_target,
)


class FakeScrollable:
    def __init__(self, yview_state=(0.0, 1.0)):
        self._yview_state = yview_state

    def yview(self):
        return self._yview_state


class FakeWidget:
    def __init__(self, name: str, parent=None, scroll_target=None):
        self._name = name
        self._parent = parent
        self._registry = {name: self}
        if parent is not None:
            self._registry.update(parent._registry)
            self._registry[name] = self
        if scroll_target is not None:
            setattr(self, SCROLL_TARGET_ATTR, scroll_target)

    def winfo_parent(self):
        return "" if self._parent is None else self._parent._name

    def nametowidget(self, name: str):
        return self._registry[name]


class TestUiHelpers(unittest.TestCase):
    def test_resolve_pack_focus_preserves_manual_value(self):
        focus, auto = resolve_pack_focus("custom auth flow", "backend api server", "frontend ui screen")
        self.assertEqual((focus, auto), ("custom auth flow", "backend api server"))

    def test_estimate_selected_files_for_full_uses_total(self):
        self.assertEqual(estimate_selected_files(42, 3, "full", False), 42)

    def test_estimate_selected_files_for_diff_tracks_changes(self):
        self.assertEqual(estimate_selected_files(50, 4, "diff", False), 8)

    def test_estimate_tokens_drop_with_stronger_compression(self):
        full_tokens = estimate_tokens_for_preview(12, "full")
        focused_tokens = estimate_tokens_for_preview(12, "focused")
        self.assertGreater(full_tokens, focused_tokens)

    def test_normalize_mousewheel_units_handles_windows_delta(self):
        self.assertEqual(normalize_mousewheel_units(SimpleNamespace(delta=120)), -1)
        self.assertEqual(normalize_mousewheel_units(SimpleNamespace(delta=-240)), 2)

    def test_normalize_mousewheel_units_handles_button_scroll(self):
        self.assertEqual(normalize_mousewheel_units(SimpleNamespace(num=4, delta=0)), -1)
        self.assertEqual(normalize_mousewheel_units(SimpleNamespace(num=5, delta=0)), 1)

    def test_resolve_scroll_target_prefers_inner_scrollable_when_it_can_scroll(self):
        outer_target = FakeScrollable((0.1, 0.9))
        inner_target = FakeScrollable((0.1, 0.9))
        root = FakeWidget(".root", scroll_target=outer_target)
        preview = FakeWidget(".preview", parent=root, scroll_target=inner_target)
        leaf = FakeWidget(".leaf", parent=preview)

        self.assertIs(resolve_scroll_target(leaf, 1), inner_target)

    def test_resolve_scroll_target_falls_back_to_outer_when_inner_is_at_edge(self):
        outer_target = FakeScrollable((0.1, 0.9))
        inner_target = FakeScrollable((0.0, 1.0))
        root = FakeWidget(".root", scroll_target=outer_target)
        preview = FakeWidget(".preview", parent=root, scroll_target=inner_target)
        leaf = FakeWidget(".leaf", parent=preview)

        self.assertIs(resolve_scroll_target(leaf, 1), outer_target)

    def test_can_scroll_target_checks_directional_bounds(self):
        self.assertFalse(can_scroll_target(FakeScrollable((0.0, 1.0)), 1))
        self.assertFalse(can_scroll_target(FakeScrollable((0.0, 1.0)), -1))
        self.assertTrue(can_scroll_target(FakeScrollable((0.2, 1.0)), -1))
        self.assertTrue(can_scroll_target(FakeScrollable((0.0, 0.8)), 1))

    @patch("ui.sys.platform", "win32")
    @patch("ui.sys.executable", r"C:\laragon\www\contexta\dist\contexta.exe")
    def test_window_icon_source_prefers_executable_for_frozen_windows_build(self):
        with patch.object(sys, "frozen", True, create=True):
            self.assertEqual(_window_icon_source(), r"C:\laragon\www\contexta\dist\contexta.exe")


if __name__ == "__main__":
    unittest.main()
