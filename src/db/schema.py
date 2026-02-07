import sqlite3

def create_tables(conn: sqlite3.Connection):
    """
    Creates the necessary tables for the Polymarket Indexer.
    """
    cursor = conn.cursor()

    # 1. markets table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS markets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT,
        condition_id TEXT UNIQUE,
        question_id TEXT,
        yes_token_id TEXT,
        no_token_id TEXT,
        status TEXT
    );
    """)

    # Create index for slug separately as it might be useful for lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_markets_slug ON markets(slug);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_markets_yes_token_id ON markets(yes_token_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_markets_no_token_id ON markets(no_token_id);")

    # 2. trades table
    # (tx_hash, log_index) must be a unique index for idempotency
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tx_hash TEXT NOT NULL,
        log_index INTEGER NOT NULL,
        market_id INTEGER,
        maker TEXT,
        taker TEXT,
        side TEXT, -- 'BUY' or 'SELL'
        outcome TEXT, -- 'YES' or 'NO'
        price REAL,
        size REAL,
        timestamp INTEGER,
        FOREIGN KEY(market_id) REFERENCES markets(id)
    );
    """)

    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_tx_log ON trades(tx_hash, log_index);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_market_id ON trades(market_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);")


    # 3. sync_state table
    # Used to track the last synced block number
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sync_state (
        key TEXT PRIMARY KEY,
        value INTEGER
    );
    """)

    # Initialize last_block if it doesn't exist
    cursor.execute("INSERT OR IGNORE INTO sync_state (key, value) VALUES ('last_block', 0);")

    # 4. events table
    # Used to store raw event metadata if needed, or structured event logs
    # As per requirement: "events: Used to store event metadata."
    # We will store basic event info here.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tx_hash TEXT,
        block_number INTEGER,
        event_name TEXT,
        data TEXT, -- JSON payload of the event
        timestamp INTEGER
    );
    """)

    conn.commit()
