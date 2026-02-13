
import datetime as dt
import pandas as pd
from unified_trading_platform.trading_core.config.config import settings
from unified_trading_platform.trading_core.strategy_engine.strategy_utils import weekly_expiry_for
from unified_trading_platform.trading_core.strategy_engine.strikes import _infer_expiry_dt

def test_exchange_config_load():
    print("Testing Config Loading...")
    nse_conf = settings.get_exchange_config("NSE")
    print(f"NSE Config: {nse_conf}")
    assert nse_conf["currency"] == "INR"
    assert nse_conf["trading_hours"]["end"] == "15:30"
    
    nyse_conf = settings.get_exchange_config("NYSE")
    print(f"NYSE Config: {nyse_conf}")
    assert nyse_conf["currency"] == "USD"
    assert nyse_conf["trading_hours"]["end"] == "16:00"
    print("✓ Config matches expected values.")

def test_expiry_logic():
    print("\nTesting Expiry Logic...")
    # Test NSE logic (from config)
    # switch date 2025-09-01. Before: Thu(3), After: Tue(1)
    
    # Date before switch: 2024-01-01 (Monday) -> Should be Thu 2024-01-04
    d1 = dt.date(2024, 1, 1)
    exp1 = weekly_expiry_for(d1, exchange="NSE")
    print(f"2024-01-01 (Mon) -> Expiry: {exp1} (Weekday: {exp1.weekday()})")
    assert exp1.weekday() == 3 # Thursday
    
    # Date after switch: 2025-09-02 (Tuesday) -> Should be Tue 2025-09-02 (Today)
    d2 = dt.date(2025, 9, 2)
    exp2 = weekly_expiry_for(d2, exchange="NSE")
    print(f"2025-09-02 (Tue) -> Expiry: {exp2} (Weekday: {exp2.weekday()})")
    assert exp2.weekday() == 1 # Tuesday
    
    # Test NYSE logic (from config default Fri=4)
    # 2024-01-01 (Mon) -> Should be Fri 2024-01-05
    d3 = dt.date(2024, 1, 1)
    exp3 = weekly_expiry_for(d3, exchange="NYSE")
    print(f"NYSE 2024-01-01 (Mon) -> Expiry: {exp3} (Weekday: {exp3.weekday()})")
    assert exp3.weekday() == 4 # Friday
    print("✓ Expiry logic respects config.")

def test_infer_expiry_time():
    print("\nTesting Infer Expiry Time...")
    # Mock dataframe
    df = pd.DataFrame({"expiry": ["2024-01-04"]})
    
    # Test NSE (15:30)
    dt_nse = _infer_expiry_dt(df, {}, exchange="NSE")
    print(f"NSE Inferred: {dt_nse}")
    assert dt_nse.hour == 15 and dt_nse.minute == 30
    
    # Test NYSE (16:00)
    dt_nyse = _infer_expiry_dt(df, {}, exchange="NYSE")
    print(f"NYSE Inferred: {dt_nyse}")
    assert dt_nyse.hour == 16 and dt_nyse.minute == 0
    print("✓ Inferred time respects exchange config.")

def test_default_exchange():
    print("\nTesting Default Exchange Resolution...")
    # Should resolve to NSE from config
    d = dt.date(2025, 9, 2)
    # Default is NSE, so Tuesday
    exp = weekly_expiry_for(d, exchange=None)
    print(f"Default Expiry for {d}: {exp} (Weekday: {exp.weekday()})")
    assert exp.weekday() == 1 # Tuesday (NSE rule)
    print("✓ Default exchange worked.")

if __name__ == "__main__":
    test_exchange_config_load()
    test_expiry_logic()
    test_infer_expiry_time()
    test_default_exchange()
    print("\nALL TESTS PASSED")
