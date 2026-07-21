"""Commission rule unit tests: flat rate and tiered marginal bands."""

from decimal import Decimal

import pytest

from commission_engine.rules.flat import FlatRate
from commission_engine.rules.registry import build_rule, load_clients
from commission_engine.rules.tiered import Tier, Tiered


class TestFlatRate:
    def test_ten_percent_exact(self):
        rule = FlatRate(Decimal("0.10"))
        assert rule.commission(Decimal("4145")) == Decimal("414.50")

    def test_no_hidden_rounding(self):
        # 894.75 * 0.10 = 89.475 exactly; rounding is a rendering concern
        rule = FlatRate(Decimal("0.10"))
        assert rule.commission(Decimal("894.75")) == Decimal("89.475")

    def test_zero_gross(self):
        assert FlatRate(Decimal("0.10")).commission(Decimal("0")) == Decimal("0")

    def test_negative_rate_rejected(self):
        with pytest.raises(ValueError):
            FlatRate(Decimal("-0.10"))


class TestTieredMarginalBands:
    def test_marginal_math_across_two_bands(self):
        # 10% on the first 100k, 15% above: gross 150k
        # -> 100000*0.10 + 50000*0.15 = 10000 + 7500 = 17500
        rule = Tiered(
            [Tier(up_to=Decimal("100000"), rate=Decimal("0.10")), Tier(up_to=None, rate=Decimal("0.15"))]
        )
        assert rule.commission(Decimal("150000")) == Decimal("17500.00")

    def test_gross_below_first_threshold_uses_only_first_band(self):
        rule = Tiered(
            [Tier(up_to=Decimal("100000"), rate=Decimal("0.10")), Tier(up_to=None, rate=Decimal("0.15"))]
        )
        assert rule.commission(Decimal("40000")) == Decimal("4000.00")

    def test_gross_exactly_at_threshold(self):
        rule = Tiered(
            [Tier(up_to=Decimal("100000"), rate=Decimal("0.10")), Tier(up_to=None, rate=Decimal("0.15"))]
        )
        assert rule.commission(Decimal("100000")) == Decimal("10000.00")

    def test_three_bands(self):
        rule = Tiered(
            [
                Tier(up_to=Decimal("1000"), rate=Decimal("0.05")),
                Tier(up_to=Decimal("2000"), rate=Decimal("0.10")),
                Tier(up_to=None, rate=Decimal("0.20")),
            ]
        )
        # 1000*0.05 + 1000*0.10 + 500*0.20 = 50 + 100 + 100 = 250
        assert rule.commission(Decimal("2500")) == Decimal("250.00")

    def test_single_open_band_equals_flat(self):
        rule = Tiered([Tier(up_to=None, rate=Decimal("0.10"))])
        assert rule.commission(Decimal("4145")) == Decimal("414.50")

    def test_thresholds_must_ascend(self):
        with pytest.raises(ValueError):
            Tiered(
                [
                    Tier(up_to=Decimal("2000"), rate=Decimal("0.05")),
                    Tier(up_to=Decimal("1000"), rate=Decimal("0.10")),
                    Tier(up_to=None, rate=Decimal("0.20")),
                ]
            )

    def test_last_tier_must_be_open_ended(self):
        with pytest.raises(ValueError):
            Tiered([Tier(up_to=Decimal("1000"), rate=Decimal("0.05"))])


class TestRegistry:
    def test_blast_media_rule_from_clients_yaml(self):
        clients = load_clients()
        cfg = clients["blast_media"]
        rule = build_rule(cfg.rule)
        assert isinstance(rule, FlatRate)
        assert rule.commission(Decimal("1000")) == Decimal("100.0")
        assert cfg.target_low == Decimal("97000")
        assert cfg.target_high == Decimal("105000")
        assert cfg.presented_method == "blend_3_6"
        assert cfg.presented_rationale

    def test_unknown_rule_type_rejected(self):
        from commission_engine.rules.registry import RuleSpec

        with pytest.raises(ValueError):
            build_rule(RuleSpec(type="mystery", params={}))
