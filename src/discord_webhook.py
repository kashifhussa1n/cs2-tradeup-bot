"""Validated Discord digests with compact embeds and full-detail attachments."""
import time
import requests
from src.rules import tradeup_eligible
from decimal import Decimal


def float_text(value):
    """Show decimal notation without rounding away supplied float precision."""
    text = format(Decimal(str(value)), 'f')
    whole, _, fraction = text.partition('.')
    return whole + '.' + fraction.ljust(9, '0')


def input_fields(rows):
    """Clickable buy links stay inside embeds, where they do not unfurl."""
    from collections import defaultdict
    groups = defaultdict(list)
    for index, row in enumerate(rows, 1):
        groups[row['name']].append((index, row))
    fields = []
    for name, listings in groups.items():
        title = f"{len(listings)} x {name}"[:230]
        lines = []
        for index, row in listings:
            line = (f"[Buy #{index}](https://csfloat.com/item/{row['id']}) | "
                    f"${row['price']:.2f} | `{float_text(row['float_value'])}`")
            if lines and len('\n'.join(lines)) + len(line) + 1 > 1000:
                fields.append({'name': title, 'value': '\n'.join(lines)})
                title = f"{name[:210]} (continued)"
                lines = []
            lines.append(line)
        fields.append({'name': title, 'value': '\n'.join(lines)})
    return fields


def format_result(result, ttl=120, now=None):
    now = time.time() if now is None else now
    for row in result.get("inputs", []) + result.get("outcomes", []):
        name = row.get("skin") or row.get("skin_name") or row.get("name", "")
        if not tradeup_eligible({"name": name}, row.get("collection")):
            raise ValueError("Refusing non-trade-up-eligible result")
    mode = result.get("search_mode", "expected_value")
    if mode not in {"upside", "expected_value"}:
        raise ValueError("Unknown search mode")
    if mode == "upside":
        fee = result["sell_fee_percent"]
        gains = [(o["price"]*(1-fee/100)-result["cost"], o["probability"])
                 for o in result["outcomes"]]
        chance = sum(p for gain,p in gains if gain > 0)
        if (not gains or chance <= 0 or chance*100 < result["min_win_chance_percent"]
                or max(g for g,p in gains) <= 0
                or max(g for g,p in gains) < result["min_win_profit_dollars"]):
            raise ValueError("No qualifying profitable outcome")
    if (result.get("verified") is not True or (mode == "expected_value" and result["profit"] <= 0)
        or result["cost"] > result["budget"] or len(result["inputs"]) != 10
        or len({x["id"] for x in result["inputs"]}) != 10
        or not 0 <= now-result["oldest_quote_at"] < ttl):
        raise ValueError("Refusing unverified, stale, losing or invalid result")
    title = "LIVE-CHECKED CHANCE-OF-PROFIT CONTRACT" if mode == "upside" else "VERIFIED TRADE-UP"
    lines = [f"{title} | {result['input_rarity']} -> next rarity",
        f"Budget ${result['budget']:.2f} | Actual inputs ${result['cost']:.2f}", "INPUTS"]
    if mode == "upside":
        lines[2:2] = [f"Best possible net profit: ${max(g for g,p in gains):+.2f} | Worst outcome: ${min(g for g,p in gains):+.2f}",
                       f"Profit chance: {chance:.2%} | Expected profit: ${result['profit']:+.2f}",
                       "Negative expected value: losses exceed gains on average." if result['profit'] < 0 else
                       "Positive expected value; a losing outcome is still possible."]
    for row in result["inputs"]:
        lines.append(f"{row['name']} | ${row['price']:.2f} | float {float_text(row['float_value'])} | https://csfloat.com/item/{row['id']}")
    lines += ["Calculator comparison: use these individual input floats and prices; a generic wear-tier float changes the contract.",
              f"Average raw input float: {result['average_float']:.9f}",
              f"Average normalized float: {result['average_normalized_float']:.9f}", "OUTPUTS"]
    for row in result["outcomes"]:
        gain = row['price']*(1-result.get('sell_fee_percent',result['selling_fees']/result['gross_ev']*100)/100)-result['cost']
        lines.append(f"{row['skin_name']} | {row['probability']:.2%} | {row['wear']} | float {float_text(row['output_float'])} | asking price ${row['price']:.2f} | net profit ${gain:+.2f}")
    lines += [f"Gross EV ${result['gross_ev']:.2f} | Selling fees ${result['selling_fees']:.2f}",
        f"Net EV ${result['net_ev']:.2f} | Expected profit ${result['profit']:+.2f} | ROI {result['roi']:+.2f}%",
        f"Probability of profitable outcome: {result['chance_profit']:.2%}",
        f"Oldest verification quote: {now-result['oldest_quote_at']:.0f}s ago",
        f"Discovery estimate age: {max(0, now-result['discovery_oldest_at'])/3600:.1f}h",
        "Checked: 10 distinct input listings, exact floats, input costs, all output prices.",
        "Output valuation uses current plain listing asks, not completed sales. Availability can change. Results may share listings; evaluate as alternatives."]
    chunks, current = [], ""
    for line in lines:
        if len(current)+len(line)+1 > 1900:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current:
        chunks.append(current)
    return chunks


def embed_length(embed):
    return (len(embed.get("title", "")) + len(embed.get("description", ""))
            + len(embed.get("footer", {}).get("text", ""))
            + sum(len(f["name"])+len(f["value"]) for f in embed.get("fields", [])))


def result_embed(result, rank, now):
    fee = result.get('sell_fee_percent', result['selling_fees']/result['gross_ev']*100)
    gains = [(o['price']*(1-fee/100)-result['cost'], o) for o in result['outcomes']]
    output_lines = []
    for gain, row in sorted(gains, key=lambda item:item[0], reverse=True):
        line = (f"**{row['skin_name']}** ({row['wear']})\n"
                f"Float `{float_text(row['output_float'])}`\n"
                f"{row['probability']:.1%} chance | ${row['price']:.2f} ask | **${gain:+.2f} net**")
        if sum(len(x)+1 for x in output_lines)+len(line) > 900:
            output_lines.append('Remaining outcomes are in the attached report.')
            break
        output_lines.append(line)
    return {
        'title': f"#{rank} | {result['input_rarity']} trade-up",
        'description': ('**Live-checked listings** | Chance-of-profit contract' if result.get('search_mode') == 'upside'
                        else '**Live-checked listings** | Positive expected value')
                       + ('\n**Negative EV: loses money on average.**' if result['profit'] < 0 else ''),
        'color': 0xD69E36 if result['profit'] < 0 else 0x248768,
        'fields': [
            {'name':'Input cost / Budget','value':f"${result['cost']:.2f} / ${result['budget']:.2f}",'inline':True},
            {'name':'Chance of profit','value':f"{result['chance_profit']:.1%}",'inline':True},
            {'name':'Best net profit','value':f"${max(g for g,o in gains):+.2f}",'inline':True},
            {'name':'Expected profit / ROI','value':f"${result['profit']:+.2f} / {result['roi']:+.1f}%",'inline':True},
            {'name':'Worst outcome','value':f"${min(g for g,o in gains):+.2f}",'inline':True},
            {'name':'Selling fee','value':f"{fee:g}%",'inline':True},
            *input_fields(result['inputs']),
            {'name':'Possible outputs (after-fee profit)','value':'\n'.join(output_lines)},
            {'name':'Float summary','value':f"Average input: `{float_text(result['average_float'])}`\nNormalized average: `{float_text(result['average_normalized_float'])}`\nUse the individual floats above in your calculator. Complete report also attached."},
        ],
        'footer':{'text':f"Quotes up to {now-result['oldest_quote_at']:.0f}s old. Asking prices are not guaranteed sale proceeds. Contracts may share listings."}
    }


def build_messages(results, status='Scan complete', ttl=120, now=None):
    """One digest where possible; paginate only at Discord's embed limits."""
    now = time.time() if now is None else now
    if not results:
        return [({'allowed_mentions':{'parse':[]}, 'embeds':[{
            'title':'CS2 trade-up scan', 'description':status[:4000], 'color':0x607080}]}, None)]
    # Validate every result before constructing anything that can be sent.
    reports = [''.join(format_result(r, ttl, now)) for r in results]
    pages, embeds, details, size = [], [], [], 0
    for rank,(result,report) in enumerate(zip(results,reports),1):
        embed=result_embed(result,rank,now)
        length=embed_length(embed)
        if embeds and (size+length>5800 or len(embeds)==10):
            pages.append((embeds,details))
            embeds,details,size=[],[],0
        embeds.append(embed)
        details.append(f"CONTRACT #{rank}\n{report}")
        size+=length
    if embeds:
        pages.append((embeds,details))
    return [({'content':f"**{len(results)} live-checked contract(s)** | Report {i}/{len(pages)}\n{status[:1500]}",
              'allowed_mentions':{'parse':[]}, 'embeds':embeds}, '\n\n'.join(details).encode('utf8'))
            for i,(embeds,details) in enumerate(pages,1)]


def post_results(webhook_url, results, status="Scan complete", ttl=120):
    import json
    for index,(payload,attachment) in enumerate(build_messages(results,status,ttl),1):
        try:
            if attachment is None:
                response=requests.post(webhook_url,json=payload,timeout=15)
            else:
                response=requests.post(webhook_url,data={'payload_json':json.dumps(payload)},
                    files={'files[0]':(f'tradeup-details-{index}.txt',attachment,'text/plain; charset=utf-8')},timeout=15)
            response.raise_for_status()
        except requests.RequestException:
            import logging
            logging.error("Discord delivery failed")
            return False
    return True
