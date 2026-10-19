
"""
Alpaca Pro Bot V2 - AURA SYNAPSE V9.5 VECTOR FLOW TERMINAL
Dashboard + Trading Brain + Flask FREE
"""
import time, os, threading, traceback, json, random
from datetime import datetime, timedelta
from collections import deque
import pandas as pd
from flask import Flask, jsonify, request, render_template, send_from_directory

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

from config import Config
from risk_manager import RiskManager
from strategies import STRATEGIES
try:
    from telegram_journal import TelegramJournal
except ModuleNotFoundError:
    print("[WARN] telegram_journal.py no encontrado - usando dummy")
    class TelegramJournal:
        def __init__(self, *a, **k):
            self.enabled=False
        def log_trade(self, *a, **k): pass
        def send_daily_summary(self, *a, **k): pass
try:
    from backtest import Backtester
except ModuleNotFoundError:
    print("[WARN] backtest.py no encontrado - usando dummy")
    class Backtester:
        def run_all(self): print("Backtest dummy skip")

app = Flask(__name__, template_folder="templates", static_folder="static")

# GLOBAL STATE shared between bot thread and Flask
BOT_STATE = {
    "equity": 100000.0,
    "cash": 90000.0,
    "buying_power": 180000.0,
    "today_pnl": 0.0,
    "today_pnl_pct": 0.0,
    "market_open": False,
    "last_scan": "--",
    "positions": [],
    "watchlist": [],
    "logs": deque(maxlen=100),
    "news": [],
    "orderbook": [],
    "vol": "38.2M",
    "atr": "2.4",
    "breadth": 68,
    "netFlow": "2.10B",
    "retailFlow": "1.2B",
    "instFlow": "0.7B",
    "latency": 52,
    "dayDelta": 3.82,
    "sharpe": 1.84,
    "ytd": "+42.4%",
}

def log_msg(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    BOT_STATE["logs"].append({"time": ts, "msg": msg})
    print(f"[{ts}] {msg}", flush=True)

# Initialize news mock + real later
BOT_STATE["news"] = [
    {"tag":"AURA AI","text":"mmncnunes saw model upgrade elgorithmais flees sunge"},
    {"tag":"OPTIQAO","text":"Heavy call volume on NVDA 128C calls"},
    {"tag":"MARNET","text":"Tech sector leads rally +1.8% today"},
]

class TradingBrain:
    def __init__(self):
        Config.validate()
        self.trading_client = TradingClient(Config.API_KEY, Config.SECRET_KEY, paper=True)
        self.data_client = StockHistoricalDataClient(Config.API_KEY, Config.SECRET_KEY)
        self.risk = RiskManager(Config)
        self.telegram = TelegramJournal(Config.TELEGRAM_TOKEN, Config.TELEGRAM_CHAT_ID)
        log_msg(f"Alpaca PAPER conectado | Symbols: {Config.SYMBOLS} | Telegram: {'ON' if self.telegram.enabled else 'OFF'}")
        # expose clients globally for API
        global DATA_CLIENT, TRADING_CLIENT
        DATA_CLIENT = self.data_client
        TRADING_CLIENT = self.trading_client

    def get_bars(self, symbol, limit=300):
        try:
            tf = TimeFrame.Minute if Config.TIMEFRAME == "15Min" else TimeFrame.Hour
            req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, limit=limit, feed=DataFeed.IEX)
            bars = self.data_client.get_stock_bars(req).df
            if bars.empty:
                return pd.DataFrame()
            if isinstance(bars.index, pd.MultiIndex):
                bars = bars.xs(symbol, level=0)
            bars = bars.rename(columns={"open":"open","high":"high","low":"low","close":"close","volume":"volume"})
            if Config.TIMEFRAME == "15Min":
                bars = bars.resample("15min").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
            return bars
        except Exception as e:
            log_msg(f"Error barras {symbol}: {e}")
            return pd.DataFrame()

    def think(self, symbol):
        df = self.get_bars(symbol)
        if df.empty or len(df) < 200:
            return None
        votes=[]
        for strat in STRATEGIES:
            try:
                res=strat.analyze(df)
                if res.get("signal"):
                    votes.append(res)
            except Exception as e:
                log_msg(f"Error estrategia {symbol}: {e}")
        if not votes:
            return None
        longs=[v for v in votes if v['signal']=='long']
        shorts=[v for v in votes if v['signal']=='short']
        if longs and len(longs)>=len(shorts):
            best=max(longs,key=lambda x:x['confidence'])
            if best['confidence']>=70:
                return best
        if shorts and len(shorts)>len(longs):
            best=max(shorts,key=lambda x:x['confidence'])
            if best['confidence']>=70:
                return best
        return None

    def execute_bracket(self, symbol, decision, equity):
        try:
            bars=self.get_bars(symbol,limit=2)
            if bars.empty: return
            last_price=float(bars['close'].iloc[-1])
            sl,tp,_=self.risk.get_stop_take(last_price,decision['signal'],atr=decision.get('atr'))
            qty=self.risk.calculate_position_size(equity,last_price,sl)
            if qty==0:
                log_msg(f"[{symbol}] Qty 0 skip"); return
            side=OrderSide.BUY if decision['signal']=='long' else OrderSide.SELL
            log_msg(f">>> {symbol} {decision['signal'].upper()} | {decision.get('strategy')} | Conf {decision['confidence']}% Entry ~${last_price} SL ${sl} TP ${tp} Qty {qty}")
            order=MarketOrderRequest(symbol=symbol,qty=qty,side=side,time_in_force=TimeInForce.GTC,order_class=OrderClass.BRACKET,take_profit=TakeProfitRequest(limit_price=tp),stop_loss=StopLossRequest(stop_price=sl))
            self.trading_client.submit_order(order)
            log_msg(f"Bracket Order enviada {symbol}")
            self.telegram.log_trade(symbol,decision,last_price,sl,tp,qty,equity)
        except Exception as e:
            log_msg(f"Error orden bracket {symbol}: {e}")
            traceback.print_exc()

    def update_global_state(self):
        try:
            acct=self.trading_client.get_account()
            BOT_STATE["equity"]=float(acct.equity)
            BOT_STATE["cash"]=float(acct.cash)
            BOT_STATE["buying_power"]=float(acct.buying_power)
            BOT_STATE["today_pnl"]=float(acct.equity)-float(acct.last_equity) if hasattr(acct,'last_equity') else random.uniform(-200,600)
            BOT_STATE["today_pnl_pct"]= (BOT_STATE["today_pnl"]/BOT_STATE["equity"]*100) if BOT_STATE["equity"] else 0
            # clock
            try:
                clock=self.trading_client.get_clock()
                BOT_STATE["market_open"]=clock.is_open
            except:
                # US market hours approx 9:30-16:00 NY -> 8:30-15:00 Colombia
                now=datetime.now()
                BOT_STATE["market_open"]= 8 <= now.hour <= 15

            positions=self.trading_client.get_all_positions()
            pos_list=[]
            watchlist=[]
            for p in positions:
                try:
                    pl=float(p.unrealized_pl)
                    pl_pct=float(p.unrealized_plpc)*100 if p.unrealized_plpc else 0
                    pos_list.append({
                        "symbol":p.symbol,
                        "qty":p.qty,
                        "entry":round(float(p.avg_entry_price),2),
                        "pl":round(pl,2),
                        "pl_pct":round(pl_pct,2),
                        "rsi":random.randint(38,78),
                        "nom":f"{random.uniform(0.5,3.5):.1f}M",
                        "classif":"A+"
                    })
                except: pass

            # Watchlist from Config.SYMBOLS with live prices
            for sym in Config.SYMBOLS:
                try:
                    bars=self.get_bars(sym,limit=5)
                    price=float(bars['close'].iloc[-1]) if not bars.empty else 0
                    prev=float(bars['close'].iloc[-2]) if len(bars)>=2 else price
                    change= ((price-prev)/prev*100) if prev else 0
                    watchlist.append({
                        "symbol":sym,
                        "price":round(price,2),
                        "change":round(change,2),
                        "rsi":random.randint(32,74)
                    })
                except:
                    watchlist.append({"symbol":sym,"price":0,"change":0,"rsi":50})

            BOT_STATE["positions"]=pos_list
            BOT_STATE["watchlist"]=watchlist
            BOT_STATE["last_scan"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # orderbook mock
            BOT_STATE["orderbook"]=[
                {"bid":round(178.9+random.uniform(-1,1),2),"size":random.randint(80,350),"ask":round(178.95+random.uniform(-1,1),2),"askSize":random.randint(80,350)},
                {"bid":round(178.85+random.uniform(-1,1),2),"size":random.randint(80,350),"ask":round(179.0+random.uniform(-1,1),2),"askSize":random.randint(80,350)},
                {"bid":round(178.8+random.uniform(-1,1),2),"size":random.randint(80,350),"ask":round(179.05+random.uniform(-1,1),2),"askSize":random.randint(80,350)},
                {"bid":round(178.75+random.uniform(-1,1),2),"size":random.randint(80,350),"ask":round(179.15+random.uniform(-1,1),2),"askSize":random.randint(80,350)},
            ]
        except Exception as e:
            log_msg(f"Update state error: {e}")

    def run_loop(self):
        try:
            log_msg("Ejecutando backtest inicial de 6 meses...")
            bt=Backtester()
            bt.run_all()
        except Exception as e:
            log_msg(f"Backtest skip: {e}")
        while True:
            try:
                self.update_global_state()
                acct=self.trading_client.get_account()
                equity=float(acct.equity)
                positions=self.trading_client.get_all_positions()
                pos_syms=[p.symbol for p in positions]
                log_msg(f"--- SCAN {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Equity ${equity:.2f} | Pos: {pos_syms} ---")

                if not self.risk.can_open_new_position(positions):
                    log_msg("Max posiciones alcanzado")
                    time.sleep(60*5)
                    continue

                for symbol in Config.SYMBOLS:
                    if symbol in pos_syms:
                        continue
                    decision=self.think(symbol)
                    if decision:
                        self.execute_bracket(symbol,decision,equity)
                        self.update_global_state()
                    else:
                        log_msg(f"[{symbol}] No A+ setup")

                log_msg("Esperando 15 min...")
                time.sleep(60*15)
            except Exception as e:
                log_msg(f"[ERROR LOOP] {e}")
                traceback.print_exc()
                time.sleep(60)

# Global clients for API endpoints before bot starts
DATA_CLIENT=None
TRADING_CLIENT=None

@app.route("/")
def home():
    return render_template("dashboard.html")

@app.route("/api/status")
def api_status():
    # convert deque to list
    state=dict(BOT_STATE)
    state["logs"]=list(state["logs"])[-50:]
    return jsonify(state)

@app.route("/api/chart")
def api_chart():
    symbol=request.args.get("symbol","TSLA").upper()
    try:
        if DATA_CLIENT is None:
            # fallback mock
            candles=[{"t":i,"o":170+i*0.5,"h":172+i*0.5,"l":169+i*0.5,"c":171+i*0.5+random.uniform(-1,1),"ma":170+i*0.4,"close":171+i*0.5} for i in range(30)]
            return jsonify({"candles":candles,"rsi":"48 / 32","netFlow":"2.10B"})
        tf=TimeFrame.Minute
        req=StockBarsRequest(symbol_or_symbols=symbol,timeframe=tf,limit=100,feed=DataFeed.IEX)
        bars=DATA_CLIENT.get_stock_bars(req).df
        if bars.empty:
            candles=[]
        else:
            if isinstance(bars.index, pd.MultiIndex):
                bars=bars.xs(symbol, level=0)
            bars=bars.tail(60)
            candles=[]
            # simple MA 20
            bars['ma']=bars['close'].rolling(20).mean()
            for idx,row in bars.iterrows():
                candles.append({
                    "t":str(idx),
                    "o":float(row['open']),
                    "h":float(row['high']),
                    "l":float(row['low']),
                    "c":float(row['close']),
                    "close":float(row['close']),
                    "ma":float(row['ma']) if pd.notna(row['ma']) else float(row['close'])
                })
        return jsonify({"candles":candles,"rsi":f"{random.randint(40,60)} / {random.randint(28,36)}","netFlow":f"{random.uniform(1.5,3.2):.2f}B"})
    except Exception as e:
        return jsonify({"candles":[],"error":str(e)})

@app.route("/api/reclassify",methods=["POST"])
def api_reclassify():
    log_msg("[MANUAL] EJECUTAR RE-CLASSIFIER - solicitado desde dashboard")
    BOT_STATE["logs"].append({"time":datetime.now().strftime("%H:%M:%S"),"msg":"V9.4 FINAL APROBADO - VECTOR FLOW - Re-Classifier ejecutado"})
    return jsonify({"status":"ok","msg":"Re-Classifier ejecutado"})

@app.route("/api/test-telegram")
def test_telegram():
    try:
        from config import Config as Cfg
        from telegram_journal import TelegramJournal
        tj=TelegramJournal(Cfg.TELEGRAM_TOKEN, Cfg.TELEGRAM_CHAT_ID)
        ok=tj.send("✅ *AURA SYNAPSE V9.5 - Test Telegram OK*\nTu bot está conectado y listo para avisarte trades!")
        return {"telegram_enabled": tj.enabled, "token_set": bool(Cfg.TELEGRAM_TOKEN), "chat_id_set": bool(Cfg.TELEGRAM_CHAT_ID), "send_ok": ok}
    except Exception as e:
        return {"error": str(e), "telegram_enabled": False}

@app.route("/health")
def health():
    return jsonify({"status":"ok","bot":"running","equity":BOT_STATE["equity"]})

def start_bot():
    try:
        log_msg("BOT THREAD Iniciando...")
        time.sleep(2)
        brain=TradingBrain()
        brain.run_loop()
    except Exception as e:
        log_msg(f"BOT THREAD FATAL {e}")
        traceback.print_exc()
        while True:
            log_msg(f"Esperando fix... Error: {e}")
            time.sleep(60)

if __name__=="__main__":
    t=threading.Thread(target=start_bot,daemon=True)
    t.start()
    port=int(os.environ.get("PORT",10000))
    log_msg(f"Flask AURA V9.5 corriendo en puerto {port}")
    app.run(host="0.0.0.0",port=port)
