"""Budget-only local discovery followed by bounded live verification."""
import argparse
import logging
import math
import os
import sys
import time
import config
from src.skin_data import load_skin_data, group_by_collection_and_rarity
from src.discovery import DiscoveryPrices
from src.search import generate, balanced_shortlist
from src.csfloat_client import CSFloatClient, VerificationStopped
from src.verifier import verify
from src.discord_webhook import post_results
from src.storage import write_json
from src import checkpoint

log = logging.getLogger(__name__)


def choose_budget(value=None):
    if value is None and sys.stdin.isatty() and not os.getenv("BUDGET_OVERRIDE"):
        value = input(f"Enter maximum budget in USD [${config.MAX_TOTAL_COST:.2f}]: ").strip()
    value = config.MAX_TOTAL_COST if value in (None, "") else float(str(value).lstrip("$"))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Budget must be a positive finite dollar amount")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("budget", nargs="?")
    parser.add_argument("--offline", action="store_true", help="Local files only; no network or Discord")
    parser.add_argument("--no-discord", action="store_true")
    parser.add_argument("--rarity", choices=config.RARITY_TIERS)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true", help="Resume saved queue using its budget and rarity")
    mode.add_argument("--fresh", action="store_true", help="Discard unfinished queue when starting live verification")
    args = parser.parse_args(argv)
    checkpoint_path = f"{config.DATA_DIR}/verification_queue.json"
    saved = checkpoint.load(checkpoint_path) if not args.fresh and not args.offline else None
    if args.resume:
        if args.offline:
            parser.error("--resume cannot be combined with --offline")
        if not saved or not saved[1]:
            parser.error("No unfinished saved queue. Start a normal scan first.")
        if args.rarity is None:
            args.rarity = saved[0]["rarity"]
        budget = choose_budget(args.budget if args.budget is not None else saved[0]["budget"])
    else:
        budget = choose_budget(args.budget)
    run_context = checkpoint.context(budget, args.rarity, config)
    if args.resume and saved[0] != run_context:
        parser.error("Saved budget, rarity, strategy or fee/profit settings differ. Use --fresh to start a new scan.")
    pending = saved[1] if saved and saved[0] == run_context and saved[1] else None
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("CS2 TRADE-UP BOT | Budget $%.2f | Scanning all configured grades", budget)
    client = CSFloatClient(os.getenv("CSFLOAT_API_KEY", ""), config.DATA_DIR,
        config.MAX_CSFLOAT_REQUESTS_PER_RUN, config.CSFLOAT_REQUEST_DELAY, config.LIVE_TTL)
    status, verified, stats, checked, sent = "", [], {}, 0, 0
    stop_reason = None
    try:
        if not args.offline:
            client.check_cooldown()
        skins = load_skin_data(config.SKIN_DATA_CACHE_PATH, offline=args.offline)
        grouped = group_by_collection_and_rarity(skins)
        log.info("Loaded %s skin records across %s collections", len(skins), len(grouped))
        prices = DiscoveryPrices.load(config.DATA_DIR, config.DISCOVERY_TTL,
            config.DISCOVERY_MAX_AGE, refresh=config.USE_SKINPORT_SNAPSHOT and not args.offline)
        log.info("Loaded %s estimated prices", len(prices.quotes))
        if pending is not None:
            candidates = pending
            log.info("Resuming %s unfinished candidates", len(pending))
        else:
            candidates, stats = generate(grouped, prices, budget, config, [args.rarity] if args.rarity else None)
        log.info("Local search: %s | shortlisted %s", dict(stats), len(candidates))
        if not prices.quotes:
            status = "Insufficient discovery prices; load a snapshot or enable bulk refresh"
        elif not candidates:
            status = "No contracts met the selected search criteria; missing prices may limit coverage"
        elif args.offline:
            status = f"Offline: {len(candidates)} estimated candidates; none live verified"
        elif not client.key:
            status = "Local candidates found; CSFLOAT_API_KEY is missing, so live verification was not attempted"
        else:
            shortlist = list(pending) if pending is not None else balanced_shortlist(candidates, config.LIVE_SHORTLIST)
            pending = list(shortlist)
            checkpoint.save(checkpoint_path, run_context, pending)
            for index, candidate in enumerate(shortlist, 1):
                log.info("Verifying candidate %s/%s: %s | estimated cost $%.2f, profit $%.2f",
                         index, len(shortlist), "; ".join(f"{n}x {b.name} ({b.wear})" for b,n in candidate.parts),
                         candidate.cost, candidate.profit)
                checked += 1
                result, reason = verify(candidate, grouped, prices, client, budget, config)
                log.info(reason)
                if result:
                    verified.append(result)
                # Only a terminal accepted/rejected candidate advances the queue.
                # Budget/cooldown exceptions leave the interrupted candidate first.
                pending.pop(0)
                checkpoint.save(checkpoint_path, run_context, pending)
            status = (f"{len(verified)} contracts met {config.SEARCH_MODE} criteria after live checks" if verified else
                      "Local candidates were found, but none met the selected criteria after live verification")
    except VerificationStopped as exc:
        status = str(exc)
        stop_reason = type(exc).__name__
    except (OSError, ValueError) as exc:
        status = f"Run could not complete: {type(exc).__name__}; check local data/configuration"
        log.error(status)
    # Rank the actual verified selections, rather than stopping at the first wins.
    ranked = sorted(verified, key=lambda r: r['score'], reverse=True)
    fresh = [r for r in ranked if 0 <= client.clock()-r['oldest_quote_at'] < client.ttl]
    if len(fresh) < len(ranked):
        status += f" | {len(ranked)-len(fresh)} results expired before reporting"
    if pending:
        status += f" | {len(pending)} unfinished candidates saved"
    selected = fresh[:config.MAX_RESULTS_TO_SHOW]
    # One results digest with its status. Routine batch pauses stay in logs.
    continuing = config.AUTO_RESUME and (stop_reason == 'CooldownActive' or
                  (stop_reason == 'RequestBudgetExceeded' and bool(pending)))
    if continuing:
        status += " | Automatic continuation enabled"
    if (selected or not continuing) and not args.offline and not args.no_discord and os.getenv('DISCORD_WEBHOOK_URL'):
        delivered = post_results(os.getenv('DISCORD_WEBHOOK_URL'), selected, status=status, ttl=client.ttl)
        sent = len(selected) if delivered else 0
    summary = {"status": status, "budget": budget, "local": dict(stats), "live_checked": checked,
               "verified": len(verified), "discord_results_sent": sent,
               "pending_candidates": len(pending or []),
               "stop_reason": stop_reason,
               "csfloat": client.stats, "completed_at": time.time()}
    write_json(f"{config.DATA_DIR}/last_run.json", {"summary": summary, "results": ranked})
    log.info("RUN SUMMARY: %s", summary)
    return summary


if __name__ == "__main__":
    from src.auto_resume import run
    try:
        run(main, config)
    except KeyboardInterrupt:
        log.info("Stopped; unfinished verification queue remains saved")
