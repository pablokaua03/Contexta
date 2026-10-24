"""--budget picks files by rank until the budget is used. --focus narrows the pack."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from contexta_app.renderer import estimate_tokens, export_pack, generate_markdown
from contexta_app.selector import fit_to_budget, tiers_for

TIERS = ("balanced", "signatures", "lean")
COSTS = {"balanced": 100, "signatures": 40, "lean": 10}


def cost(item: str, tier: str) -> int:
    return COSTS[tier]


class FitToBudgetTests(unittest.TestCase):
    def test_everything_fits_at_the_richest_tier(self):
        result = fit_to_budget(["a", "b", "c"], 1000, cost, TIERS)
        self.assertEqual(result.kept, [("a", "balanced"), ("b", "balanced"), ("c", "balanced")])
        self.assertEqual(result.dropped, [])
        self.assertEqual(result.used, 300)

    def test_never_exceeds_the_budget_and_keeps_rank_order(self):
        items = [f"f{i}" for i in range(30)]
        for budget in (50, 120, 400, 900, 2500):
            result = fit_to_budget(items, budget, cost, TIERS)
            self.assertLessEqual(result.used, max(budget, COSTS["lean"]), budget)
            kept = result.kept_items
            self.assertEqual(kept, [i for i in items if i in kept])
            self.assertEqual(sorted(kept + result.dropped), sorted(items))

    def test_higher_ranked_files_get_more_detail(self):
        items = [f"f{i}" for i in range(20)]
        result = fit_to_budget(items, 600, cost, TIERS)
        rank = {tier: i for i, tier in enumerate(reversed(TIERS))}  # lean < signatures < balanced
        levels = [rank[tier] for _item, tier in result.kept]
        self.assertEqual(levels, sorted(levels, reverse=True))
        self.assertEqual(result.kept[0][1], "balanced")

    def test_low_ranked_files_are_dropped_first(self):
        items = [f"f{i}" for i in range(50)]
        result = fit_to_budget(items, 300, cost, TIERS)
        self.assertIn("f0", result.kept_items)
        self.assertIn("f49", result.dropped)
        self.assertEqual(result.dropped, items[len(result.kept):])

    def test_top_file_survives_a_tiny_budget(self):
        result = fit_to_budget(["a", "b"], 1, cost, TIERS)
        self.assertEqual(result.kept_items, ["a"])
        self.assertEqual(result.dropped, ["b"])

    def test_tiers_start_at_the_pack_compression(self):
        self.assertEqual(tiers_for("balanced"), ["balanced", "signatures", "lean"])
        self.assertEqual(tiers_for("signatures"), ["signatures", "lean"])
        self.assertEqual(tiers_for("lean"), ["lean"])
        self.assertEqual(tiers_for("full")[0], "full")


def make_project(root: Path, files: int = 40) -> None:
    (root / "pyproject.toml").write_text('[project]\nname = "shop"\ndescription = "A small shop backend."\n', encoding="utf-8")
    pkg = root / "shop"
    pkg.mkdir()
    for i in range(files):
        body = "\n".join(f"def helper_{i}_{j}(value):\n    return value + {j}\n" for j in range(25))
        (pkg / f"module_{i}.py").write_text(body, encoding="utf-8")
    (pkg / "sessions.py").write_text(
        "import hmac\n\n"
        "def sign_session_cookie(payload, secret):\n    return hmac.new(secret, payload).hexdigest()\n\n"
        "def read_session_cookie(cookie, secret):\n    return cookie\n",
        encoding="utf-8",
    )
    (root / "main.py").write_text("from shop.sessions import sign_session_cookie\n\nprint(sign_session_cookie(b'x', b'y'))\n", encoding="utf-8")


class BudgetPackTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        make_project(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_pack_fits_the_budget_and_reports_what_was_left_out(self):
        full_stats: dict = {}
        generate_markdown(self.root, stats=full_stats)
        budget = 4000
        self.assertGreater(full_stats["tokens"], budget * 2)
        stats: dict = {}
        text = generate_markdown(self.root, token_budget=budget, stats=stats)
        self.assertLessEqual(stats["tokens"], budget)
        self.assertGreater(stats["tokens"], budget * 0.6)
        self.assertGreater(len(stats["dropped"]), 0)
        self.assertIn("## Token Budget", text)
        self.assertIn("Left out to fit", text)
        self.assertEqual(estimate_tokens(text) > 0, True)

    def test_a_budget_that_already_fits_drops_nothing(self):
        stats: dict = {}
        text = generate_markdown(self.root, token_budget=500_000, stats=stats)
        self.assertEqual(stats["dropped"], [])
        self.assertIn("Nothing was left out.", text)

    def test_json_export_carries_the_same_budget_pack(self):
        stats: dict = {}
        export_pack(self.root, output_format="json", stats=stats, token_budget=3000)
        self.assertLessEqual(stats["tokens"], 3000)

    def test_without_a_budget_the_pack_is_unchanged(self):
        stats: dict = {}
        text = generate_markdown(self.root, stats=stats)
        self.assertNotIn("## Token Budget", text)
        self.assertNotIn("budget_report", stats)


class FocusTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        make_project(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_focus_shrinks_the_pack_and_leads_with_the_matching_file(self):
        full: dict = {}
        generate_markdown(self.root, stats=full)
        focused: dict = {}
        text = generate_markdown(self.root, focus_query="session cookie signing", stats=focused)
        self.assertLess(focused["tokens"], full["tokens"] / 4)
        first_line = next(line for line in text.splitlines() if line.startswith("1. `"))
        self.assertIn("shop/sessions.py", first_line)
        payload = [line for line in text.splitlines() if line.startswith("### 📄")]
        self.assertIn("### 📄 `shop/sessions.py`", payload)
        self.assertLess(len(payload), 12)

    def test_focus_with_no_match_keeps_the_normal_pack(self):
        stats: dict = {}
        text = generate_markdown(self.root, focus_query="zzzqqq", stats=stats)
        payload = [line for line in text.splitlines() if line.startswith("### 📄")]
        self.assertGreater(len(payload), 30)

    def test_focus_and_budget_combine(self):
        stats: dict = {}
        text = generate_markdown(self.root, focus_query="session cookie", token_budget=2500, stats=stats)
        self.assertLessEqual(stats["tokens"], 2500)
        self.assertIn("### 📄 `shop/sessions.py`", text)


class CliFlagTests(unittest.TestCase):
    def test_budget_and_max_tokens_are_the_same_option(self):
        from contexta_app.cli import build_parser

        parser = build_parser()
        self.assertEqual(parser.parse_args(["x", "--budget", "1234"]).max_tokens, 1234)
        self.assertEqual(parser.parse_args(["x", "--max-tokens", "99"]).max_tokens, 99)


if __name__ == "__main__":
    unittest.main()
