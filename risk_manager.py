class RiskManager:
    def __init__(self, config):
        self.risk_per_trade = config.RISK_PER_TRADE
        self.max_positions = config.MAX_POSITIONS

    def calculate_position_size(self, equity, entry_price, stop_loss_price):
        risk_amount = equity * self.risk_per_trade
        risk_per_share = abs(entry_price - stop_loss_price)
        # V11 FIX: SL minimo 1% para no generar qty gigante
        min_risk = entry_price * 0.012  # 1.2% minimo
        if risk_per_share < min_risk:
            risk_per_share = min_risk
        if risk_per_share == 0 or risk_per_share < 0.01:
            risk_per_share = entry_price * 0.015
        qty = int(risk_amount / risk_per_share)
        # V11 FIX: cap por buying power - max 20% del equity por posicion
        max_notional = equity * 0.20
        max_qty_by_power = int(max_notional / entry_price)
        qty = min(qty, max_qty_by_power)
        # V11: max absoluto 100 shares para acciones caras >$300
        if entry_price > 300:
            qty = min(qty, 80)
        elif entry_price > 150:
            qty = min(qty, 150)
        else:
            qty = min(qty, 250)
        return max(qty, 1)

    def can_open_new_position(self, current_positions):
        return len(current_positions) < self.max_positions

    def get_stop_take(self, entry, direction, atr=None):
        # V11 FIX: ATR * 1.8 para SL mas amplio, TP 2.2
        atr_dist = atr * 1.8 if atr and atr > 0 else entry * 0.018
        # minimo 1.2%
        min_dist = entry * 0.012
        if atr_dist < min_dist:
            atr_dist = min_dist
        if direction == "long":
            sl = entry - atr_dist
            tp = entry + (atr_dist * 2.2)
        else:
            sl = entry + atr_dist
            tp = entry - (atr_dist * 2.2)
        return round(sl,2), round(tp,2), round(atr_dist,2)
