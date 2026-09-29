"""Simulations : propriétés mathématiques et recalcul indépendant ligne à ligne."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from profit import whatif as w


def brute_force_price(lines: pd.DataFrame, x: float, e: float, v: float) -> float:
    """Recalcule ligne à ligne : nouvelles quantités, nouveau revenu, coût évité = v x coût des unités perdues."""
    vol = max(0.0, 1 + e * x)
    q1 = lines["q"] * vol
    revenue1 = (q1 * lines["price"] * (1 + x)).sum()
    cost1 = (lines["cogs"] * (1 - v * (1 - vol)) if False else lines["cogs"] * (1 - v * (1 - vol))).sum()
    base = (lines["q"] * lines["price"]).sum() - lines["cogs"].sum()
    return (revenue1 - cost1) - base


@pytest.mark.parametrize("seed", range(20))
def test_price_change_matches_line_by_line_recomputation(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(2, 30))
    lines = pd.DataFrame({"q": rng.integers(1, 200, n).astype(float), "price": rng.uniform(5, 90, n), "cogs": rng.uniform(100, 5000, n)})
    seg = w.Segment(float((lines.q * lines.price).sum()), float(lines.cogs.sum()))
    x, e, v = float(rng.uniform(0, .3)), float(rng.uniform(-4, 0)), float(rng.uniform(.4, 1))
    assert w.price_change(seg, x, e, v) == pytest.approx(brute_force_price(lines, x, e, v), rel=1e-9, abs=1e-6)


def test_no_price_change_no_effect():
    seg = w.Segment(1000, 800)
    for e in (0, -1, -5):
        assert w.price_change(seg, 0.0, e) == 0


def test_price_increase_without_volume_loss_gains_revenue_times_x():
    seg = w.Segment(2_000_000, 2_300_000)
    assert w.price_change(seg, 0.05, 0.0) == pytest.approx(100_000)


def test_loss_making_segment_always_gains_from_price_increase():
    seg = w.Segment(1000, 1200)                            # marge négative
    for x in (0.01, 0.05, 0.3):
        for e in (0, -1, -3, -10, -100):                   # y compris perte totale des volumes
            assert w.price_change(seg, x, e) > 0, (x, e)
    assert w.break_even_elasticity(seg, 0.05) is None


def test_break_even_elasticity_profitable_segment():
    seg = w.Segment(100, 60)                               # marge +40
    e_star = w.break_even_elasticity(seg, 0.10)
    assert e_star == pytest.approx(-100 / (110 - 60))      # = -2
    assert w.price_change(seg, 0.10, e_star) == pytest.approx(0, abs=1e-9)
    assert w.price_change(seg, 0.10, e_star + 0.3) > 0 and w.price_change(seg, 0.10, e_star - 0.3) < 0


def test_cost_avoidance_share_lowers_gain_when_volume_falls():
    seg = w.Segment(1000, 1200)
    assert w.price_change(seg, 0.1, -3, 1.0) > w.price_change(seg, 0.1, -3, 0.6)
    assert w.price_change(seg, 0.1, 0.0, 1.0) == w.price_change(seg, 0.1, 0.0, 0.6), "sans perte de volume, v est sans effet"


def test_price_grid_shape_and_values():
    seg = w.Segment(1000, 1200)
    g = w.price_grid(seg, [0.05, 0.1], [0, -1, -2])
    assert g.shape == (2, 3) and g.loc[0.05, 0] == pytest.approx(50)


def test_stop_selling_break_even():
    seg = w.Segment(919, 1000)
    assert w.break_even_variable_share(seg) == pytest.approx(0.919)
    assert w.stop_selling(seg, 0.919) == pytest.approx(0, abs=1e-9)
    assert w.stop_selling(seg, 1.0) == pytest.approx(81) and w.stop_selling(seg, 0.8) < 0
    assert w.stop_selling(seg, 1.0) == pytest.approx(-seg.margin), "avec 100 % de coût évitable, on supprime exactement la perte"


LINES = pd.DataFrame({
    "gross_amount": [1000, 1000, 500, 200], "discount_amount": [50, 200, 100, 0],
    "margin_before_discount": [300, -100, 50, 40], "gross_margin": [250, -300, -50, 40]})


def test_discount_rule_no_discount_below_cost():
    r = w.discount_rule(LINES, "no_discount_below_cost")
    assert r["lines"] == 1 and r["discount_removed"] == 200 and r["margin_delta"] == 200


def test_discount_rule_cap():
    r = w.discount_rule(LINES, "cap", cap=0.10)             # ligne 2 : 20 % -> 10 % (retire 100) ; ligne 3 : 20 % -> 10 % (retire 50)
    assert r["lines"] == 2 and r["discount_removed"] == 150 and r["margin_delta"] == 150
    assert w.discount_rule(LINES, "cap", cap=0.0)["discount_removed"] == 350
    assert w.discount_rule(LINES, "cap", cap=1.0)["lines"] == 0


def test_discount_rule_cap_monotonic():
    removed = [w.discount_rule(LINES, "cap", cap=c)["discount_removed"] for c in (0.0, 0.05, 0.1, 0.2, 0.5)]
    assert removed == sorted(removed, reverse=True)


def test_discount_rule_lost_volume():
    r = w.discount_rule(LINES, "no_discount_below_cost", lost_volume_share=1.0)
    assert r["margin_delta"] == pytest.approx(-(-300))       # on perd toute la ligne : la perte de -300 disparaît
    r0 = w.discount_rule(LINES, "no_discount_below_cost", lost_volume_share=0.0)
    assert r["margin_delta"] > r0["margin_delta"], "perdre du volume sur des lignes à perte améliore la marge (hypothèse v = 100 %)"


def test_discount_rule_errors():
    with pytest.raises(ValueError):
        w.discount_rule(LINES, "inconnue")
    with pytest.raises(ValueError):
        w.discount_rule(LINES, "cap")
