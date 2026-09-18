import copy
import json
import tempfile
import unittest
from unittest.mock import Mock, patch
from src.discord_webhook import build_messages, embed_length, post_results
from src.auto_resume import run
from test_pipeline import Clock, settings


def result():
    return {'verified':True,'budget':20,'cost':10,'gross_ev':20,'selling_fees':2.6,
        'net_ev':17.4,'profit':7.4,'roi':74,'chance_profit':1,'oldest_quote_at':1000,
        'discovery_oldest_at':900,'average_float':.2,'average_normalized_float':.2,
        'input_rarity':'Restricted','sell_fee_percent':13,
        'inputs':[{'id':str(i),'name':'A (Field-Tested)','skin':'A','price':1,'float_value':.2}
                  for i in range(10)],
        'outcomes':[{'skin_name':'X','wear':'Field-Tested','output_float':.2,'probability':1,'price':20}]}


class DigestTests(unittest.TestCase):
    def test_full_contract_one_message_without_link_previews(self):
        messages=build_messages([result()],now=1000)
        self.assertEqual(len(messages),1)
        payload,attachment=messages[0]
        self.assertEqual(len(payload['embeds']),1)
        self.assertNotIn('https://',payload['content'])
        card=json.dumps(payload['embeds'])
        self.assertEqual(card.count('https://csfloat.com/item/'),10)
        self.assertEqual(card.count('[Buy #'),10)
        self.assertIn('`0.200000000`',card)
        self.assertEqual(attachment.count(b'https://csfloat.com/item/'),10)
        self.assertIn(b'0.200000000',attachment)
        self.assertEqual(payload['allowed_mentions'],{'parse':[]})

    def test_long_listing_ids_and_full_precision_are_visible(self):
        r=result()
        for i,row in enumerate(r['inputs']):
            row.update(id=str(1014064329340881704+i),float_value=.05044854812345678)
        payload,attachment=build_messages([r],now=1000)[0]
        text=json.dumps(payload['embeds'])
        for row in r['inputs']:
            self.assertIn(f"https://csfloat.com/item/{row['id']}",text)
        self.assertEqual(text.count('0.05044854812345678'),10)
        self.assertIn(b'0.05044854812345678',attachment)
        self.assertTrue(all(len(f['value'])<=1024 for e in payload['embeds'] for f in e['fields']))

    def test_tiny_float_is_decimal_not_scientific_notation(self):
        from src.discord_webhook import float_text
        self.assertEqual(float_text(3.7e-8),'0.000000037')

    def test_many_results_respect_total_embed_limits_without_losing_details(self):
        messages=build_messages([copy.deepcopy(result()) for _ in range(20)],now=1000)
        self.assertLess(len(messages),20)
        count=0
        for payload,attachment in messages:
            self.assertLessEqual(len(payload['embeds']),10)
            self.assertLessEqual(sum(embed_length(e) for e in payload['embeds']),6000)
            self.assertLessEqual(len(payload['content']),2000)
            for embed in payload['embeds']:
                self.assertLessEqual(len(embed['fields']),25)
                self.assertTrue(all(len(f['value'])<=1024 for f in embed['fields']))
            count+=attachment.count(b'CONTRACT #')
        self.assertEqual(count,20)

    def test_one_multipart_post_instead_of_split_text_posts(self):
        with patch('src.discord_webhook.time.time',return_value=1000), \
             patch('src.discord_webhook.requests.post') as post:
            self.assertTrue(post_results('fake',[result()]))
        post.assert_called_once()
        self.assertIn('payload_json',post.call_args.kwargs['data'])
        self.assertIn('files[0]',post.call_args.kwargs['files'])

    def test_negative_ev_is_visible_on_card(self):
        r=result()
        r.update(search_mode='upside',gross_ev=8,net_ev=6.96,selling_fees=1.04,
            profit=-3.04,roi=-30.4,chance_profit=.2,min_win_chance_percent=20,min_win_profit_dollars=.1)
        r['outcomes']=[{**r['outcomes'][0],'probability':.2},
                       {**r['outcomes'][0],'skin_name':'Y','price':5,'probability':.8}]
        payload,_=build_messages([r],now=1000)[0]
        self.assertIn('Negative EV',payload['embeds'][0]['description'])
        self.assertIn('-3.04',json.dumps(payload))

    def test_continuation_does_not_post_countdown(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg=settings(DATA_DIR=directory,AUTO_RESUME=True,AUTO_RESUME_DELAY_SECONDS=300,AUTO_MAX_BATCHES=10)
            clock=Clock()
            batch=Mock(side_effect=[{'budget':20,'stop_reason':'RequestBudgetExceeded','pending_candidates':1},
                                    {'budget':20,'stop_reason':None,'pending_candidates':0}])
            with patch.dict('os.environ',{'DISCORD_WEBHOOK_URL':'fake'}),patch('src.auto_resume.post_results') as post:
                run(batch,cfg,['20'],clock,clock.sleep)
            post.assert_not_called()
