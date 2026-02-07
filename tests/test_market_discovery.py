import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Add project root to python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.indexer.market_discovery import fetch_markets_by_slug, process_market_data

class TestMarketDiscovery(unittest.TestCase):

    @patch('src.indexer.market_discovery.requests.get')
    def test_fetch_markets_by_slug(self, mock_get):
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "slug": "event-slug",
                "markets": [
                    {"slug": "market-slug-1"},
                    {"slug": "market-slug-2"}
                ]
            }
        ]
        mock_get.return_value = mock_response

        markets = fetch_markets_by_slug("event-slug")
        self.assertEqual(len(markets), 2)
        self.assertEqual(markets[0]['slug'], "market-slug-1")

    def test_process_market_data_dynamic_outcomes(self):
        # Case 1: Standard [No, Yes]
        raw_market_1 = {
             "slug": "market-1",
             "conditionId": "0xABC",
             "questionID": "0xQ123",
             "clobTokenIds": ["0xNO_TOKEN", "0xYES_TOKEN"],
             "outcomes": ["No", "Yes"],
             "active": True
        }
        
        result = process_market_data(raw_market_1)
        self.assertEqual(result['condition_id'], "0xabc") # Lowercase check
        self.assertEqual(result['yes_token_id'], "0xYES_TOKEN")
        self.assertEqual(result['no_token_id'], "0xNO_TOKEN")
        self.assertEqual(result['status'], "ACTIVE")

        # Case 2: Reversed [Yes, No] (Hypothetical, but testing dynamic logic)
        raw_market_2 = {
             "slug": "market-2",
             "conditionId": "0xDEF",
             "clobTokenIds": ["0xYES_TOKEN_2", "0xNO_TOKEN_2"],
             "outcomes": ["Yes", "No"]
        }
        
        result_2 = process_market_data(raw_market_2)
        self.assertEqual(result_2['yes_token_id'], "0xYES_TOKEN_2")
        self.assertEqual(result_2['no_token_id'], "0xNO_TOKEN_2")

    def test_process_market_data_missing_outcomes(self):
        raw_market = {
            "slug": "market-bad",
            "clobTokenIds": ["0x1", "0x2"],
            "outcomes": [] # Missing outcomes
        }
        result = process_market_data(raw_market)
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
