"""Tests for pricing calculation engine."""
import pytest
from vpn_bot import pricing


class TestPricing:
    """Test price calculation logic."""

    def test_prebuilt_price(self):
        """Test prebuilt package pricing."""
        plan = {"price": 10.50}
        assert pricing.calculate_prebuilt_price(plan) == 10.50

    def test_pergb_base_price(self):
        """Test per-GB base pricing calculation."""
        pricing_config = {
            "price_per_gb": 2.0,
            "additional_user_price": 1.0,
        }
        total, breakdown = pricing.calculate_pergb_price(
            volume_gb=10,
            duration_months=1,
            num_users=1,
            pricing=pricing_config
        )
        assert total == 20.0
        assert breakdown["base_volume"] == 20.0
        assert "extra_months" not in breakdown
        assert "extra_users" not in breakdown

    def test_pergb_with_extra_months_percent(self):
        """Test per-GB pricing with percentage-based extra months."""
        pricing_config = {
            "price_per_gb": 2.0,
            "extra_month_price_percent": 10.0,
            "additional_user_price": 0.0,
        }
        total, breakdown = pricing.calculate_pergb_price(
            volume_gb=10,
            duration_months=3,
            num_users=1,
            pricing=pricing_config
        )
        # Base: 10 GB * 2.0 = 20
        # Extra months: 20 * 10% * 2 = 4
        # Total: 24
        assert total == 24.0
        assert breakdown["base_volume"] == 20.0
        assert breakdown["extra_months"] == 4.0

    def test_pergb_with_extra_months_absolute(self):
        """Test per-GB pricing with absolute extra month pricing."""
        pricing_config = {
            "price_per_gb": 2.0,
            "extra_month_price_absolute": 5.0,
            "additional_user_price": 0.0,
        }
        total, breakdown = pricing.calculate_pergb_price(
            volume_gb=10,
            duration_months=3,
            num_users=1,
            pricing=pricing_config
        )
        # Base: 20
        # Extra months: 5 * 2 = 10
        # Total: 30
        assert total == 30.0
        assert breakdown["extra_months"] == 10.0

    def test_pergb_with_extra_users(self):
        """Test per-GB pricing with additional users."""
        pricing_config = {
            "price_per_gb": 2.0,
            "additional_user_price": 3.0,
        }
        total, breakdown = pricing.calculate_pergb_price(
            volume_gb=10,
            duration_months=1,
            num_users=3,
            pricing=pricing_config
        )
        # Base: 20
        # Extra users: 3 * 2 = 6
        # Total: 26
        assert total == 26.0
        assert breakdown["extra_users"] == 6.0

    def test_pergb_complex_scenario(self):
        """Test per-GB pricing with all features combined."""
        pricing_config = {
            "price_per_gb": 1.5,
            "extra_month_price_percent": 20.0,
            "additional_user_price": 2.5,
        }
        total, breakdown = pricing.calculate_pergb_price(
            volume_gb=50,
            duration_months=4,
            num_users=2,
            pricing=pricing_config
        )
        # Base: 50 * 1.5 = 75
        # Extra months: 75 * 20% * 3 = 45
        # Extra users: 2.5 * 1 = 2.5
        # Total: 122.5
        assert total == 122.5
        assert breakdown["base_volume"] == 75.0
        assert breakdown["extra_months"] == 45.0
        assert breakdown["extra_users"] == 2.5

    def test_validate_pricing_constraints_valid(self):
        """Test pricing constraint validation with valid input."""
        pricing_config = {
            "min_months": 1,
            "max_months": 6,
        }
        is_valid, error = pricing.validate_pricing_constraints(
            volume_gb=50,
            duration_months=3,
            pricing=pricing_config
        )
        assert is_valid is True
        assert error is None

    def test_validate_pricing_constraints_below_min(self):
        """Test pricing constraint validation below minimum."""
        pricing_config = {
            "min_months": 2,
            "max_months": 6,
        }
        is_valid, error = pricing.validate_pricing_constraints(
            volume_gb=50,
            duration_months=1,
            pricing=pricing_config
        )
        assert is_valid is False
        assert "Minimum duration is 2 months" in error

    def test_validate_pricing_constraints_above_max(self):
        """Test pricing constraint validation above maximum."""
        pricing_config = {
            "min_months": 1,
            "max_months": 3,
        }
        is_valid, error = pricing.validate_pricing_constraints(
            volume_gb=50,
            duration_months=6,
            pricing=pricing_config
        )
        assert is_valid is False
        assert "Maximum duration is 3 months" in error

    def test_validate_pricing_constraints_zero_volume(self):
        """Test pricing constraint validation with zero volume."""
        pricing_config = {
            "min_months": 1,
            "max_months": 6,
        }
        is_valid, error = pricing.validate_pricing_constraints(
            volume_gb=0,
            duration_months=3,
            pricing=pricing_config
        )
        assert is_valid is False
        assert "Volume must be greater than 0" in error

    def test_format_price_breakdown_en(self):
        """Test price breakdown formatting in English."""
        breakdown = {
            "base_volume": 20.0,
            "extra_months": 4.0,
            "extra_users": 3.0,
            "total": 27.0,
        }
        formatted = pricing.format_price_breakdown(breakdown, lang="en")
        assert "Base volume: $20.00" in formatted
        assert "Extra months: $4.00" in formatted
        assert "Extra users: $3.00" in formatted
        assert "Total: $27.00" in formatted

    def test_format_price_breakdown_fa(self):
        """Test price breakdown formatting in Persian."""
        breakdown = {
            "base_volume": 20.0,
            "total": 20.0,
        }
        formatted = pricing.format_price_breakdown(breakdown, lang="fa")
        assert "قیمت پایه: 20.00" in formatted
        assert "جمع کل: 20.00" in formatted
