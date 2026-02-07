import sys
import os
import sqlite3
import unittest

# Add src to python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from db.store import Store

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db_path = 'test_polymarket.db'
        self.store = Store(self.db_path)
        self.store.init_db()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_upsert_market(self):
        market_data = {
            'slug': 'test-market',
            'condition_id': '0x123',
            'question_id': '0x456',
            'yes_token_id': '0xYES',
            'no_token_id': '0xNO',
            'status': 'ACTIVE'
        }
        self.store.upsert_market(market_data)

        # Verify insertion
        market = self.store.fetch_market_by_slug('test-market')
        self.assertIsNotNone(market)
        self.assertEqual(market['condition_id'], '0x123')

        # Test Update
        market_data['status'] = 'RESOLVED'
        self.store.upsert_market(market_data)
        
        market = self.store.fetch_market_by_slug('test-market')
        self.assertEqual(market['status'], 'RESOLVED')

    def test_insert_trades_idempotency(self):
        # Insert a market first
        market_data = {
            'slug': 'test-market',
            'condition_id': '0x123',
            'question_id': '0x456',
            'yes_token_id': '0xYES',
            'no_token_id': '0xNO',
            'status': 'ACTIVE'
        }
        self.store.upsert_market(market_data)
        market = self.store.fetch_market_by_slug('test-market')
        market_id = market['id']

        trades = [
            {
                'tx_hash': '0xTX1',
                'log_index': 1,
                'market_id': market_id,
                'maker': '0xMaker',
                'taker': '0xTaker',
                'side': 'BUY',
                'outcome': 'YES',
                'price': 0.5,
                'size': 100.0,
                'timestamp': 1000
            }
        ]

        # First insert
        self.store.insert_trades(trades)
        
        conn = self.store.get_connection()
        count = conn.execute("SELECT count(*) as c FROM trades").fetchone()['c']
        self.assertEqual(count, 1)

        # Second insert (duplicate)
        self.store.insert_trades(trades)
        
        count = conn.execute("SELECT count(*) as c FROM trades").fetchone()['c']
        self.assertEqual(count, 1) # Should still be 1
        conn.close()

    def test_sync_state(self):
        self.store.update_sync_state(12345)
        last_block = self.store.get_sync_state()
        self.assertEqual(last_block, 12345)

        self.store.update_sync_state(12346)
        last_block = self.store.get_sync_state()
        self.assertEqual(last_block, 12346)

    def test_fetch_market_by_token_id(self):
        market_data = {
            'slug': 'test-market',
            'condition_id': '0x123',
            'question_id': '0x456',
            'yes_token_id': '0xYES',
            'no_token_id': '0xNO',
            'status': 'ACTIVE'
        }
        self.store.upsert_market(market_data)

        market = self.store.fetch_market_by_token_id('0xYES')
        self.assertIsNotNone(market)
        self.assertEqual(market['slug'], 'test-market')

        market = self.store.fetch_market_by_token_id('0xNO')
        self.assertIsNotNone(market)
        self.assertEqual(market['slug'], 'test-market')

if __name__ == '__main__':
    unittest.main()
