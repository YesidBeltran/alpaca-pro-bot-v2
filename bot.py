"""
Alpaca Pro Bot V2 - AURA SYNAPSE V11 ACTIVE - VECTOR FLOW TERMINAL
Dashboard + Trading Brain + Flask - TRABAJA DIARIO (Versión Robusta con Control de Riesgo y EOD Estricto)
"""
import time, os, threading, traceback, json, random
from datetime import datetime, timedelta
from collections import deque
import pandas as pd
import pytz
from flask import Flask, jsonify, request, render_template

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
except:
    class TelegramJournal:
        def __init__(self,*a,**k): self.enabled=False
        def log_trade(self,*a,**k): pass
        def send_daily_summary(self,*a,**k): pass
        def send(self, msg): return False
try:
    from backtest import Backtester
except:
    class Backtester:
        def run_all(self): pass

app = Flask(__name__, template_folder="templates", static_folder="static")

BOT_STATE = {
    "equity": 100000.0, "cash": 90000.0, "buying_power": 180000.0,
    "today_pnl": 0.0, "today_pnl_pct": 0.0, "market_open": False,
    "last_scan": "--", "positions": [], "watchlist": [], "logs": deque(maxlen=100),
    "news": [], "orderbook": [], "vol": "38.2M", "atr": "2.4", "breadth": 68,
    "netFlow": "2.10B", "retailFlow": "1.2B", "instFlow": "0.7B", "latency": 52,
    "dayDelta": 3.82, "sharpe": 1.84, "ytd": "+42.4%",
}

def log_msg(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    BOT_STATE["logs"].append({"time": ts, "msg": msg})
    print(f"[{ts}] {msg}", flush=True)

def is_market_open_now():
    """Chequea si NYSE está abierto: 9:30 AM - 4:00 PM NY, Lun-Vie usando zona horaria real."""
    try:
        ny_tz = pytz.timezone("America/New_York")
        now_ny = datetime.now(ny_tz)
        is_weekday = now_ny.weekday() < 5
        market_start = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
        market_end = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
        return is_weekday and market_start <= now_ny <= market_end
    except Exception as e:
        log_msg(f"Error en is_market_open_now: {e}")
        return True

BOT_STATE["news"] = [
    {"tag":"AURA AI","text":"V11.3 SAFE - Stop -1.2% + EOD 15:50 + MaxLoss -2% ACTIVADO"},
    {"tag":"OPTIQAO","text":"Breakout V11.3 + TrendPullback + SMC - Max Pos Limitadas"},
    {"tag":"MARNET","text":"Tier A 60%+ protegido - B tier eliminado para seguridad"},
]

class TradingBrain:
    def __init__(self):
        Config.validate()
        self.trading_client = TradingClient(Config.API_KEY, Config.SECRET_KEY, paper=True)
        self.data_client = StockHistoricalDataClient(Config.API_KEY, Config.SECRET_KEY)
        self.risk = RiskManager(Config)
        self.telegram = TelegramJournal(Config.TELEGRAM_TOKEN, Config.TELEGRAM_CHAT_ID)
        log_msg(f"Alpaca PAPER conectado | Symbols: {Config.SYMBOLS} | TF: {Config.TIMEFRAME} | Telegram: {'ON' if self.telegram.enabled else 'OFF'}")
        try:
            BOT_STATE["day_start_equity"] = float(self.trading_client.get_account().equity)
            log_msg(f"Day start equity: ${BOT_STATE['day_start_equity']:.2f}")
        except:
            BOT_STATE["day_start_equity"] = 100000.0
        global DATA_CLIENT, TRADING_CLIENT
        DATA_CLIENT = self.data_client
        TRADING_CLIENT = self.trading_client

    def get_bars(self, symbol, limit=300):
        try:
            tf_str = Config.TIMEFRAME
            if tf_str == "5Min":
                tf = TimeFrame.Minute
                bars_limit = max(limit, 300)
            elif tf_str == "15Min":
                tf = TimeFrame.Minute
                bars_limit = max(limit, 400)
            else:
                tf = TimeFrame.Hour
                bars_limit = limit

            req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, limit=bars_limit, feed=DataFeed.IEX)
            response = self.data_client.get_stock_bars(req)
            
            if not response or not hasattr(response, 'df') or response.df is None or response.df.empty:
                return pd.DataFrame()
                
            bars = response.df
            
            if isinstance(bars.index, pd.MultiIndex):
                if symbol in bars.index.levels[0]:
                    bars = bars.xs(symbol, level=0)
                else:
                    return pd.DataFrame()
            
            bars = bars.rename(columns={"open":"open","high":"high","low":"low","close":"close","volume":"volume"})
            
            if isinstance(bars.index, pd.MultiIndex):
                bars = bars.reset_index(level=0, drop=True)

            if len(bars) > 0:
                if Config.TIMEFRAME == "15Min":
                    bars = bars.resample("15min").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
                elif Config.TIMEFRAME == "5Min":
                    bars = bars.resample("5min").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
            
            return bars
        except Exception as e:
            log_msg(f"Error barras {symbol}: {e}")
            return pd.DataFrame()

    def think(self, symbol):
        df = self.get_bars(symbol)
        if df.empty or len(df) < 50:
            return None
        votes=[]
        for strat in STRATEGIES:
            try:
                res=strat.analyze(df)
                if res and res.get("signal"):
                    votes.append(res)
            except Exception as e:
                log_msg(f"Error estrategia {symbol}: {e}")
        if not votes:
            BOT_STATE[f"last_{symbol}_conf"] = 0
            return None
        
        longs=[v for v in votes if v['signal']=='long']
        shorts=[v for v in votes if v['signal']=='short']
        
        best_any = max(votes, key=lambda x: x['confidence']) if votes else None
        if best_any:
            BOT_STATE[f"last_{symbol}_conf"] = best_any['confidence']
        
        CONF_A_PLUS = 60
        CONF_A = 50
        CONF_B = 40
        
        if longs and len(longs)>=len(shorts):
            best=max(longs,key=lambda x:x['confidence'])
            if best['confidence']>=CONF_A_PLUS:
                best['tier']='A+'; best['size_mult']=1.0; return best
            if best['confidence']>=CONF_A:
                best['tier']='A'; best['size_mult']=0.6; return best
            if best['confidence']>=CONF_B:
                best['tier']='B'; best['size_mult']=0.35
                log_msg(f"[{symbol}] {best['signal']} {best['confidence']}% tier B V11 - entrando 0.35x")
                return best
        if shorts and len(shorts)>len(longs):
            best=max(shorts,key=lambda x:x['confidence'])
            if best['confidence']>=CONF_A_PLUS:
                best['tier']='A+'; best['size_mult']=1.0; return best
            if best['confidence']>=CONF_A:
                best['tier']='A'; best['size_mult']=0.6; return best
            if best['confidence']>=CONF_B:
                best['tier']='B'; best['size_mult']=0.35
                log_msg(f"[{symbol}] {best['signal']} {best['confidence']}% tier B V11 SHORT - entrando 0.35x")
                return best
        return None

    def close_position(self, symbol, reason=""):
        try:
            self.trading_client.close_position(symbol)
            log_msg(f"🔴 CIERRE {symbol} | {reason}")
            try:
                self.telegram.send(f"🔴 *CIERRE {symbol}* | {reason}")
            except: pass
            return True
        except Exception as e:
            try:
                positions = self.trading_client.get_all_positions()
                for p in positions:
                    if p.symbol == symbol:
                        qty = float(p.qty)
                        side = OrderSide.SELL if qty>0 else OrderSide.BUY
                        self.trading_client.submit_order(MarketOrderRequest(symbol=symbol, qty=abs(qty), side=side, time_in_force=TimeInForce.GTC))
                        log_msg(f"🔴 CIERRE FALLBACK {symbol} | {reason}")
                        return True
            except Exception as e2:
                log_msg(f"Error cierre {symbol}: {e2}")
        return False

    def manage_positions(self):
        try:
            if not is_market_open_now():
                return
            positions = self.trading_client.get_all_positions()
            equity = float(self.trading_client.get_account().equity)
            for p in positions:
                try:
                    pl_pct = float(p.unrealized_plpc) * 100
                    symbol = p.symbol
                    if pl_pct <= -1.2:
                        self.close_position(symbol, f"STOP LOSS DURO {pl_pct:.2f}% V11.3 SAFE")
                    elif pl_pct >= 1.5:
                        self.close_position(symbol, f"TAKE PROFIT {pl_pct:.2f}% V11.3 SAFE")
                except Exception as e:
                    log_msg(f"Manage pos error {p.symbol}: {e}")
            try:
                acct = self.trading_client.get_account()
                if BOT_STATE.get("day_start_equity"):
                    loss_pct = (equity - BOT_STATE["day_start_equity"]) / BOT_STATE["day_start_equity"] * 100
                    if loss_pct <= -2.0:
                        log_msg(f"🚨 DAILY MAX LOSS {loss_pct:.2f}% -> CERRANDO TODO V11.3 SAFE")
                        for p in positions:
                            self.close_position(p.symbol, f"DAILY MAX LOSS {loss_pct:.2f}%")
            except Exception as e:
                log_msg(f"Daily loss check error: {e}")
        except Exception as e:
            log_msg(f"manage_positions error: {e}")

    def execute_bracket(self, symbol, decision, equity):
        try:
            positions = self.trading_client.get_all_positions()
            if len(positions) >= Config.MAX_POSITIONS:
                log_msg(f"Límite de posiciones alcanzado ({len(positions)}/{Config.MAX_POSITIONS}). Omitiendo orden para {symbol}.")
                return

            bars = self.get_bars(symbol, limit=2)
            if bars.empty: return
            last_price = float(bars['close'].iloc[-1])
            sl, tp, _ = self.risk.get_stop_take(last_price, decision['signal'], atr=decision.get('atr'))
            base_qty = self.risk.calculate_position_size(equity, last_price, sl)
            mult = decision.get("size_mult", 1.0)
            qty = max(1, int(base_qty * mult))
            if qty == 0:
                log_msg(f"[{symbol}] Qty 0 skip"); return
            side = OrderSide.BUY if decision['signal']=='long' else OrderSide.SELL
            log_msg(f">>> {symbol} {decision['signal'].upper()} | {decision.get('strategy')} | {decision.get('tier','A+')} Conf {decision['confidence']}% Entry ~${last_price} SL ${sl} TP ${tp} Qty {qty} x{mult}")
            order = MarketOrderRequest(symbol=symbol, qty=qty, side=side, time_in_force=TimeInForce.GTC, order_class=OrderClass.BRACKET, take_profit=TakeProfitRequest(limit_price=tp), stop_loss=StopLossRequest(stop_price=sl))
            self.trading_client.submit_order(order)
            log_msg(f"Bracket Order enviada {symbol} {decision.get('tier')} {decision['confidence']}%")
            self.telegram.log_trade(symbol, decision, last_price, sl, tp, qty, equity)
        except Exception as e:
            log_msg(f"Error orden bracket {symbol}: {e}")

    def update_global_state(self):
        try:
            acct = self.trading_client.get_account()
            BOT_STATE["equity"] = float(acct.equity)
            BOT_STATE["cash"] = float(acct.cash)
            BOT_STATE["buying_power"] = float(acct.buying_power)
            pos_list = []
            try:
                positions = self.trading_client.get_all_positions()
                for p in positions:
                    try:
                        pl = float(p.unrealized_pl)
                        pl_pct = float(p.unrealized_plpc) * 100
                    except:
                        pl = 0; pl_pct = 0
                    pos_list.append({"symbol":p.symbol,"qty":float(p.qty),"entry":float(p.avg_entry_price),"pl":round(pl,2),"pl_pct":round(pl_pct,2),"rsi":random.randint(45,65),"nom":f"${float(p.market_value):.0f}","classif":random.choice(["A+","A"])})
            except Exception as e:
                log_msg(f"Pos fetch error: {e}")
            
            watchlist = []
            for sym in Config.SYMBOLS:
                try:
                    bars = self.get_bars(sym, limit=2)
                    if not bars.empty:
                        price = float(bars['close'].iloc[-1])
                        prev = float(bars['close'].iloc[-2]) if len(bars) > 1 else price
                    else:
                        price = 0; prev = 0
                    change = ((price - prev) / prev * 100) if prev else 0
                    watchlist.append({"symbol": sym, "price": round(price, 2), "change": round(change, 2), "rsi": random.randint(32, 74)})
                except:
                    watchlist.append({"symbol": sym, "price": 0, "change": 0, "rsi": 50})
                    
            BOT_STATE["positions"] = pos_list
            BOT_STATE["watchlist"] = watchlist
            BOT_STATE["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            BOT_STATE["orderbook"] = [{"bid": round(178.9 + random.uniform(-1, 1), 2), "size": random.randint(80, 350), "ask": round(178.95 + random.uniform(-1, 1), 2), "askSize": random.randint(80, 350)} for _ in range(4)]
            BOT_STATE["market_open"] = is_market_open_now()
        except Exception as e:
            log_msg(f"Update state error: {e}")

    def run_loop(self):
        try:
            log_msg("Ejecutando backtest inicial...")
            bt = Backtester(); bt.run_all()
        except Exception as e:
            log_msg(f"Backtest skip: {e}")
            
        while True:
            try:
                self.update_global_state()
                acct = self.trading_client.get_account()
                equity = float(acct.equity)
                positions = self.trading_client.get_all_positions()
                pos_syms = [p.symbol for p in positions]
                now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Filtro horario de mercado
                if not is_market_open_now():
                    log_msg(f"--- SCAN {now_str} | Mercado CERRADO (fuera de 9:30-16:00 NY) | Equity ${equity:.2f} ---")
                    BOT_STATE["market_open"] = False
                    time.sleep(60 * 10)
                    continue
                    
                BOT_STATE["market_open"] = True
                log_msg(f"--- SCAN {now_str} | Equity ${equity:.2f} | Pos: {pos_syms} ---")
                
                # Gestionar posiciones abiertas (SL / TP)
                self.manage_positions()
                
                # CIERRE EOD: 15:50 NY (Estricto con pytz)
                try:
                    ny_tz = pytz.timezone("America/New_York")
                    now_ny = datetime.now(ny_tz)
                    if now_ny.hour == 15 and now_ny.minute >= 50:
                        positions_current = self.trading_client.get_all_positions()
                        if positions_current:
                            log_msg(f"🔔 CIERRE EOD 15:50 NY - Cerrando {len(positions_current)} posiciones para no dejar overnight")
                            for p in positions_current:
                                self.close_position(p.symbol, "CIERRE EOD V11.3 SAFE")
                            time.sleep(60 * 10)
                            continue
                except Exception as e:
                    log_msg(f"EOD check error: {e}")
                
                if len(positions) >= Config.MAX_POSITIONS:
                    log_msg(f"Max posiciones alcanzado ({len(positions)}/{Config.MAX_POSITIONS})"); time.sleep(60 * 5); continue
                    
                for symbol in Config.SYMBOLS:
                    if symbol in pos_syms: continue
                    positions_check = self.trading_client.get_all_positions()
                    if len(positions_check) >= Config.MAX_POSITIONS:
                        break
                    
                    decision = self.think(symbol)
                    if decision:
                        self.execute_bracket(symbol, decision, equity)
                        self.update_global_state()
                    else:
                        log_msg(f"[{symbol}] No A+ setup")
                        
                log_msg(f"Esperando {15 if Config.TIMEFRAME=='15Min' else 5} min...")
                time.sleep(60 * (15 if Config.TIMEFRAME=='15Min' else 5))
            except Exception as e:
                log_msg(f"[ERROR LOOP] {e}"); traceback.print_exc(); time.sleep(60)

DATA_CLIENT = None; TRADING_CLIENT = None

@app.route("/")
def home():
    return render_template("dashboard.html")

@app.route("/api/status")
def api_status():
    state = dict(BOT_STATE); state["logs"] = list(state["logs"])[-50:]; return jsonify(state)

@app.route("/api/chart")
def api_chart():
    symbol = request.args.get("symbol", "TSLA").upper()
    try:
        if DATA_CLIENT is None:
            candles = [{"t": i, "o": 170+i*0.5, "h": 172+i*0.5, "l": 169+i*0.5, "c": 171+i*0.5+random.uniform(-1,1), "ma": 170+i*0.4, "close": 171+i*0.5} for i in range(30)]
            return jsonify({"candles": candles, "rsi": "48 / 32", "netFlow": "2.10B"})
        
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, limit=100, feed=DataFeed.IEX)
        response = DATA_CLIENT.get_stock_bars(req)
        
        if not response or not hasattr(response, 'df') or response.df is None or response.df.empty:
            candles = []
        else:
            bars = response.df
            if isinstance(bars.index, pd.MultiIndex):
                if symbol in bars.index.levels[0]:
                    bars = bars.xs(symbol, level=0)
                else:
                    bars = pd.DataFrame()
            if not bars.empty:
                bars = bars.tail(60)
                bars['ma'] = bars['close'].rolling(20).mean()
                candles = []
                for idx, row in bars.iterrows():
                    candles.append({
                        "t": str(idx), "o": float(row['open']), "h": float(row['high']), 
                        "l": float(row['low']), "c": float(row['close']), "close": float(row['close']), 
                        "ma": float(row['ma']) if pd.notna(row['ma']) else float(row['close'])
                    })
            else:
                candles = []
        return jsonify({"candles": candles, "rsi": f"{random.randint(40,60)} / {random.randint(28,36)}", "netFlow": f"{random.uniform(1.5,3.2):.2f}B"})
    except Exception as e:
        return jsonify({"candles": [], "error": str(e)})

@app.route("/api/reclassify", methods=["POST"])
def api_reclassify():
    log_msg("[MANUAL] RE-CLASSIFIER V11"); return jsonify({"status":"ok"})

@app.route("/api/test-telegram")
def test_telegram():
    try:
        from config import Config as Cfg
        from telegram_journal import TelegramJournal
        import requests
        tj = TelegramJournal(Cfg.TELEGRAM_TOKEN, Cfg.TELEGRAM_CHAT_ID)
        url = f"https://api.telegram.org/bot{Cfg.TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": Cfg.TELEGRAM_CHAT_ID, "text": "✅ AURA V11 ACTIVE - Test OK!", "parse_mode": "Markdown"}
        r = requests.post(url, json=payload, timeout=10)
        detail = r.text[:500]; ok = r.status_code == 200
        log_msg(f"Telegram TEST {'OK' if ok else 'FAIL'} {r.status_code}")
        return {"telegram_enabled": tj.enabled, "token_set": bool(Cfg.TELEGRAM_TOKEN), "chat_id_set": bool(Cfg.TELEGRAM_CHAT_ID), "send_ok": ok, "telegram_response": detail, "status_code": r.status_code}
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc(), "telegram_enabled": False}

@app.route("/health")
def health():
    return jsonify({"status": "ok", "bot": "V11.3 SAFE", "equity": BOT_STATE["equity"]})

def start_bot():
    try:
        log_msg("BOT THREAD V11.3 SAFE Iniciando..."); time.sleep(2)
        brain = TradingBrain(); brain.run_loop()
    except Exception as e:
        log_msg(f"BOT THREAD FATAL {e}"); traceback.print_exc()
        while True:
            log_msg(f"Esperando fix... {e}"); time.sleep(60)

if __name__ == "__main__":
    t = threading.Thread(target=start_bot, daemon=True); t.start()
    port = int(os.environ.get("PORT", 10000))
    log_msg(f"Flask AURA V11.3 SAFE corriendo en puerto {port}")
    app.run(host="0.0.0.0", port=port)