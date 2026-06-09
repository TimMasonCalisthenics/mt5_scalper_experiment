# MT5 Scalper - XAUUSD Optimization Guide

## Problem Identified
Your bot was hitting **Stop Loss before Take Profit** because:
- **Old SL**: 1000 pips (100 points) = **WAY too wide** for scalping
- **Old TP**: 1300 pips = only 1.3:1 reward/risk ratio
- **Strategy**: Timeframes too slow (EMA 5/20) for micro-movements

---

## ✅ Changes Made

### 1. **Risk Management Config** (`config.py`)

#### Stop Loss & Take Profit (TIGHTENED)
```python
OLD:  SL = 1000 pips  |  TP = 1300 pips  → 1.3:1 ratio  ❌
NEW:  SL = 20 pips    |  TP = 40 pips    → 2:1 ratio     ✅
```

**Why 20/40 pips?**
- For XAUUSD: 20 pips = 2 points (not 100!)
- Faster TP hits → More winning trades
- Tighter risk containment

#### ATR-Based Dynamic Stops (NEW)
```python
"use_atr_stops": True,        # Enable dynamic adjustment
"atr_sl_multiplier": 1.5,     # SL = ATR × 1.5
"atr_tp_multiplier": 3.0,     # TP = ATR × 3.0
"min_sl_pips": 15,            # Floor at 15 pips
"max_sl_pips": 50,            # Ceiling at 50 pips
```

**Benefits:**
- Adapts to market volatility automatically
- Wide spread/news events → wider stops
- Calm periods → tighter stops
- Prevents SL whipsaws

#### Risk Per Trade (REDUCED)
```python
OLD:  risk_per_trade_pct = 1.0%   (larger trades)
NEW:  risk_per_trade_pct = 0.5%   (smaller, more consistent)
```

---

### 2. **Scalping Strategy Config** (`config.py`)

#### Faster Indicators (for M1 scalping)
```python
"ema_fast": 3,      # OLD: 5   → Quicker trend detection
"ema_slow": 10,     # OLD: 20  → Faster filtering
"bb_period": 15,    # OLD: 20  → Tighter Bollinger Bands
"bb_std": 1.5,      # OLD: 2.0 → Closer to midline
```

#### Aggressive Entry Levels
```python
"rsi_overbought": 65,   # OLD: 70  → Enter earlier on momentum
"rsi_oversold": 35,     # OLD: 30  → Enter earlier on dips
```

#### Strict Spread Requirements
```python
"max_spread_pips": 1.0  # OLD: 10000  → Only trade tight spreads
```

**Why these changes?**
- Gold scalping needs **tight, responsive signals**
- Slower EMAs miss micro-trends
- Stricter spreads = real opportunities only

---

### 3. **Bot Engine Integration** (`core/bot_engine.py`)

#### ATR-Based Stop Calculation
The bot now:
1. ✅ Extracts ATR from signal indicators
2. ✅ Passes ATR to `calculate_sl_tp()`
3. ✅ Automatically uses ATR-based or fixed stops
4. ✅ Recalculates lot size based on **actual** SL distance

**Code flow:**
```
Generate Signal (includes ATR)
    ↓
Extract ATR from details
    ↓
Pass to calculate_sl_tp()
    ↓
Use ATR multipliers OR fallback to fixed pips
    ↓
Calculate lot size from actual SL distance
```

---

### 4. **Risk Manager Enhancement** (`core/risk_manager.py`)

New methods for dynamic stops:
- `_calculate_atr_based_sl()` - Volatility-aware SL
- `_calculate_atr_based_tp()` - Ensures 2:1+ reward ratio

Automatic fallback: If ATR fails → uses fixed pip values

---

## 📊 Expected Improvements

| Metric | Old Strategy | New Strategy | Impact |
|--------|--------------|--------------|--------|
| **SL Size** | 100 pips | 15-50 pips | 🟢 3-6x tighter |
| **TP Size** | 130 pips | 30-100 pips | 🟢 More achievable |
| **Risk/Reward** | 1.3:1 | 2:1 to 3:1 | 🟢 Better ratio |
| **Entry Speed** | Slow (EMA 5/20) | Fast (EMA 3/10) | 🟢 Quicker signals |
| **False Signals** | High | Medium | 🟡 Quality focus |
| **Spread Impact** | Low priority | High priority | 🟢 Only tight spreads |

---

## 🎯 Testing Recommendations

### 1. **Backtest First**
```bash
# In backtester, run:
- Symbol: XAUUSDm
- Timeframe: M1
- Period: Last 2 weeks (volatile data)
- Focus on: SL vs TP frequency ratio
```

### 2. **Monitor These Metrics**
- **Win Rate**: Target 50-60% (scalping)
- **SL Hit vs TP Hit**: Should be roughly equal now
- **Avg Profit/Loss**: Target 1.5-2x per winner
- **Daily P&L**: Should be more consistent

### 3. **Live Trading Checklist**
- [ ] Test with small lot size (0.05)
- [ ] Monitor spread quality (Exness spreads on XAU?)
- [ ] Track first 100 trades before scaling up
- [ ] Verify ATR calculations are correct
- [ ] Check trailing stop execution

---

## 🔧 Advanced Tuning (If Needed)

### If Still Hitting SL Too Often:
```python
# Option 1: Tighter signals
"ema_fast": 2,           # Even faster
"require_all_confirmations": True  # Need all 6 indicators

# Option 2: Wider stops (only in high volatility)
"atr_sl_multiplier": 2.0   # SL = ATR × 2.0
"min_sl_pips": 20          # Floor at 20 pips
```

### If TP Takes Too Long:
```python
# Reduce TP targets
"take_profit_pips": 30  # From 40
"atr_tp_multiplier": 2.5  # From 3.0

# Or increase position management:
"use_trailing_stop": True
"trailing_stop_pips": 8   # Trail every 8 pips
```

### If Spread Too Wide (Exness Issue):
```python
# Switch to lower timeframe confirmations
"trade_london": True   # Use London session (tighter spreads)
"trade_new_york": True # Use NY overlap (tight spreads)
"trade_asian": False   # Skip Asian (wide spreads)
```

---

## 📈 Performance Expectations

**Before Optimization:**
- ❌ SL hits before TP regularly
- ❌ Wins too small, losses too large  
- ❌ Frustrating whipsaws

**After Optimization:**
- ✅ SL and TP both achievable
- ✅ Better 2:1 risk/reward ratio
- ✅ Fewer false signals (quality focus)
- ✅ Fewer whipsaws (ATR adapts)

---

## ⚙️ Configuration Summary

**Key Parameter Changes:**
```python
# Risk Management
stop_loss_pips: 20        # ← 1000  (50x tighter!)
take_profit_pips: 40      # ← 1300  (33x tighter!)
use_atr_stops: True       # ← NEW (adaptive)
risk_per_trade_pct: 0.5   # ← 1.0  (half risk)

# Strategy Indicators  
ema_fast: 3               # ← 5     (faster)
ema_slow: 10              # ← 20    (faster)
bb_period: 15             # ← 20    (tighter bands)
rsi_overbought: 65        # ← 70    (earlier entry)
max_spread_pips: 1.0      # ← 10000 (strict spreads)
```

---

## ✅ Next Steps

1. **Verify** ATR calculations in the logs
2. **Backtest** with new config for 500+ trades
3. **Monitor** first 50 live trades for signal quality
4. **Adjust** ATR multipliers based on results
5. **Scale up** lot size only after proven win rate

**Questions?** Check the scalping strategy docs or risk manager code for detailed logic.
