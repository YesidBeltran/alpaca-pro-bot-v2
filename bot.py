"""
Alpaca Pro Bot V2 - Compatible con Render FREE Web Service
"""
import time, os, threading, traceback
import pandas as pd
from datetime import datetime
from flask import Flask

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

from config import Config
from risk_manager import RiskManager
from strategies import STRATEGIES
from telegram_journal import TelegramJournal
from backtest import Backtester

app = Flask(__name__)

@app.route("/")
def home():
    return "Alpaca Pro Bot V2 - Running 24/7 | Status: OK"

@app.route("/health")
def health():
    return {"status": "ok", "bot": "running"}

class TradingBrain:
    def __init__(self):
        Config.validate()
        self.trading_client = TradingClient(Config.API_KEY, Config.SECRET_KEY, paper=True)
        self.data_client = StockHistoricalDataClient(Config.API_KEY, Config.SECRET_KEY)
        self.risk = RiskManager(Config)
        self.telegram = TelegramJournal(Config.TELEGRAM_TOKEN, Config.TELEGRAM_CHAT_ID)
        print(f"[INIT] Alpaca PAPER conectado | Symbols: {Config.SYMBOLS} | Telegram: {'ON' if self.telegram.enabled else 'OFF'}", flush=True)

    def get_bars(self, symbol, limit=300):
        try:
            tf = TimeFrame.Minute if Config.TIMEFRAME == "15Min" else TimeFrame.Hour
            request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, limit=limit)
            bars = self.data_client.get_stock_bars(request).df
            if bars.empty:
                return pd.DataFrame()
            if isinstance(bars.index, pd.MultiIndex):
                bars = bars.xs(symbol, level=0)
            bars = bars.rename(columns={"open":"open","high":"high","low":"low","close":"close","volume":"volume"})
            if Config.TIMEFRAME == "15Min":
                bars = bars.resample("15min").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
            return bars
        except Exception as e:
            print(f"Error barras {symbol}: {e}", flush=True)
            return pd.DataFrame()

    def think(self, symbol):
        df = self.get_bars(symbol)
        if df.empty or len(df) < 200:
            return None
        votes = []
        for strat in STRATEGIES:
            try:
                res = strat.analyze(df)
                if res.get("signal"):
                    votes.append(res)
            except Exception as e:
                print(f"Error estrategia {getattr(strat,'__name__', str(strat))} en {symbol}: {e}", flush=True)
        if not votes:
            return None
        longs = [v for v in votes if v['signal']=='long']
        shorts = [v for v in votes if v['signal']=='short']
        if longs and len(longs) >= len(shorts):
            best = max(longs, key=lambda x: x['confidence'])
            if best['confidence'] >= 70:
                return best
        if shorts and len(shorts) > len(longs):
            best = max(shorts, key=lambda x: x['confidence'])
            if best['confidence'] >= 70:
                return best
        return None

    def execute_bracket(self, symbol, decision, equity):
        try:
            bars = self.get_bars(symbol, limit=2)
            if bars.empty:
                return
            last_price = float(bars['close'].iloc[-1])
            sl, tp, _ = self.risk.get_stop_take(last_price, decision['signal'], atr=decision.get('atr'))
            qty = self.risk.calculate_position_size(equity, last_price, sl)
            if qty == 0:
                print(f"[{symbol}] Qty 0 skip", flush=True)
                return
            side = OrderSide.BUY if decision['signal'] == 'long' else OrderSide.SELL
            print(f"\n>>> {symbol} {decision['signal'].upper()} | {decision.get('strategy')} | Conf {decision['confidence']}%", flush=True)
            order = MarketOrderRequest(symbol=symbol, qty=qty, side=side, time_in_force=TimeInForce.GTC, order_class=OrderClass.BRACKET, take_profit=TakeProfitRequest(limit_price=tp), stop_loss=StopLossRequest(stop_price=sl))
            self.trading_client.submit_order(order)
            print(f"    Bracket Order enviada", flush=True)
            self.telegram.log_trade(symbol, decision, last_price, sl, tp, qty, equity)
        except Exception as e:
            print(f"    Error orden bracket {symbol}: {e}", flush=True)
            traceback.print_exc()

    def run_loop(self):
        try:
            print("Ejecutando backtest inicial de 6 meses...", flush=True)
            bt = Backtester()
            bt.run_all()
        except Exception as e:
            print(f"Backtest skip: {e}", flush=True)
            traceback.print_exc()
        last_summary_hour = -1
        while True:
            try:
                account = self.trading_client.get_account()
                equity = float(account.equity)
                positions = self.trading_client.get_all_positions()
                pos_symbols = [p.symbol for p in positions]
                now = datetime.now()
                print(f"\n--- SCAN {now.strftime('%Y-%m-%d %H:%M:%S')} | Equity ${equity:.2f} | Pos: {pos_symbols} ---", flush=True)
                if not self.risk.can_open_new_position(positions):
                    print("Max posiciones alcanzado", flush=True)
                    time.sleep(60*5)
                    continue
                for symbol in Config.SYMBOLS:
                    if symbol in pos_symbols:
                        continue
                    decision = self.think(symbol)
                    if decision:
                        self.execute_bracket(symbol, decision, equity)
                    else:
                        print(f"[{symbol}] No A+ setup", flush=True)
                print("Esperando 15 min...", flush=True)
                time.sleep(60*15)
            except Exception as e:
                print(f"[ERROR LOOP] {e}", flush=True)
                traceback.print_exc()
                time.sleep(60)

def start_bot():
    try:
        print("[BOT THREAD] Iniciando thread del bot...", flush=True)
        time.sleep(3)
        brain = TradingBrain()
        brain.run_loop()
    except Exception as e:
        print(f"[BOT THREAD FATAL] {e}", flush=True)
        traceback.print_exc()
        # No salgas, deja el thread vivo para que se vea el error en logs
        while True:
            print(f"[BOT THREAD] Esperando fix... Error: {e}", flush=True)
            time.sleep(60)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    port = int(os.environ.get("PORT", 10000))
    print(f"[WEB] Flask corriendo en puerto {port} para Render FREE", flush=True)
    app.run(host="0.0.0.0", port=port)
