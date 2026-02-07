import os
import logging
from decimal import Decimal
from typing import List, Dict, Optional, Any
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
# from web3.middleware import geth_poa_middleware # Deprecated in v7
from eth_abi import decode
from hexbytes import HexBytes

from ..db.store import Store
from .market_discovery import discover_and_store_markets

logger = logging.getLogger(__name__)

# ABI for OrderFilled event
ORDER_FILLED_ABI = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "internalType": "bytes32", "name": "orderHash", "type": "bytes32"},
        {"indexed": True, "internalType": "address", "name": "maker", "type": "address"},
        {"indexed": True, "internalType": "address", "name": "taker", "type": "address"},
        {"indexed": False, "internalType": "uint256", "name": "makerAssetId", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "takerAssetId", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "makerAmountFilled", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "takerAmountFilled", "type": "uint256"},
        {"indexed": False, "internalType": "uint256", "name": "fee", "type": "uint256"}
    ],
    "name": "OrderFilled",
    "type": "event"
}

# Calculated Topic Hash for OrderFilled
# search online or calc: web3.keccak(text="OrderFilled(bytes32,address,address,uint256,uint256,uint256,uint256,uint256)").hex()
# But here we will use web3 contract events to handle it easily or just filter by topic.
# Polymarket Exchange Addresses (Mainnet Polygon)
# CTF Exchange: 0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E (Binary)
# NegRisk Exchange: 0xC5d563a36AE78145C45a50134d48A1215220f80a
# We can just fetch logs for these addresses or filter by topic.

EXCHANGE_ADDRESSES = [
    "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E", # CTF Exchange
    "0xC5d563a36AE78145C45a50134d48A1215220f80a"  # NegRisk Adapter/Exchange
]

class Indexer:
    def __init__(self, rpc_url: str, store: Store):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.store = store
        self.contract = self.w3.eth.contract(abi=[ORDER_FILLED_ABI])
        self.block_timestamp_cache = {} # Simple cache: {block_number: timestamp}

    def get_block_timestamp(self, block_number: int) -> int:
        if block_number in self.block_timestamp_cache:
            return self.block_timestamp_cache[block_number]
        
        try:
            block = self.w3.eth.get_block(block_number)
            timestamp = block['timestamp']
            self.block_timestamp_cache[block_number] = timestamp
            return timestamp
        except Exception as e:
            logger.error(f"Failed to get timestamp for block {block_number}: {e}")
            return 0

    def run_indexer(self, from_block: int, to_block: int, event_slug: Optional[str] = None):
        """
        Main loop to index trades in a block range.
        """
        logger.info(f"Indexing trades from block {from_block} to {to_block}...")
        
        # Filter parameters
        filter_params = {
            "fromBlock": from_block,
            "toBlock": to_block,
            "topics": [self.contract.events.OrderFilled().topic] # Filter by OrderFilled topic
            # We can optionally filter by address, but let's cast a wide net or specific list
            # "address": EXCHANGE_ADDRESSES
        }
        
        try:
            logs = self.w3.eth.get_logs(filter_params)
            logger.info(f"Found {len(logs)} logs.")
        except Exception as e:
            logger.error(f"Error fetching logs: {e}")
            return []

        processed_trades = []

        for log in logs:
            try:
                trade = self.decode_and_process_log(log, event_slug)
                if trade:
                    processed_trades.append(trade)
            except Exception as e:
                logger.error(f"Error processing log {log['transactionHash'].hex()}: {e}")
                continue
        
        # Batch insert
        if processed_trades:
            self.store.insert_trades(processed_trades)
            self.store.update_sync_state(to_block)
            logger.info(f"Inserted {len(processed_trades)} trades.")
        
        return processed_trades

    def decode_and_process_log(self, log, event_slug: Optional[str]) -> Optional[Dict[str, Any]]:
        # 1. Decode Log
        try:
            event_data = self.contract.events.OrderFilled().process_log(log)
            args = event_data['args']
        except Exception as e:
            # logger.warn(f"Failed to decode log: {e}") 
            # might not be OrderFilled or ABI mismatch
            return None

        # Filter out Exchange wrapper logs
        exchange_address = log['address']
        if args['taker'].lower() == exchange_address.lower():
            return None

        # 2. Extract Data
        maker_asset_id = args['makerAssetId']
        taker_asset_id = args['takerAssetId']
        maker_amount = args['makerAmountFilled']
        taker_amount = args['takerAmountFilled']
        
        price = Decimal(0)
        side = ""
        token_id_int = 0
        outcome = "" # 'YES' or 'NO'

        # Logic for price and side
        if maker_asset_id == 0:
            # Maker BUYS Token with USDC
            try:
                price = Decimal(maker_amount) / Decimal(taker_amount)
            except:
                price = Decimal(0)
            token_id_int = taker_asset_id
            side = "BUY"
        else:
            # Maker SELLS Token for USDC
            try:
                price = Decimal(taker_amount) / Decimal(maker_amount)
            except:
                price = Decimal(0)
            token_id_int = maker_asset_id
            side = "SELL"

        # Format Token ID: Lowercase Hex
        token_id_hex = hex(token_id_int).lower()

        # 3. Find Market and Outcome
        market = self.store.fetch_market_by_token_id(token_id_hex)
        
        if not market:
            # Auto-discovery attempt
            if event_slug:
                logger.info(f"Market not found for token {token_id_hex}. Triggering discovery for slug: {event_slug}")
                discover_and_store_markets(event_slug, self.store)
                # Retry fetch
                market = self.store.fetch_market_by_token_id(token_id_hex)
        
        market_id = None
        if market:
            market_id = market['id']
            if market['yes_token_id'] == token_id_hex:
                outcome = "YES"
            elif market['no_token_id'] == token_id_hex:
                outcome = "NO"
        else:
            logger.warning(f"Market not found for token {token_id_hex} even after discovery attempt. Skipping trade.")
            return None

        # 4. Get Timestamp
        block_number = log['blockNumber']
        timestamp = self.get_block_timestamp(block_number)

        # 5. Construct Trade Record
        # Size logic: Use the Token Amount (not USDC amount)
        size = Decimal(taker_amount) if side == "BUY" else Decimal(maker_amount)
        # Convert to float for DB (retaining decimals logic might be needed but float is requested)
        # Actually usually size is / 1e6 maybe? The user prompt implies raw or simple conversion.
        # Let's keep raw unit or simple float.
        # Polymarket tokens are usually 6 decimals (USDC) and Collateral too?
        # Let's store as float for now as per schema 'REAL'.
        # NOTE: Stage 1 said "price = taker_amount / maker_amount".
        
        return {
            "tx_hash": self.w3.to_hex(log['transactionHash']),
            "log_index": log['logIndex'],
            "market_id": market_id,
            "maker": args['maker'],
            "taker": args['taker'],
            "side": side,
            "outcome": outcome,
            "price": float(price),
            "size": float(size),
            "timestamp": timestamp,
            # Extra fields not in DB schema but useful for debug, remove if strict
            "token_id": token_id_hex, 
            "block_number": block_number
        }
