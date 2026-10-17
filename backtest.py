import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from datetime import datetime, timedelta
from config import Config
from strategies import STRATEGIES

class Backtester:
    def __init__(self):
        self.client = StockHistoricalDataClient(Config.API_KEY, Config.SECRET_KEY)
        self.strategies = STRATEGIES

    def get_history(self, symbol, months=6):
        end = datetime.now()
        start = end - timedelta(days=30*months)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            feed=DataFeed.IEX,
            start=start,
            end=end,
            limit=10000
        )
        bars = self.client.get_stock_bars(request).df
        if bars.empty:
            return pd.DataFrame()
        if isinstance(bars.index, pd.MultiIndex):
            bars = bars.xs(symbol, level=0)
        return bars

    def run_symbol(self, symbol, months=6):
        df = self.get_history(symbol, months)
        if len(df) < 250:
            return None
        trades = []
        for i in range(200, len(df)-1):
            window = df.iloc[:i+1]
            window_renamed = window.rename(columns={"open":"open","high":"high","low":"low","close":"close","volume":"volume"})
            votes = []
            for strat in self.strategies:
                try:
                    res = strat.analyze(window_renamed)
                    if res.get("signal"):
                        votes.append(res)
                except:
                    continue
            if not votes:
                continue
            longs = [v for v in votes if v['signal']=='long']
            shorts = [v for v in votes if v['signal']=='short']
            decision = None
            if longs and len(longs) >= len(shorts):
                decision = max(longs, key=lambda x: x['confidence'])
            elif shorts:
                decision = max(shorts, key=lambda x: x['confidence'])
            if not decision or decision['confidence'] < 70:
                continue
            entry = window_renamed['close'].iloc[-1]
            atr = decision.get('atr', entry*0.015)
            sl_dist = atr * 1.5
            if decision['signal'] == 'long':
                sl = entry - sl_dist
                tp = entry + sl_dist*2.5
                future = df.iloc[i+1:i+11]
                win = False
                for _, row in future.iterrows():
                    if row['high'] >= tp:
                        win = True
                        break
                    if row['low'] <= sl:
                        break
            else:
                sl = entry + sl_dist
                tp = entry - sl_dist*2.5
                future = df.iloc[i+1:i+11]
                win = False
                for _, row in future.iterrows():
                    if row['low'] <= tp:
                        win = True
                        break
                    if row['high'] >= sl:
                        break
            trades.append({"win": win})
        if not trades:
            return {"symbol": symbol, "trades":0}
        wins = sum(1 for t in trades if t['win'])
        winrate = wins/len(trades)*100 if trades else 0
        return {
            "symbol": symbol,
            "trades": len(trades),
            "wins": wins,
            "losses": len(trades)-wins,
            "winrate": round(winrate,1),
            "profit_factor_est": round((wins*2.5)/(max(1,(len(trades)-wins))),2)
        }

    def run_all(self):
        print(f"\n=== BACKTEST {Config.BACKTEST_MONTHS} MESES ===")
        results = []
        for sym in Config.SYMBOLS:
            print(f"Backtesting {sym}...")
            r = self.run_symbol(sym, Config.BACKTEST_MONTHS)
            if r:
                results.append(r)
                print(f"  -> {r['trades']} trades | WR {r.get('winrate',0)}% | PF {r.get('profit_factor_est',0)}")
        if results:
            total_trades = sum(r['trades'] for r in results)
            avg_wr = sum(r.get('winrate',0) for r in results)/len(results) if results else 0
            print(f"\nTOTAL: {total_trades} trades | WinRate promedio {avg_wr:.1f}%")
        return results

if __name__ == "__main__":
    Config.validate()
    bt = Backtester()
    bt.run_all()
