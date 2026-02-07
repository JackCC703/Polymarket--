import os
import json
import argparse
from decimal import Decimal
from web3 import Web3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ABI for OrderFilled event
# Event signature: OrderFilled(bytes32 indexed orderHash, address indexed maker, address indexed taker, uint256 makerAssetId, uint256 takerAssetId, uint256 makerAmountFilled, uint256 takerAmountFilled, uint256 fee)
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

def decode_trades(tx_hash: str, rpc_url: str = None) -> list:
    if not rpc_url:
        rpc_url = os.getenv("RPC_URL")
    
    if not rpc_url:
        raise ValueError("RPC_URL not set")

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    tx_receipt = w3.eth.get_transaction_receipt(tx_hash)
    
    # Contract interface for decoding logs
    # We can use a minimal contract instance to decode logs
    contract = w3.eth.contract(abi=[ORDER_FILLED_ABI])
    
    trades = []
    
    for log in tx_receipt['logs']:
        try:
            # Attempt to decode log as OrderFilled
            event = contract.events.OrderFilled().process_log(log)
            args = event['args']
            
            # Filter out Exchange wrapper logs if checking strictly,
            # but usually duplicated logs have 'taker' as the Exchange contract address which triggers the match?
            # Stage 1 Guide says: 
            # "通常会有...一条'taker汇总'的OrderFilled，其中taker字段会显示为Exchange合约地址本身...过滤掉 taker == exchange_address"
            # We need the exchange address. The log address itself IS the exchange address.
            exchange_address = log['address']
            
            if args['taker'].lower() == exchange_address.lower():
                continue

            maker_asset_id = args['makerAssetId']
            taker_asset_id = args['takerAssetId']
            maker_amount = args['makerAmountFilled']
            taker_amount = args['takerAmountFilled']
            
            # Logic for price and side
            # makerAssetId == 0 means Maker is spending USDC (BUYING outcome token)
            # takerAssetId == 0 means Maker is spending Token (SELLING outcome token) -> Wait
            # In Polymarket:
            # makerAssetId = 0 (USDC) -> Maker BUYS token
            # takerAssetId = 0 (USDC) -> Maker SELLS token (gets USDC)
            
            price = Decimal(0)
            side = ""
            token_id = ""
            
            # Calculate price: USDC amount / Token amount
            # Note: Both are usually in base units. 
            # If USDC is 6 decimals and Token is "1e6 per unit", the ratio is same as raw integers ratio.
            
            if maker_asset_id == 0:
                # Maker Spends USDC -> Maker BUYS Info
                # Price = MakerAmt (USDC) / TakerAmt (Token)
                try:
                    price = Decimal(maker_amount) / Decimal(taker_amount)
                except:
                    price = Decimal(0)
                
                token_id = hex(taker_asset_id)
                side = "BUY"
            else:
                # Maker Spends Token -> Maker SELLS Info
                # Taker Spends USDC
                # Price = TakerAmt (USDC) / MakerAmt (Token)
                try:
                    price = Decimal(taker_amount) / Decimal(maker_amount)
                except:
                    price = Decimal(0)
                    
                token_id = hex(maker_asset_id)
                side = "SELL"

            # Format fields
            trade = {
                "tx_hash": tx_hash,
                "log_index": log['logIndex'],
                "exchange": exchange_address,
                "maker": args['maker'],
                "taker": args['taker'],
                "maker_asset_id": str(maker_asset_id),
                "taker_asset_id": str(taker_asset_id),
                "maker_amount": str(maker_amount),
                "taker_amount": str(taker_amount),
                "price": f"{price:.6f}".rstrip('0').rstrip('.') if '.' in f"{price:.6f}" else f"{price:.6f}",
                # Ensure price format is string float
                # Stage 1 example says "1.0", "0.5".
                # Let's start with simple str(price) or float formatting
                # But example showed "1.0". 
                "token_id": token_id, 
                "side": side
            }
            # Refine price formatting to match example exactly if possible
            trade["price"] = str(price)

            trades.append(trade)

        except Exception as e:
            # Not an OrderFilled event or decode failed
            continue
            
    return trades

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trade Decoder")
    parser.add_argument("--tx-hash", required=True, help="Transaction Hash")
    parser.add_argument("--output", help="Output JSON file path")
    
    args = parser.parse_args()
    
    try:
        trades = decode_trades(args.tx_hash)
        print(json.dumps(trades, indent=2))
        
        if args.output:
            # Create directory if not exists
            os.makedirs(os.path.dirname(args.output), exist_ok=True)
            with open(args.output, 'w') as f:
                json.dump(trades, f, indent=2)
                
    except Exception as e:
        print(f"Error: {e}")
