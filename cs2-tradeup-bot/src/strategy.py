"""Qualification for positive-EV investing versus chance-of-profit contracts."""


def best_profit(outcomes, cost, fee):
    return max(o.price * (1-fee/100) - cost for o in outcomes)


def qualifies(profit, roi, chance, best, settings):
    if settings.SEARCH_MODE == "upside":
        return (chance > 0 and chance*100 >= settings.MIN_WIN_CHANCE_PERCENT
                and best > 0 and best >= settings.MIN_WIN_PROFIT_DOLLARS)
    return profit > 0 and profit >= settings.MIN_PROFIT_DOLLARS and roi >= settings.MIN_ROI_PERCENT
