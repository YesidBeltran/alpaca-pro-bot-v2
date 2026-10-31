@app.route("/api/chart")
def api_chart():
    symbol = request.args.get("symbol", "TSLA").upper()
    tf_param = request.args.get("tf", "5M").upper()

    try:
        if DATA_CLIENT is None:
            return jsonify({"candles": [], "price": 0, "rsi": "50", "netFlow": "0.0B", "pos_info": None})

        limit = 60
        if tf_param in ["1M", "1MIN"]:
            tf = TimeFrame(1, TimeFrameUnit.Minute)
            limit = 60
        elif tf_param in ["15M", "15MIN"]:
            tf = TimeFrame(15, TimeFrameUnit.Minute)
            limit = 60
        elif tf_param in ["1H", "1HOUR"]:
            tf = TimeFrame(1, TimeFrameUnit.Hour)
            limit = 50
        elif tf_param in ["1D", "1DAY"]:
            tf = TimeFrame.Day
            limit = 45
        else:
            tf = TimeFrame(5, TimeFrameUnit.Minute)
            limit = 60

        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            limit=limit,
            feed=DataFeed.IEX,
        )
        bars = DATA_CLIENT.get_stock_bars(req).df

        if bars.empty and tf_param in ["1M", "5M"]:
            req_fallback = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(1, TimeFrameUnit.Hour),
                limit=40,
                feed=DataFeed.IEX,
            )
            bars = DATA_CLIENT.get_stock_bars(req_fallback).df

        candles = []
        last_price = 0.0
        if not bars.empty:
            if isinstance(bars.index, pd.MultiIndex):
                bars = bars.xs(symbol, level=0)
            bars["ma"] = bars["close"].rolling(10).mean()
            for idx, row in bars.iterrows():
                c_val = float(row["close"])
                last_price = c_val
                time_str = str(idx)
                if tf_param in ["1D", "1DAY"]:
                    time_label = time_str[:10]
                elif " " in time_str:
                    time_label = time_str.split(" ")[1][:5]
                else:
                    time_label = time_str[-5:]

                candles.append({
                    "t": time_label,
                    "o": float(row["open"]),
                    "h": float(row["high"]),
                    "l": float(row["low"]),
                    "c": c_val,
                    "close": c_val,
                    "ma": float(row["ma"]) if pd.notna(row["ma"]) else c_val,
                })

        pos_info = None
        if TRADING_CLIENT:
            try:
                positions = TRADING_CLIENT.get_all_positions()
                for p in positions:
                    if p.symbol == symbol:
                        entry = float(p.avg_entry_price)
                        qty = float(p.qty)
                        is_long = qty > 0
                        sl = round(entry * (0.988 if is_long else 1.012), 2)
                        tp = round(entry * (1.025 if is_long else 0.975), 2)
                        pos_info = {
                            "has_position": True,
                            "entry": entry,
                            "sl": sl,
                            "tp": tp,
                            "side": "LONG" if is_long else "SHORT",
                            "qty": qty,
                            "pl": round(float(p.unrealized_pl), 2),
                            "pl_pct": round(float(p.unrealized_plpc) * 100, 2)
                        }
                        break
            except Exception:
                pass

        return jsonify({
            "candles": candles,
            "price": round(last_price, 2),
            "rsi": "54 / 38",
            "netFlow": "2.10B",
            "pos_info": pos_info,
            "tf": tf_param
        })
    except Exception as e:
        return jsonify({"candles": [], "price": 0, "error": str(e), "pos_info": None})
