"""Bounded automatic continuation of a saved queue, not repeated new scans."""
import logging
import os
import sys
import time
from src.storage import read_json, write_json
from src.discord_webhook import post_results


def run(batch, settings, argv=None, clock=time.time, sleep=time.sleep):
    args = list(sys.argv[1:] if argv is None else argv)
    enabled = settings.AUTO_RESUME and '--offline' not in args
    path = f'{settings.DATA_DIR}/auto_resume.json'
    cooldown_path = f'{settings.DATA_DIR}/csfloat_cooldown.json'
    stalled = 0
    previous_pending = None
    for index in range(settings.AUTO_MAX_BATCHES if enabled else 1):
        if enabled:
            until = max(read_json(path, {}).get('next_run_at', 0),
                        read_json(cooldown_path, {}).get('blocked_until', 0))
            if until > clock():
                logging.info('Automatic continuation waiting %.0f seconds', until-clock())
            while clock() < until:
                sleep(min(30, until-clock()))
                # Honor cooldown extensions made while waiting.
                until = max(until, read_json(cooldown_path, {}).get('blocked_until', 0))
        summary = batch(args)
        reason = summary.get('stop_reason')
        remaining = summary.get('pending_candidates', 0)
        retryable = reason == 'CooldownActive' or (reason == 'RequestBudgetExceeded' and remaining > 0)
        if not enabled or not retryable:
            if enabled:
                write_json(path, {'next_run_at': 0})
            return summary
        if reason == 'RequestBudgetExceeded':
            stalled = stalled + 1 if remaining == previous_pending else 1
            previous_pending = remaining
        if stalled >= 3 or index+1 >= settings.AUTO_MAX_BATCHES:
            message = 'Automatic continuation stopped: no queue progress in three batches' if stalled >= 3 else 'Automatic continuation reached its batch limit'
            message += '; unfinished candidates remain saved.'
            logging.warning(message)
            summary['auto_stop'] = message
            if '--no-discord' not in args and os.getenv('DISCORD_WEBHOOK_URL'):
                post_results(os.getenv('DISCORD_WEBHOOK_URL'), [], status=message)
            return summary
        until = max(clock()+settings.AUTO_RESUME_DELAY_SECONDS,
                    read_json(cooldown_path, {}).get('blocked_until', 0))
        write_json(path, {'next_run_at': until})
        message = f'Automatic continuation scheduled in {until-clock():.0f}s; {remaining} candidates pending.'
        logging.info(message)
        if remaining:
            args = ['--resume'] + (['--no-discord'] if '--no-discord' in args else [])
        else:
            # A startup cooldown can occur before a queue exists. Preserve the
            # original options and avoid asking for the budget again.
            original = args
            args = [str(summary['budget'])]
            for flag in ('--fresh', '--no-discord'):
                if flag in original:
                    args.append(flag)
            if '--rarity' in original:
                args += ['--rarity', original[original.index('--rarity')+1]]
    return summary
