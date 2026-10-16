# Alpaca Pro Bot V2 - Full Auto

Bot con 3 estrategias + Bracket Orders + Telegram + Backtest 6 meses.

### ✅ Mejoras V2 Operativas
1. **Bracket Orders reales**: Cada orden entra con SL y TP automático en Alpaca. Ya no tienes que gestionarlo manual.
2. **Backtest 6 meses**: `python backtest.py` simula tu sistema en cada símbolo y te da WinRate y Profit Factor estimado.
3. **Journal a Telegram**: Cada trade y resumen diario te llega al celular. Log local en `journal.json`.

### 🚀 Proceso Completo GitHub + Render (Sin errores)

#### PARTE 1: GitHub
1. Ve a github.com/new -> Crea repo `alpaca-pro-bot-v2` (Public o Private, sin README)
2. En tu PC:
```bash
# Descomprime la carpeta v2 que descargaste de aquí
cd alpaca-pro-bot-v2
git init
git add .
git commit -m "v2: bracket orders + telegram + backtest operativo"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/alpaca-pro-bot-v2.git
git push -u origin main
```
IMPORTANTE: Tu .env NO se sube (está en .gitignore). Es seguro.

#### PARTE 2: Telegram (2 min)
1. Busca @BotFather en Telegram -> /newbot -> nombre `AlpacaProBot` -> te da un TOKEN tipo `12345:AAH...`
2. Busca @userinfobot -> te da tu CHAT_ID
3. Guarda TOKEN y CHAT_ID para Render.

#### PARTE 3: Render.com - Bot 24/7
1. Entra a render.com -> Sign Up con GitHub
2. Dashboard -> New + -> Background Worker
3. Conecta tu repo `alpaca-pro-bot-v2`
4. Configuración:
   - Name: `alpaca-pro-bot`
   - Environment: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python bot.py`
   - Plan: Free (o Starter $7 si quieres que nunca se duerma)

5. Environment Variables -> Add:
   - `APCA_API_KEY_ID` = tu key PAPER
   - `APCA_API_SECRET_KEY` = tu secret PAPER
   - `APCA_API_BASE_URL` = https://paper-api.alpaca.markets
   - `SYMBOLS` = AAPL,MSFT,SPY,QQQ,NVDA,TSLA
   - `TELEGRAM_BOT_TOKEN` = tu token de BotFather
   - `TELEGRAM_CHAT_ID` = tu chat id
   - `RISK_PER_TRADE` = 0.005

6. Create Worker -> Deploy. Ve a Logs.

En 2 minutos verás:
`[INIT] Alpaca PAPER conectado...`
`=== BACKTEST 6 MESES ===`
`--- SCAN ...`

Y en Telegram recibirás: 🚀 NUEVO TRADE...

#### Test Local Primero
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # edita .env con tus keys
python backtest.py  # prueba 6 meses
python bot.py       # prueba live paper
```

Listo. 100% automático, con SL/TP reales y notificaciones.
