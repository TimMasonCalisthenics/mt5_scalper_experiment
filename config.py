"""
Configuration - Edit these settings before running
"""

# ─── MT5 CONNECTION ────────────────────────────────────────────────
MT5_CONFIG = {
    "login": 433730614,          # Your MT5 account number
    "password": "Timmy_3281", # Your MT5 password
    "server": "Exness-MT5Trial7",  # e.g. "ICMarkets-Demo"
    "path": r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe",  # MT5 path
    "timeout": 60000,
}

# ─── DEFAULT TRADING SETTINGS ──────────────────────────────────────
TRADING_CONFIG = {
    "symbol": "XAUUSDm",
    "timeframe": "M30",           # M1, M5, M15, M30, H1
    "lot_size": 0.10,
    "max_open_trades": 5,
    "max_daily_loss_pct": 3.0,   # Stop trading if daily loss > 3%
    "max_daily_profit_pct": 5.0, # Stop trading if daily profit > 5%
}

# ─── RISK MANAGEMENT ───────────────────────────────────────────────
# NOTE: Exness XAUUSD: 1000 points = $1 USD per lot (10x other brokers)
RISK_CONFIG = {
    "stop_loss_pips": 200,         # 500 points = $0.05 per 0.10 lot (Exness)
    "take_profit_pips": 400,      # 1000 points = $0.10 per 0.10 lot (2:1 ratio)
    "trailing_stop_pips": 100,     # Move stop after 300 points profit
    "use_trailing_stop": True,
    "use_atr_stops": True,         # Dynamic stops based on ATR
    "atr_sl_multiplier": 1.5,      # SL = ATR * 1.5 (Exness adjusted)
    "atr_tp_multiplier": 3.0,      # TP = ATR * 3.0 (maintains 2:1 ratio)
    "min_sl_pips": 200,            # Minimum stop loss (200 points = $0.02 per 0.10 lot)
    "max_sl_pips": 1000,           # Maximum stop loss (1000 points = $0.10 per 0.10 lot)
    "risk_per_trade_pct": 0.5,     # 0.5% of balance per trade
    "auto_lot_sizing": True,       # Calculate lot from risk %
    "magic_number": 20240101,      # Unique ID for bot's trades
}

# ─── SCALPING STRATEGY ─────────────────────────────────────────────
STRATEGY_CONFIG = {
    "ema_fast": 5,               # 5-period for trend detection
    "ema_slow": 13,              # 13-period for confirmation
    "rsi_period": 14,
    "rsi_overbought": 65,        # Entry on momentum pullback
    "rsi_oversold": 35,
    "bb_period": 20,             # Standard 20-period bands
    "bb_std": 2.0,               # Standard 2.0 deviation
    "stoch_k": 5,
    "stoch_d": 3,
    "stoch_smooth": 3,
    "atr_period": 14,
    "min_spread_pips": 10,        # Skip if spread > 10 points (Exness spreads ~5-15 pts)
    "max_spread_pips": 10000,        # Trade all spread range
    "min_atr_threshold": 50,      # Minimum ATR (50+ points for volatility)
    "trade_on_news": False,      # Skip trades during high-impact news
    "require_all_confirmations": False,  # Allow 3+ confirmations (NEW)
}

# ─── SESSIONS (UTC times) ──────────────────────────────────────────
SESSION_CONFIG = {
    "trade_london": True,        # 07:00–16:00 UTC
    "trade_new_york": True,      # 12:00–21:00 UTC
    "trade_asian": False,        # 00:00–09:00 UTC
    "avoid_news_minutes": 30,    # Minutes before/after high-impact news
}

# ─── TELEGRAM ALERTS ───────────────────────────────────────────────
TELEGRAM_CONFIG = {
    "enabled": False,
    "bot_token": "YOUR_BOT_TOKEN",  # From @BotFather
    "chat_id": "YOUR_CHAT_ID",      # Your Telegram chat ID
    "send_on_open": True,
    "send_on_close": True,
    "send_on_error": True,
    "send_daily_summary": True,
    "summary_time": "21:00",        # UTC
}

# ─── EMAIL ALERTS ──────────────────────────────────────────────────
EMAIL_CONFIG = {
    "enabled": False,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "your@gmail.com",
    "sender_password": "your_app_password",  # Gmail App Password
    "recipient_email": "your@gmail.com",
    "send_on_open": False,
    "send_on_close": True,
    "send_on_error": True,
    "send_daily_summary": True,
}

# ─── DATABASE ──────────────────────────────────────────────────────
DB_CONFIG = {
    "path": "data/trades.db",
    "log_all_ticks": False,      # Heavy on disk space
    "log_signals": True,
}

# ─── BACKTEST ──────────────────────────────────────────────────────
BACKTEST_CONFIG = {
    "default_symbol": "XAUUSDm",
    "default_timeframe": "M30",
    "default_start": "2024-01-01",
    "default_end": "2024-12-31",
    "initial_balance": 10000.0,
    "commission_per_lot": 7.0,   # USD per lot round-trip
    "slippage_pips": 0.5,
}

# ─── DISPLAY ───────────────────────────────────────────────────────
UI_CONFIG = {
    "theme": "dark",             # dark / light
    "refresh_interval_ms": 1000, # GUI refresh rate
    "chart_candles": 100,        # Candles to show on chart
    "show_indicators": True,
}