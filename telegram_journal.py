import requests
import json
import os
from datetime import datetime

class TelegramJournal:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id and token.startswith("123") is False and len(token) > 20 or (token and chat_id))
        # Validacion simple: si contiene AAH_ o tiene formato bot token, lo intentamos
        if token and chat_id:
            self.enabled = True
        else:
            self.enabled = False
        self.log_file = "journal.json"

    def send(self, message):
        if not self.enabled:
            print(f"[Telegram desactivado] {message[:100]}...")
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"}
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                print("[Telegram] Mensaje enviado")
                return True
            else:
                print(f"[Telegram Error] {r.text}")
                return False
        except Exception as e:
            print(f"[Telegram Exception] {e}")
            return False

    def log_trade(self, symbol, decision, entry, sl, tp, qty, equity):
        entry_data = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": decision['signal'],
            "strategy": decision.get('strategy',''),
            "confidence": decision.get('confidence',0),
            "reason": decision.get('reason',''),
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "qty": qty,
            "equity": equity
        }
        logs = []
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file,'r') as f:
                    logs = json.load(f)
            except:
                logs = []
        logs.append(entry_data)
        with open(self.log_file,'w') as f:
            json.dump(logs, f, indent=2)

        msg = f"""🚀 *NUEVO TRADE - Alpaca Pro Bot*
📊 {symbol} | {decision['signal'].upper()} | {decision.get('strategy')}
💡 {decision.get('reason')}
🎯 Entrada: ${entry:.2f} | Qty: {qty}
🛑 SL: ${sl:.2f} | ✅ TP: ${tp:.2f}
📈 Confianza: {decision.get('confidence')}% | Equity: ${equity:.2f}
"""
        self.send(msg)

    def send_daily_summary(self, trading_client):
        try:
            account = trading_client.get_account()
            positions = trading_client.get_all_positions()
            equity = float(account.equity)
            pnl = float(account.equity) - float(account.last_equity)
            pos_text = "\n".join([f"- {p.symbol}: {p.qty} @ ${float(p.avg_entry_price):.2f} PnL ${float(p.unrealized_pl):.2f}" for p in positions]) if positions else "Sin posiciones abiertas"
            msg = f"""📊 *RESUMEN DIARIO - Alpaca Pro Bot*
🕒 {datetime.now().strftime('%Y-%m-%d %H:%M')}
💰 Equity: ${equity:.2f} | PnL Hoy: ${pnl:.2f}
📦 Posiciones:
{pos_text}
🤖 Bot activo y escaneando...
"""
            self.send(msg)
        except Exception as e:
            print(f"Error resumen diario: {e}")
