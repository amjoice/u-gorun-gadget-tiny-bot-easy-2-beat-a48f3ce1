"""Tiny Bot entry: slow-trend rider for hourly Solana bars (bars-replay/v1).

Strategy (long only, cash by default):
- Per symbol, track closes. Entry needs the 8-bar SMA above the 24-bar SMA,
  the close above the 24-bar SMA, and positive 6-bar momentum. Before 24 bars
  exist (cold start), a fast lane (4/10 SMA, same momentum rule) may open a
  half-size position so an early trend is not missed entirely.
- Entries are staged in two tranches (half now, half next bar if the trend
  still holds) and sized as equity/5 slots, never past the weight cap.
- Exit the whole position when the fast SMA falls under the slow SMA, when
  the close falls 8% under its peak since entry, or when the position is
  worth 12% under its cost. After 12+ bars, a position up 6% over cost is
  trimmed by half (at most once per 12 bars) to bank gains.
- A 2-bar cooldown after an exit prevents immediate re-entry whipsaws.

Indicators are float64 means of integer closes (IEEE +, -, *, / only, so the
same bars give the same orders); sizing and stop tests are integer tests on
the harness's raw units. No clock, no environment, no randomness: two runs
on the same bars produce byte-identical replies.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

FAST_BARS = 8
SLOW_BARS = 24
EARLY_FAST_BARS = 4
EARLY_SLOW_BARS = 10
MOM_BARS = 6
SLOTS = 5
COOLDOWN_BARS = 2
TRIM_AFTER_BARS = 12
MAX_SLIPPAGE_BPS = 500
# Trailing stop: exit at 92% of the peak close since entry.
TRAIL_NUM, TRAIL_DEN = 92, 100
# Hard stop: exit when worth 88% of cost.
STOP_NUM, STOP_DEN = 88, 100
# Profit trim: sell half when worth 106% of cost.
TRIM_NUM, TRIM_DEN = 106, 100


class Series:
    __slots__ = ("closes", "peak", "last_exit_seq", "entry_seq", "pending_add")

    def __init__(self):
        self.closes = []
        self.peak = 0
        self.last_exit_seq = -10**9
        self.entry_seq = -10**9
        self.pending_add = 0


series = {}


def sma(closes, span):
    window = closes[-span:] if len(closes) >= span else None
    if window is None:
        return None
    return sum(window) / span


def sell_order(sym, qty):
    return {"side": "sell", "symbol": sym, "qty": qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS}


def buy_order(sym, notional):
    return {"side": "buy", "symbol": sym,
            "notional_quote_units": notional,
            "max_slippage_bps": MAX_SLIPPAGE_BPS}


def on_batch(state, batch):
    seq = state.seq
    fresh = set()
    for bar in batch["bars"]:
        sym = bar["symbol"]
        s = series.get(sym)
        if s is None:
            s = Series()
            series[sym] = s
        s.closes.append(int(bar["c"]))
        fresh.add(sym)

    if state.warming_up:
        return []

    caps = state.hello["caps"]
    min_notional = int(state.hello["fees"]["min_notional_quote_units"])
    max_orders = caps["max_orders_per_bar"]
    symbols = [s["symbol"] for s in state.hello["symbols"]]

    sells = []
    sold = set()
    held = [sym for sym in symbols if sym in state.positions]

    # Exits and trims first.
    for sym in held:
        if sym not in fresh:
            continue
        s = series[sym]
        pos = state.positions[sym]
        close = int(state.latest[sym]["c"])
        if close > s.peak:
            s.peak = close
        fast = sma(s.closes, FAST_BARS)
        slow = sma(s.closes, SLOW_BARS)
        value = state.value(sym, pos.qty)
        exit_all = False
        if fast is not None and slow is not None and fast < slow:
            exit_all = True
        if s.peak > 0 and close * TRAIL_DEN <= s.peak * TRAIL_NUM:
            exit_all = True
        if pos.cost > 0 and value * STOP_DEN <= pos.cost * STOP_NUM:
            exit_all = True
        if exit_all:
            sells.append(sell_order(sym, pos.qty))
            sold.add(sym)
            s.last_exit_seq = seq
            s.peak = 0
            s.pending_add = 0
        elif (pos.cost > 0 and value * TRIM_DEN >= pos.cost * TRIM_NUM
              and seq - s.entry_seq >= TRIM_AFTER_BARS):
            half = pos.qty // 2
            if half > 0:
                sells.append(sell_order(sym, half))
                s.entry_seq = seq

    orders = list(sells[:max_orders])
    room = SLOTS - len(held) + len(sold)
    cash = state.cash

    # Second tranches for positions opened on an earlier bar.
    for sym in symbols:
        if len(orders) >= max_orders:
            break
        s = series.get(sym)
        if s is None or s.pending_add <= 0 or sym in sold:
            continue
        if sym not in state.positions or sym not in fresh:
            s.pending_add = 0
            continue
        fast = sma(s.closes, FAST_BARS)
        slow = sma(s.closes, SLOW_BARS)
        amt = s.pending_add
        s.pending_add = 0
        if fast is None or slow is None or fast <= slow:
            continue
        room_w = state.weight_room(sym)
        if amt > room_w:
            amt = room_w
        if amt > cash:
            amt = cash
        if amt < min_notional or amt <= 0:
            continue
        orders.append(buy_order(sym, amt))
        cash -= amt

    # New entries, strongest 6-bar momentum first (ties: symbol order).
    candidates = []
    for sym in symbols:
        if sym in state.positions or sym not in fresh:
            continue
        s = series[sym]
        if seq - s.last_exit_seq < COOLDOWN_BARS:
            continue
        closes = s.closes
        if len(closes) <= MOM_BARS:
            continue
        close = closes[-1]
        mom = close / closes[-1 - MOM_BARS] - 1
        if mom <= 0:
            continue
        frac_num, frac_den = 1, 1
        if len(closes) >= SLOW_BARS:
            fast = sma(closes, FAST_BARS)
            slow = sma(closes, SLOW_BARS)
            if fast is None or slow is None or not (fast > slow and close > slow):
                continue
        elif len(closes) >= EARLY_SLOW_BARS:
            fast = sma(closes, EARLY_FAST_BARS)
            slow = sma(closes, EARLY_SLOW_BARS)
            if fast is None or slow is None or not (fast > slow and close > slow):
                continue
            frac_num, frac_den = 1, 2
        else:
            continue
        candidates.append((-mom, sym, frac_num, frac_den))
    candidates.sort()

    equity = state.equity
    by_weight = caps["max_weight_bps"] * equity // 10000
    for _neg_mom, sym, frac_num, frac_den in candidates:
        if room <= 0 or len(orders) >= max_orders:
            break
        full = equity // SLOTS
        if full > by_weight:
            full = by_weight
        full = full * frac_num // frac_den
        if full > cash:
            full = cash
        if full < min_notional or full <= 0:
            break
        first = full // 2
        if first < min_notional:
            first = full
        orders.append(buy_order(sym, first))
        cash -= first
        room -= 1
        s = series[sym]
        s.entry_seq = seq
        s.peak = s.closes[-1]
        s.pending_add = full - first

    return orders


def main():
    makefun_bars.run(on_batch)


if __name__ == "__main__":
    main()
