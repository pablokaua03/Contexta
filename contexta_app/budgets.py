"""
budgets.py - Context-window fit estimates for a context pack.

Windows are approximate published input limits used for planning. They are not
a provider quota, and they reserve headroom for the user's question and the
model's reply.
"""

from __future__ import annotations

from dataclasses import dataclass

HEADROOM_RATIO = 0.20

@dataclass(frozen=True)
class ModelBudget:
    name: str
    window: int
    profile: str


@dataclass(frozen=True)
class BudgetFit:
    name: str
    window: int
    tokens: int
    status: str
    percent: float

    def as_dict(self) -> dict[str, int | float | str]:
        return {
            "model": self.name,
            "window": self.window,
            "tokens": self.tokens,
            "percent": round(self.percent, 1),
            "status": self.status,
        }


# Planning numbers for the profiles Contexta already exposes.
# Each entry is a commonly published context window, not a live model catalog.
PROFILE_BUDGETS: dict[str, tuple[ModelBudget, ...]] = {
    "generic": (
        ModelBudget("typical chat", 32_000, "generic"),
        ModelBudget("long-context session", 128_000, "generic"),
    ),
    "chatgpt": (
        ModelBudget("GPT-4o", 128_000, "chatgpt"),
        ModelBudget("GPT-4.1", 1_047_576, "chatgpt"),
    ),
    "claude": (
        ModelBudget("Claude Sonnet", 200_000, "claude"),
        ModelBudget("Claude Opus", 200_000, "claude"),
    ),
    "gemini": (
        ModelBudget("Gemini Flash", 1_048_576, "gemini"),
        ModelBudget("Gemini Pro", 1_048_576, "gemini"),
    ),
    "copilot": (
        ModelBudget("Copilot Chat", 64_000, "copilot"),
        ModelBudget("Copilot coding agent", 128_000, "copilot"),
    ),
}

COMPRESSION_LADDER: tuple[str, ...] = ("full", "balanced", "focused", "signatures", "lean")


def budgets_for(ai_profile: str) -> tuple[ModelBudget, ...]:
    return PROFILE_BUDGETS.get(ai_profile, PROFILE_BUDGETS["generic"])


def fit_status(tokens: int, window: int, headroom: float = HEADROOM_RATIO) -> str:
    """Classify a pack against one window.

    ``fits`` leaves the reserved headroom free. ``tight`` is inside the window
    but inside that headroom. ``over`` does not fit the window at all.
    """
    if window <= 0:
        return "over"
    usable = int(window * (1 - headroom))
    if tokens <= usable:
        return "fits"
    if tokens <= window:
        return "tight"
    return "over"


def evaluate_budgets(tokens: int, ai_profile: str) -> list[BudgetFit]:
    rows: list[BudgetFit] = []
    for budget in budgets_for(ai_profile):
        percent = (tokens / budget.window) * 100 if budget.window else 100.0
        rows.append(
            BudgetFit(
                name=budget.name,
                window=budget.window,
                tokens=tokens,
                status=fit_status(tokens, budget.window),
                percent=percent,
            )
        )
    return rows


def _compact_window(window: int) -> str:
    if window >= 1_000_000:
        value = window / 1_000_000
        text = f"{value:.1f}".rstrip("0").rstrip(".")
        return f"{text}M"
    if window >= 10_000:
        return f"{round(window / 1000)}k"
    return str(window)


def budget_summary(tokens: int, ai_profile: str) -> str:
    """One-line fit summary for pack footers and logs."""
    parts: list[str] = []
    for row in evaluate_budgets(tokens, ai_profile):
        window = _compact_window(row.window)
        if row.status == "fits":
            parts.append(f"fits {row.name} ({window})")
        elif row.status == "tight":
            parts.append(f"tight for {row.name} ({window})")
        else:
            parts.append(f"over {row.name} ({window})")
    return "budget: " + "; ".join(parts)


def format_budget_report(tokens: int, ai_profile: str) -> str:
    """Multi-line report printed next to a saved or streamed pack."""
    lines = [f"Context budget (~{tokens / 1000:.1f}k tokens, cl100k estimate, profile {ai_profile}):"]
    for row in evaluate_budgets(tokens, ai_profile):
        lines.append(
            f"  {row.name:<24} {_compact_window(row.window):>6}  {row.percent:5.1f}%  {row.status}"
        )
    lines.append("Headroom reserves 20% of each window for the question and the reply.")
    over = [row for row in evaluate_budgets(tokens, ai_profile) if row.status == "over"]
    tight = [row for row in evaluate_budgets(tokens, ai_profile) if row.status == "tight"]
    if over:
        names = ", ".join(row.name for row in over)
        lines.append(f"Over the planning window for {names}.")
    elif tight:
        names = ", ".join(row.name for row in tight)
        lines.append(f"Inside the window but tight for {names}.")
    return "\n".join(lines)


def next_compression(compression: str) -> str | None:
    try:
        index = COMPRESSION_LADDER.index(compression)
    except ValueError:
        return None
    if index + 1 >= len(COMPRESSION_LADDER):
        return None
    return COMPRESSION_LADDER[index + 1]
