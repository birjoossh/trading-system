"""
Accuracy tests for the option-pricing layer.

These check the maths against *independent oracles* rather than against
previously recorded output:
  - textbook Black-Scholes reference values,
  - exact analytic identities (put-call parity, delta relationships, symmetry
    of the normal CDF), which must hold for any correct implementation,
  - round-trips (price -> implied vol -> price).
"""

import datetime as dt

import numpy as np
import pytest

from unified_trading_platform.trading_core.strategy_engine.greeks_helper import (
    _norm_cdf_np,
    bs_delta,
    bs_delta_vec,
    bs_price,
    bs_price_vec,
    compute_iv_delta_for_chain,
    ensure_delta,
    iv_from_price_scalar,
    yearfrac,
)

# The CDF approximation (Abramowitz & Stegun 7.1.26) is accurate to ~1.5e-7,
# which propagates to roughly 1e-4 on a ~100-unit option price.
PRICE_TOL = 1e-3
CDF_TOL = 1e-6


class TestNormalCDF:
    def test_known_values(self):
        for x, expected in [
            (0.0, 0.5),
            (1.0, 0.8413447461),
            (-1.0, 0.1586552539),
            (1.96, 0.9750021049),
            (-1.96, 0.0249978951),
            (2.5758293035, 0.9950000000),
            (3.0, 0.9986501020),
        ]:
            assert _norm_cdf_np(np.array(x)) == pytest.approx(expected, abs=CDF_TOL)

    def test_symmetry_identity(self):
        """N(x) + N(-x) == 1 exactly, for every x."""
        xs = np.linspace(-5, 5, 201)
        assert np.allclose(_norm_cdf_np(xs) + _norm_cdf_np(-xs), 1.0, atol=1e-9)

    def test_monotonic_and_bounded(self):
        xs = np.linspace(-8, 8, 401)
        cdf = _norm_cdf_np(xs)
        assert np.all(np.diff(cdf) >= 0), "CDF must be non-decreasing"
        assert np.all(cdf >= 0) and np.all(cdf <= 1)


class TestBlackScholesReferenceValues:
    """Textbook case: S=100, K=100, T=1, r=5%, q=0, sigma=20%."""

    S, K, T, R, Q, SIGMA = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20

    def test_call_price(self):
        price = bs_price(self.S, self.K, self.T, self.R, self.Q, self.SIGMA, "C")
        assert price == pytest.approx(10.450583572185565, abs=PRICE_TOL)

    def test_put_price(self):
        price = bs_price(self.S, self.K, self.T, self.R, self.Q, self.SIGMA, "P")
        assert price == pytest.approx(5.573526022256971, abs=PRICE_TOL)

    def test_call_delta(self):
        delta = bs_delta(self.S, self.K, self.T, self.R, self.Q, self.SIGMA, "C")
        assert delta == pytest.approx(0.6368306511, abs=CDF_TOL * 10)

    def test_put_delta(self):
        delta = bs_delta(self.S, self.K, self.T, self.R, self.Q, self.SIGMA, "P")
        assert delta == pytest.approx(-0.3631693489, abs=CDF_TOL * 10)

    def test_ce_pe_aliases_are_accepted(self):
        """The engine passes NSE-style 'CE'/'PE' rather than 'C'/'P'."""
        assert bs_price(self.S, self.K, self.T, self.R, self.Q, self.SIGMA, "CE") == pytest.approx(
            bs_price(self.S, self.K, self.T, self.R, self.Q, self.SIGMA, "C")
        )
        assert bs_price(self.S, self.K, self.T, self.R, self.Q, self.SIGMA, "PE") == pytest.approx(
            bs_price(self.S, self.K, self.T, self.R, self.Q, self.SIGMA, "P")
        )


class TestAnalyticIdentities:
    """Identities that hold exactly for correct Black-Scholes, on a whole grid."""

    GRID = [
        (S, K, T, r, q, sigma)
        for S in (80.0, 100.0, 125.0)
        for K in (90.0, 100.0, 110.0)
        for T in (0.05, 0.5, 2.0)
        for r in (0.0, 0.06)
        for q in (0.0, 0.02)
        for sigma in (0.10, 0.35)
    ]

    def test_put_call_parity(self):
        """C - P == S*e^(-qT) - K*e^(-rT)."""
        for S, K, T, r, q, sigma in self.GRID:
            call = bs_price(S, K, T, r, q, sigma, "C")
            put = bs_price(S, K, T, r, q, sigma, "P")
            expected = S * np.exp(-q * T) - K * np.exp(-r * T)
            assert (call - put) == pytest.approx(expected, abs=1e-3), f"parity broken at {(S, K, T, r, q, sigma)}"

    def test_delta_difference_identity(self):
        """delta_call - delta_put == e^(-qT)."""
        for S, K, T, r, q, sigma in self.GRID:
            dc = bs_delta(S, K, T, r, q, sigma, "C")
            dp = bs_delta(S, K, T, r, q, sigma, "P")
            assert (dc - dp) == pytest.approx(np.exp(-q * T), abs=1e-5)

    def test_delta_bounds(self):
        for S, K, T, r, q, sigma in self.GRID:
            dc = bs_delta(S, K, T, r, q, sigma, "C")
            dp = bs_delta(S, K, T, r, q, sigma, "P")
            assert 0.0 <= dc <= 1.0
            assert -1.0 <= dp <= 0.0

    def test_price_never_below_intrinsic(self):
        """A European option is worth at least its discounted intrinsic value."""
        for S, K, T, r, q, sigma in self.GRID:
            call = bs_price(S, K, T, r, q, sigma, "C")
            put = bs_price(S, K, T, r, q, sigma, "P")
            assert call >= max(S * np.exp(-q * T) - K * np.exp(-r * T), 0.0) - 1e-3
            assert put >= max(K * np.exp(-r * T) - S * np.exp(-q * T), 0.0) - 1e-3
            assert call <= S * np.exp(-q * T) + 1e-3
            assert put <= K * np.exp(-r * T) + 1e-3

    def test_call_price_monotonic_in_spot(self):
        spots = np.linspace(50, 150, 40)
        prices = [bs_price(S, 100.0, 1.0, 0.05, 0.0, 0.2, "C") for S in spots]
        assert np.all(np.diff(prices) > 0)

    def test_price_monotonic_in_volatility(self):
        """Vega is positive: both calls and puts gain value with volatility."""
        vols = np.linspace(0.05, 1.0, 40)
        calls = [bs_price(100.0, 100.0, 1.0, 0.05, 0.0, v, "C") for v in vols]
        puts = [bs_price(100.0, 100.0, 1.0, 0.05, 0.0, v, "P") for v in vols]
        assert np.all(np.diff(calls) > 0)
        assert np.all(np.diff(puts) > 0)

    def test_call_delta_increases_with_spot(self):
        spots = np.linspace(60, 140, 40)
        deltas = [bs_delta(S, 100.0, 1.0, 0.05, 0.0, 0.2, "C") for S in spots]
        assert np.all(np.diff(deltas) > 0)

    def test_atm_delta_near_half(self):
        """A short-dated, zero-carry ATM call sits close to 0.50 delta."""
        delta = bs_delta(100.0, 100.0, 0.02, 0.0, 0.0, 0.2, "C")
        assert delta == pytest.approx(0.5, abs=0.01)


class TestVectorization:
    def test_vector_matches_scalar_prices(self):
        S = np.array([90.0, 100.0, 110.0, 120.0])
        K = np.array([100.0, 100.0, 105.0, 95.0])
        cp = np.array(["C", "P", "CE", "PE"])
        vec = bs_price_vec(S, K, 0.5, 0.06, 0.01, 0.25, cp)
        for i in range(len(S)):
            scalar = bs_price(float(S[i]), float(K[i]), 0.5, 0.06, 0.01, 0.25, str(cp[i]))
            assert float(vec[i]) == pytest.approx(scalar, abs=1e-9)

    def test_vector_matches_scalar_deltas(self):
        S = np.array([90.0, 100.0, 110.0])
        K = np.array([100.0, 100.0, 105.0])
        cp = np.array(["C", "P", "CE"])
        vec = bs_delta_vec(S, K, 0.5, 0.06, 0.01, 0.25, cp)
        for i in range(len(S)):
            scalar = bs_delta(float(S[i]), float(K[i]), 0.5, 0.06, 0.01, 0.25, str(cp[i]))
            assert float(vec[i]) == pytest.approx(scalar, abs=1e-9)

    def test_per_row_sigma_is_respected(self):
        """A vector of sigmas must price each row with its own sigma."""
        sigmas = np.array([0.10, 0.30])
        vec = bs_price_vec(np.array([100.0, 100.0]), np.array([100.0, 100.0]), 1.0, 0.05, 0.0, sigmas, "C")
        assert float(vec[0]) == pytest.approx(bs_price(100, 100, 1.0, 0.05, 0.0, 0.10, "C"), abs=1e-9)
        assert float(vec[1]) == pytest.approx(bs_price(100, 100, 1.0, 0.05, 0.0, 0.30, "C"), abs=1e-9)


class TestImpliedVolatility:
    @pytest.mark.parametrize("sigma", [0.08, 0.15, 0.22, 0.40, 0.75])
    @pytest.mark.parametrize("cp", ["C", "P"])
    def test_round_trip(self, sigma, cp):
        """price(sigma) -> iv -> price must return the original price."""
        S, K, T, r, q = 21600.0, 21700.0, 2.0 / 365.0, 0.06, 0.0
        price = bs_price(S, K, T, r, q, sigma, cp)
        iv = iv_from_price_scalar(S, K, T, r, q, cp, price)
        assert iv == pytest.approx(sigma, abs=1e-3)
        assert bs_price(S, K, T, r, q, iv, cp) == pytest.approx(price, abs=1e-2)

    def test_price_below_intrinsic_clamps_low(self):
        iv = iv_from_price_scalar(100.0, 50.0, 1.0, 0.05, 0.0, "C", 0.0)
        assert iv == pytest.approx(1e-6, abs=1e-9)

    def test_price_above_range_clamps_high(self):
        iv = iv_from_price_scalar(100.0, 100.0, 1.0, 0.05, 0.0, "C", 99.0)
        assert iv == pytest.approx(5.0, abs=1e-9)

    def test_monotonic_in_price(self):
        """A richer option implies a higher volatility."""
        S, K, T, r, q = 100.0, 100.0, 0.25, 0.05, 0.0
        ivs = [iv_from_price_scalar(S, K, T, r, q, "C", p) for p in (2.0, 4.0, 6.0, 8.0)]
        assert all(b > a for a, b in zip(ivs, ivs[1:]))


class TestChainGreeks:
    """compute_iv_delta_for_chain must recover the vol it was priced with."""

    def _synthetic_chain(self, S=21600.0, sigma=0.18, T_days=2):
        import pandas as pd

        now = dt.datetime(2024, 1, 2, 11, 0)
        expiry = now + dt.timedelta(days=T_days)
        T = yearfrac(now, expiry)
        rows = []
        for strike in np.arange(21400, 21801, 50.0):
            for cp in ("CE", "PE"):
                rows.append(
                    {
                        "strike": strike,
                        "option_type": cp,
                        "Close": bs_price(S, strike, T, 0.06, 0.0, sigma, cp),
                        "timestamp": now,
                    }
                )
        return pd.DataFrame(rows), now, expiry, sigma, S

    def test_recovers_input_volatility(self):
        chain, now, expiry, sigma, S = self._synthetic_chain()
        out = compute_iv_delta_for_chain(chain, S=S, expiry_dt=expiry, now_dt=now)
        # Deep-OTM options priced under `min_price` are floored, so only check
        # the strikes with real premium.
        meaningful = out[out["Close"] > 1.0]
        assert not meaningful.empty
        assert np.allclose(meaningful["IV"], sigma, atol=5e-3)

    def test_delta_matches_analytic(self):
        chain, now, expiry, sigma, S = self._synthetic_chain()
        out = compute_iv_delta_for_chain(chain, S=S, expiry_dt=expiry, now_dt=now)
        T = yearfrac(now, expiry)
        meaningful = out[out["Close"] > 1.0]
        for row in meaningful.itertuples():
            expected = bs_delta(S, row.Strike, T, 0.06, 0.0, sigma, row.option_type)
            assert row.Delta == pytest.approx(expected, abs=1e-2)

    def test_call_and_put_delta_signs(self):
        chain, now, expiry, _, S = self._synthetic_chain()
        out = compute_iv_delta_for_chain(chain, S=S, expiry_dt=expiry, now_dt=now)
        assert (out.loc[out["option_type"] == "CE", "Delta"] >= 0).all()
        assert (out.loc[out["option_type"] == "PE", "Delta"] <= 0).all()

    def test_ensure_delta_preserves_existing_column(self):
        chain, now, expiry, _, S = self._synthetic_chain()
        chain["Delta"] = 0.42
        out = ensure_delta(chain, S=S, expiry_dt=expiry, now_dt=now)
        assert (out["Delta"] == 0.42).all(), "existing Delta column must not be recomputed"

    def test_ensure_delta_computes_when_missing(self):
        chain, now, expiry, _, S = self._synthetic_chain()
        out = ensure_delta(chain, S=S, expiry_dt=expiry, now_dt=now)
        assert "Delta" in out.columns and out["Delta"].notna().any()

    def test_empty_chain_is_handled(self):
        import pandas as pd

        out = compute_iv_delta_for_chain(pd.DataFrame(), S=100.0, expiry_dt=dt.datetime(2024, 1, 4))
        assert out.empty


class TestYearFraction:
    def test_act_365_fixed(self):
        start = dt.datetime(2024, 1, 1)
        assert yearfrac(start, start + dt.timedelta(days=365)) == pytest.approx(1.0)
        assert yearfrac(start, start + dt.timedelta(days=1)) == pytest.approx(1.0 / 365.0)
        assert yearfrac(start, start + dt.timedelta(hours=12)) == pytest.approx(0.5 / 365.0)

    def test_negative_is_clamped_to_zero(self):
        start = dt.datetime(2024, 1, 10)
        assert yearfrac(start, start - dt.timedelta(days=5)) == 0.0
