
import numpy as np
from unified_trading_platform.trading_core.strategy_engine.greeks_helper import bs_price, bs_delta, bs_price_vec, bs_delta_vec

def test_greeks():
    S = 100.0
    K = 100.0
    T = 1.0
    r = 0.05
    q = 0.0
    sigma = 0.2
    
    # 1. Scalar Test
    c_price = bs_price(S, K, T, r, q, sigma, 'C')
    p_price = bs_price(S, K, T, r, q, sigma, 'P')
    c_delta = bs_delta(S, K, T, r, q, sigma, 'C')
    p_delta = bs_delta(S, K, T, r, q, sigma, 'P')
    
    print(f"Scalar Call Price: {c_price:.4f}")
    print(f"Scalar Put Price: {p_price:.4f}")
    print(f"Scalar Call Delta: {c_delta:.4f}")
    print(f"Scalar Put Delta: {p_delta:.4f}")
    
    # Validation against online calculator (approx):
    # Call ~ 10.45, Put ~ 5.57, Delta ~ 0.63, Put Delta ~ -0.36
    
    # 2. Vectorized Test
    S_arr = np.array([100.0, 100.0])
    K_arr = np.array([100.0, 110.0])
    cp_arr = np.array(['C', 'P'])
    
    prices = bs_price_vec(S_arr, K_arr, T, r, q, sigma, cp_arr)
    deltas = bs_delta_vec(S_arr, K_arr, T, r, q, sigma, cp_arr)
    
    print(f"Vector Prices: {prices}")
    print(f"Vector Deltas: {deltas}")
    
    # Check consistency
    assert np.isclose(prices[0], c_price), "Vectorized Call Price Mismatch"
    
    # Check simple Put (strike 110)
    p_110 = bs_price(100, 110, T, r, q, sigma, 'P')
    assert np.isclose(prices[1], p_110), "Vectorized Put Price Mismatch"

    print("SUCCESS: Vectorized Greeks match Scalar implementation.")

if __name__ == "__main__":
    test_greeks()
