import argparse
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional, Dict, Any
from ..db.store import Store

from fastapi.responses import RedirectResponse

app = FastAPI(title="Polymarket Indexer API")
store: Optional[Store] = None

@app.get("/", include_in_schema=False)
def read_root():
    return RedirectResponse(url="/docs")

@app.get("/markets/{slug}")
def get_market(slug: str):
    if not store:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    market = store.fetch_market_by_slug(slug)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    
    # Return market details as per requirement (markets table content)
    # The store returns a dict, which FastAPI automatically serializes to JSON
    return market

@app.get("/markets/{slug}/trades")
def get_market_trades(
    slug: str, 
    limit: int = 100, 
    cursor: int = 0
):
    if not store:
        raise HTTPException(status_code=500, detail="Database not initialized")

    market = store.fetch_market_by_slug(slug)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    
    market_id = market['id']
    trades = store.fetch_trades_for_market(market_id, limit, cursor)
    
    return trades

def start_server():
    parser = argparse.ArgumentParser(description="Polymarket Indexer API Server")
    parser.add_argument("--db", default="./indexer.db", help="Path to SQLite database")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to run the server on")
    
    args = parser.parse_args()
    
    global store
    store = Store(args.db)
    # Ensure DB exists/tables created (optional, but good practice if valid db path)
    if not store.get_sync_state(): # fast check if connected
        # Maybe init if new? Requirement implies reading existing DB.
        pass

    print(f"Starting API Server on {args.host}:{args.port} using DB: {args.db}")
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    start_server()
