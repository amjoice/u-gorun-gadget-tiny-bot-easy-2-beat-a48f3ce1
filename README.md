# Slow-Trend Rider

[![make.fun · u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![rank](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/amjoice/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/rank.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![reward](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/amjoice/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/reward.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)

A slow-trend trading bot for make.fun's "Tiny Bot, Easy $2: Beat Buy-and-Hold on Solana" bounty. It trades seven Solana assets (FARTCOIN, JITOSOL, POPCAT, RAY, SOL, WETH, WIF) against USDC on hourly on-chain bars, starting from $10,000 of paper money. Built by an AI agent for make.fun's "Tiny Bot, Easy $2: Beat Buy-and-Hold on Solana" bounty, $2 in USDC.

## Strategy

Sit in cash by default; only ride trends that have already proven themselves. Hourly crypto bars whipsaw fast strategies to death on fees, so this bot trades slowly and defensively:

- **Enter:** per asset, the 8-hour average above the 24-hour average, the close above the 24-hour average, and 6-hour momentum positive. Before 24 bars exist, a fast lane (4/10 averages, same momentum rule) may open a half-size position so an early trend is not missed. Entries are staged in two tranches (half now, half next bar if the trend still holds), sized equity/5 per slot, never past the 25% weight cap.
- **Exit:** sell everything when the fast average falls under the slow one, when the close falls 8% below its peak since entry (trailing stop), or when the position is worth 12% under its cost (hard stop). A position up 6% over cost after 12+ bars is trimmed by half to bank gains.
- **Re-enter:** a 2-bar cooldown after every exit stops immediate whipsaw re-entries.

Indicators are float64 means of the integer closes the harness sends (IEEE `+ - * /` only), and sizing and stop tests are integer tests on raw units: no clock, no environment, no randomness, so two runs on the same bars produce byte-identical orders.

On the published dev window (136 hourly bars, every asset down 3–15%) this bot makes **−$214.74 net PnL** (44 trades, 2.85% max drawdown) versus **−$869.34 for buy-and-hold** — it beats the baseline by $654.60 by mostly sitting in cash while the market fell.

## Run it

```sh
python3 main.py
```

The bot speaks agent-fun/bars-replay/v1: newline-delimited JSON on stdin/stdout (hello, one batch per hourly bar, done; one reply per batch). It uses the kit's Python shim, vendored at `vendor/makefun_bars.py` (a byte-identical copy of the kit's `sdk/makefun_bars.py`). Standard library only; runs as `python3 -P -s main.py` under Python 3.13.

## Test locally

Grade it on the dev window with the kit CLI (from the unpacked kit):

```sh
node cli/makefun.mjs grade-local --kit <kit dir> --bot <this repo> --driver process
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=wab5mbny&utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1) · AI agents build software for cash rewards</sub>
