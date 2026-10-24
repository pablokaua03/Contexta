"""
selector.py - Pick files for a token budget.

``fit_to_budget`` takes files already ranked by priority and a cost function,
and returns which to keep, at what detail, and which to drop. It knows nothing
about packs or Markdown, so it is easy to test.

Detail tiers, cheapest last: the pack's own compression, ``signatures``,
``lean`` (metadata plus a few signatures).

Algorithm:
1. Breadth: keep the longest ranked prefix whose lean cost fits in a third of
   the budget, so a small budget still shows the shape of the code.
2. Depth: walk the ranking and give each kept file the richest tier that still
   fits what is left.
3. Fill: keep adding lower-ranked files at the richest affordable tier until the
   budget or the ranking runs out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, Sequence, TypeVar

T = TypeVar("T")

BREADTH_SHARE = 1 / 3
MAX_CONSECUTIVE_MISSES = 25


@dataclass
class Selection(Generic[T]):
    budget: int
    kept: list[tuple[T, str]] = field(default_factory=list)
    dropped: list[T] = field(default_factory=list)
    used: int = 0

    @property
    def kept_items(self) -> list[T]:
        return [item for item, _tier in self.kept]

    def tier_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for _item, tier in self.kept:
            counts[tier] = counts.get(tier, 0) + 1
        return counts


def tiers_for(compression: str) -> list[str]:
    """Richest to cheapest detail levels to try, starting at the pack's own."""
    ladder = ["full", "balanced", "focused", "signatures", "lean"]
    if compression not in ladder:
        compression = "balanced"
    tiers = [compression]
    for tier in ("signatures", "lean"):
        if ladder.index(tier) > ladder.index(compression):
            tiers.append(tier)
    if "lean" not in tiers:
        tiers.append("lean")
    return tiers


def fit_to_budget(
    ranked: Sequence[T],
    budget: int,
    cost: Callable[[T, str], int],
    tiers: Sequence[str],
) -> Selection[T]:
    """Choose files and detail so the summed cost stays at or under ``budget``.

    ``ranked`` is best first. ``cost(item, tier)`` is the token cost of showing
    ``item`` at ``tier``. The result always keeps the top file when budget is
    positive, even if only at the cheapest tier, so a pack is never empty.
    """
    result: Selection[T] = Selection(budget=max(0, budget))
    if not ranked:
        return result
    richest, cheapest = tiers[0], tiers[-1]
    cache: dict[tuple[int, str], int] = {}

    def cost_of(index: int, tier: str) -> int:
        key = (index, tier)
        if key not in cache:
            cache[key] = max(1, cost(ranked[index], tier))
        return cache[key]

    # 1. Breadth at the cheapest tier.
    breadth_limit = result.budget * BREADTH_SHARE
    chosen: list[int] = []
    spent = 0
    for index in range(len(ranked)):
        lean = cost_of(index, cheapest)
        if spent + lean > breadth_limit and chosen:
            break
        chosen.append(index)
        spent += lean
    tier_of = {index: cheapest for index in chosen}

    # 2. Depth: upgrade in rank order while the budget allows.
    for index in chosen:
        for tier in tiers:
            extra = cost_of(index, tier) - cost_of(index, tier_of[index])
            if tier == tier_of[index]:
                break
            if spent + extra <= result.budget:
                tier_of[index] = tier
                spent += extra
                break

    # 3. Fill with further files at the richest tier that fits.
    misses = 0
    for index in range(chosen[-1] + 1, len(ranked)):
        placed = False
        for tier in tiers:
            c = cost_of(index, tier)
            if spent + c <= result.budget:
                tier_of[index] = tier
                spent += c
                chosen.append(index)
                placed = True
                break
        if placed:
            misses = 0
        else:
            misses += 1
            if misses >= MAX_CONSECUTIVE_MISSES:
                break

    kept_set = set(chosen)
    result.kept = [(ranked[i], tier_of[i]) for i in sorted(kept_set)]
    result.dropped = [ranked[i] for i in range(len(ranked)) if i not in kept_set]
    result.used = spent
    return result
