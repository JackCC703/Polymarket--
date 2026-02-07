import sqlite3
import os
from typing import List, Dict, Optional, Any
from .schema import create_tables

class Store:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_connection(self) -> sqlite3.Connection:
        """Establishes and returns a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable accessing columns by name
        return conn

    def init_db(self):
        """Initializes the database and creates tables if they don't exist."""
        # Ensure the directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            
        conn = self.get_connection()
        try:
            create_tables(conn)
        finally:
            conn.close()

    def upsert_market(self, market_data: Dict[str, Any]):
        """
        Inserts or updates a market.
        Matches primarily on `condition_id`.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Check if market exists by condition_id
            cursor.execute("SELECT id FROM markets WHERE condition_id = ?", (market_data.get('condition_id'),))
            result = cursor.fetchone()

            if result:
                # Update existing market
                market_id = result['id']
                cursor.execute("""
                    UPDATE markets 
                    SET slug = ?, question_id = ?, yes_token_id = ?, no_token_id = ?, status = ?
                    WHERE id = ?
                """, (
                    market_data.get('slug'),
                    market_data.get('question_id'),
                    market_data.get('yes_token_id'),
                    market_data.get('no_token_id'),
                    market_data.get('status'),
                    market_id
                ))
            else:
                # Insert new market
                cursor.execute("""
                    INSERT INTO markets (slug, condition_id, question_id, yes_token_id, no_token_id, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    market_data.get('slug'),
                    market_data.get('condition_id'),
                    market_data.get('question_id'),
                    market_data.get('yes_token_id'),
                    market_data.get('no_token_id'),
                    market_data.get('status')
                ))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def insert_trades(self, trades_list: List[Dict[str, Any]]):
        """
        Bulk inserts trades. Ignores duplicates based on (tx_hash, log_index).
        """
        if not trades_list:
            return

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Using INSERT OR IGNORE to handle unique constraint violations (idempotency)
            cursor.executemany("""
                INSERT OR IGNORE INTO trades (
                    tx_hash, log_index, market_id, maker, taker, side, outcome, price, size, timestamp
                ) VALUES (
                    :tx_hash, :log_index, :market_id, :maker, :taker, :side, :outcome, :price, :size, :timestamp
                )
            """, trades_list)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def update_sync_state(self, block_number: int):
        """Updates the last synced block number."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO sync_state (key, value) VALUES ('last_block', ?)
            """, (block_number,))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_sync_state(self) -> int:
        """Retrieves the last synced block number."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT value FROM sync_state WHERE key = 'last_block'")
            result = cursor.fetchone()
            if result:
                return result['value']
            return 0
        finally:
            conn.close()

    def fetch_market_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Fetches a market by its slug."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM markets WHERE slug = ?", (slug,))
            result = cursor.fetchone()
            if result:
                return dict(result)
            return None
        finally:
            conn.close()

    def fetch_market_by_token_id(self, token_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches market details by either yes_token_id or no_token_id.
        This is crucial for indexing trades where we only have the token ID.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM markets 
                WHERE yes_token_id = ? OR no_token_id = ?
            """, (token_id, token_id))
            result = cursor.fetchone()
            if result:
                return dict(result)
            return None
        finally:
            conn.close()

    def fetch_trades_for_market(self, market_id: int, limit: int = 100, cursor_val: int = 0) -> List[Dict[str, Any]]:
        """
        Fetches trades for a specific market with pagination.
        Using log_index or id as cursor might be better, but requirement says 'cursor'.
        Since we have unique (tx_hash, log_index), we can use a simple offset or id-based cursor.
        Using simple offset for now as per requirement 'limit and cursor/pagination'.
        Interpreting 'cursor' as offset here for simplicity unless specified otherwise, 
        or we can use id > cursor. Let's use offset for strict compliance with 'offset' example in stage2.md,
        but stage2.md also mentions 'cursor'. Standard cursor usually implies ID.
        Let's support cursor as an offset for now to match 'offset=0' example in stage2 doc.
        Wait, stage2 doc says: GET /markets/{slug}/trades?limit=100&offset=0 in one place, 
        and limit & cursor in another. I will support 'cursor' param but treat it as offset 
        if it looks like an int, matching typical simple pagination.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Assuming cursor is offset
            offset = cursor_val
            
            # Use query with limit/offset
            cursor.execute("""
                SELECT * FROM trades 
                WHERE market_id = ? 
                ORDER BY timestamp DESC, log_index DESC
                LIMIT ? OFFSET ?
            """, (market_id, limit, offset))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
