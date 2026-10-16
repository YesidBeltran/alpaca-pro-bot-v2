class RiskManager:
    def __init__(self, config):
        self.risk_per_trade = config.RISK_PER_TRADE
        self.max_positions = config.MAX_POSITIONS

    def calculate_position_size(self, equity, entry_price, stop_loss_price):
        risk_amount = equity * self.risk_per_trade
        risk_per_share = abs(entry_price - stop_loss_price)
        if risk_per_share == 0 or risk_per_share < 0.01:
            risk_per_share = entry_price * 0.015
        qty = int(risk_amount / risk_per_share)
        return max(qty, 1)

    def can_open_new_position(self, current_positions):
        return len(current_positions) < self.max_positions

    def get_stop_take(self, entry, direction, atr=None):
        atr_dist = atr * 1.5 if atr and atr > 0 else entry * 0.015
        if direction == "long":
            sl = entry - atr_dist
            tp = entry + (atr_dist * 2.5)
        else:
            sl = entry + atr_dist
            tp = entry - (atr_dist * 2.5)
        return round(sl,2), round(tp,2), round(atr_dist,2)
