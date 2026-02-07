import argparse
import os
import json
import logging
from typing import Dict, Any, List
from dotenv import load_dotenv

from .db.store import Store
from .indexer.run import Indexer
from .indexer.market_discovery import discover_and_store_markets

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Polymarket Indexer Demo")
    parser.add_argument("--tx-hash", help="Transaction hash to index")
    parser.add_argument("--event-slug", help="Event slug for market discovery")
    parser.add_argument("--reset-db", action="store_true", help="Reset the database")
    parser.add_argument("--from-block", type=int, help="Start block number")
    parser.add_argument("--to-block", type=int, help="End block number")
    parser.add_argument("--output", help="Output JSON file path")
    parser.add_argument("--db", default="./indexer.db", help="Path to SQLite database")

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()
    rpc_url = os.getenv("RPC_URL")
    if not rpc_url:
        logger.error("RPC_URL environment variable not set")
        return

    # Initialize Store
    db_path = args.db
    if args.reset_db and os.path.exists(db_path):
        os.remove(db_path)
        logger.info(f"Database reset: {db_path}")

    store = Store(db_path)
    store.init_db()

    # Initialize Indexer
    indexer = Indexer(rpc_url, store)

    # Market Discovery (if slug provided)
    if args.event_slug:
        logger.info(f"Running market discovery for slug: {args.event_slug}")
        discover_and_store_markets(args.event_slug, store)

    trades: List[Dict[str, Any]] = []

    # Logic decision
    if args.tx_hash:
        logger.info(f"Indexing transaction: {args.tx_hash}")
        try:
            tx_receipt = indexer.w3.eth.get_transaction_receipt(args.tx_hash)
            block_number = tx_receipt['blockNumber']
            # We fetch logs for this block range to catch the specific tx logs
            # Or we could filter by blockhash but fetch_logs logic uses ranges.
            # Using block range [block, block] is safe.
            block_trades = indexer.run_indexer(block_number, block_number, args.event_slug)
            
            # Filter specifically for this tx hash from the block trades
            trades = [t for t in block_trades if t['tx_hash'].lower() == args.tx_hash.lower()]
            logger.info(f"Found {len(trades)} trades in transaction {args.tx_hash}")
        except Exception as e:
            logger.error(f"Error fetching transaction {args.tx_hash}: {e}")
    
    elif args.from_block and args.to_block:
        logger.info(f"Indexing range: {args.from_block} - {args.to_block}")
        trades = indexer.run_indexer(args.from_block, args.to_block, args.event_slug)
    
    else:
        logger.warning("No action specified. Use --tx-hash or --from-block/--to-block.")

    # Prepare Output
    inserted_count = len(trades) # In this run script, we return processed trades. Store.insert_trades handles insertion.
    
    # We want to show what IS in DB or what was processed. 
    # The requirement says "inserted_trades", "sample_trades".
    # Since run_indexer returns processed_trades, we can use that.
    
    # Construct stage2 output format
    output_data = {
        "stage2": {
            "from_block": args.from_block if args.from_block else (trades[0]['block_number'] if trades else 0),
            "to_block": args.to_block if args.to_block else (trades[-1]['block_number'] if trades else 0),
            "inserted_trades": inserted_count,
            "market_slug": args.event_slug, 
            "market_id": trades[0]['market_id'] if trades else None, # Sample from first trade
            "sample_trades": trades[:5] if trades else [],
            "db_path": db_path
        }
    }

    if args.output:
        # import os # Already imported globally
        output_dir = os.path.dirname(args.output)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        logger.info(f"Output written to {args.output}")
    else:
        print(json.dumps(output_data, indent=2))

if __name__ == "__main__":
    main()
