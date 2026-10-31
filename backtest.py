"""
Backtester V12 - Corregido con DataFeed.IEX para cuentas Paper y Free de Alpaca
"""
import pandas as pd
from datetime import datetime, timedelta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

from config import Config
try:
    from strategies import STRATEGIES
except ImportError:
    class DummyStrategy:
        def analyze(self, df): return {}
    STRATEGIES = [DummyStrategy()]


class Backtester:
    def __init__(self):
        self.client = StockHistoricalDataClient(Config.API_KEY, Config.SECRET_KEY)
        self.strategies = STRATEGIES

    def get_history(self, symbol, months=6):
        try:
            end = datetime.now()
            start = end - timedelta(days=30 * months)
            
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
                limit=1000,
                feed=DataFeed.IEX
            )
            bars = self.client.get_stock_bars(request).df
            if bars.empty:
                return pd.DataFrame()
            if isinstance(bars.index, pd.MultiIndex):
                bars = bars.xs(symbol, level=0)
            return bars
        except Exception as e:
            print(f"Error descargando historico de {symbol}: {e}")
            return pd.DataFrame()

    def run_symbol(self, symbol, months=6):
        df = self.get_history(symbol, months)
        if df.empty or len(df) < 50:
            return None
            
        trades = []
        start_idx = min(30, len(df) - 10)
        
        for i in range(start_idx, len(df) - 1):
            window = df.iloc[:i + 1]
            window_renamed = window.rename(
                columns={"open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"}
            )
            votes = []
            for strat in self.strategies:
                try:
                    res = strat.analyze(window_renamed)
                    if res and res.get("signal"):
                        votes.append(res)
                except Exception:
                    continue
            if not votes:
                continue

            longs = [v for v in votes if v.get("signal") == "long"]
            shorts = [v for v in votes if v.get("signal") == "short"]
            decision = None
            if longs and len(longs) >= len(shorts):
                decision = max(longs, key=lambda x: x.get("confidence", 0))
            elif shorts:
                decision = max(shorts, key=lambda x: x.get("confidence", 0))

            if not decision or decision.get("confidence", 0) < 65:
                continue

            entry = float(window_renamed["close"].iloc[-1])
            atr = decision.get("atr", entry * 0.015)
            sl_dist = atr * 1.5

            if decision["signal"] == "long":
                sl = entry - sl_dist
                tp = entry + (sl_dist * 2.2)
                future = df.iloc[i + 1:i + 11]
                win = False
                for _, row in future.iterrows():
                    if row["high"] >= tp:
                        win = True
                        break
                    if row["low"] <= sl:
                        break
            else:
                sl = entry + sl_dist
                tp = entry - (sl_dist * 2.2)
                future = df.iloc[i + 1:i + 11]
                win = False
                for _, row in future.iterrows():
                    if row["low"] <= tp:
                        win = True
                        break
                    if row["high"] >= sl:
                        break

            trades.append({"win": win})

        if not trades:
            return {"symbol": symbol, "trades": 0, "wins": 0, "losses": 0, "winrate": 0.0, "profit_factor_est": 0.0}

        wins = sum(1 for t in trades if t["win"])
        winrate = (wins / len(trades) * 100) if trades else 0
        losses = len(trades) - wins
        pf = round((wins * 2.2) / max(1, losses), 2)

        return {
            "symbol": symbol,
            "trades": len(trades),
            "wins": wins,
            "losses": losses,
            "winrate": round(winrate, 1),
            "profit_factor_est": pf
        }

    def run_all(self):
        print(f"\n=== BACKTEST INICIAL ({Config.BACKTEST_MONTHS} MESES) [FEED IEX] ===")
        results = []
        for sym in Config.SYMBOLS:
            r = self.run_symbol(sym, Config.BACKTEST_MONTHS)
            if r and r["trades"] > 0:
                results.append(r)
                print(f"  -> {sym}: {r['trades']} trades | WinRate {r['winrate']}% | Factor Profit {r['profit_factor_est']}")
            else:
                print(f"  -> {sym}: Sin trades significativos en periodo.")

        if results:
            total_trades = sum(r["trades"] for r in results)
            avg_wr = sum(r["winrate"] for r in results) / len(results)
            print(f"\nTOTAL BACKTEST: {total_trades} trades | WinRate promedio: {avg_wr:.1f}%\n")
        return results


if __name__ == "__main__":
    Config.validate()
    bt = Backtester()
    bt.run_all()
