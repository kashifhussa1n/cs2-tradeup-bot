"""Persist unfinished candidates, never persist a 'verified' price decision."""
from dataclasses import asdict
import time
from src.search import Block, Candidate
from src.storage import read_json, write_json


def context(budget, rarity, settings):
    return {"version": 1, "budget": budget, "rarity": rarity,
            "fee": settings.SELL_FEE_PERCENT, "min_profit": settings.MIN_PROFIT_DOLLARS,
            "min_roi": settings.MIN_ROI_PERCENT, "search_mode": settings.SEARCH_MODE,
            "min_win_chance": settings.MIN_WIN_CHANCE_PERCENT,
            "min_win_profit": settings.MIN_WIN_PROFIT_DOLLARS}


def save(path, run_context, pending):
    write_json(path, {"context": run_context, "updated_at": time.time(),
                     "pending": [asdict(c) for c in pending]})


def load(path):
    state = read_json(path, None)
    if state is None:
        return None
    if state.get("context", {}).get("version") != 1:
        raise ValueError("Unsupported verification checkpoint")
    pending = []
    for raw in state["pending"]:
        item = dict(raw)
        item["parts"] = [(Block(**block), count) for block, count in item["parts"]]
        pending.append(Candidate(**item))
    return state["context"], pending
