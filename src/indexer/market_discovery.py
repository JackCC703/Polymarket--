import requests
import logging
from typing import List, Dict, Optional, Tuple
from ..db.store import Store

logger = logging.getLogger(__name__)

GAMMA_API_URL = "https://gamma-api.polymarket.com/events"

def fetch_markets_by_slug(slug: str) -> List[Dict]:
    """
    Fetches market data from Gamma API for a given event slug.
    """
    try:
        url = f"{GAMMA_API_URL}?slug={slug}"
        logger.info(f"Fetching markets from {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            logger.warning(f"No event found for slug: {slug}")
            return []
            
        # Gamma API returns a list of events (usually one if searching by specific slug)
        # We take the first one matching the slug roughly, or just all markets from all returned events
        all_markets = []
        for event in data:
            markets = event.get('markets', [])
            all_markets.extend(markets)
            
        return all_markets
    except requests.RequestException as e:
        logger.error(f"Error fetching markets for slug {slug}: {e}")
        return []

def process_market_data(market: Dict) -> Optional[Dict]:
    """
    Parses and processes a single market entry from the API.
    Returns a dictionary suitable for storage, or None if invalid.
    """
    try:
        # Extract basic fields
        slug = market.get('slug')
        condition_id = market.get('conditionId')
        question_id = market.get('questionID') # Note: API might use 'questionID' or 'questionId', check both
        if not question_id:
             question_id = market.get('questionId')
             
        status = 'ACTIVE' if market.get('active') else 'CLOSED' 
        if market.get('closed'):
            status = 'CLOSED'
        if market.get('resolved'):
            status = 'RESOLVED'

        # Lowercase IDs
        if condition_id:
            condition_id = condition_id.lower()
        if question_id:
            question_id = question_id.lower()

        # Handle Tokens and Outcomes
        clob_token_ids = market.get('clobTokenIds', [])
        if isinstance(clob_token_ids, str):
            try:
                import json
                clob_token_ids = json.loads(clob_token_ids)
            except Exception:
                logger.warning(f"Failed to parse clobTokenIds string: {clob_token_ids}")
                return None
        
        # Convert decimal token IDs to hex strings
        try:
            clob_token_ids = [hex(int(tid)).lower() for tid in clob_token_ids]
        except Exception as e:
            logger.warning(f"Failed to convert token IDs to hex: {e}")
            return None
                
        outcomes = market.get('outcomes', [])
        if isinstance(outcomes, str):
            try:
                import json
                outcomes = json.loads(outcomes)
            except Exception:
                 pass
        
        if not clob_token_ids or not outcomes or len(clob_token_ids) != len(outcomes):
            logger.warning(f"Market {slug} has mismatched tokens/outcomes. Tokens: {len(clob_token_ids)}, Outcomes: {len(outcomes)}")
            return None

        yes_token_id = None
        no_token_id = None

        # Dynamic mapping based on outcomes
        # Usually outcomes are ["No", "Yes"]
        for idx, outcome in enumerate(outcomes):
            token_id = clob_token_ids[idx]
            if outcome.upper() == 'YES':
                yes_token_id = token_id
            elif outcome.upper() == 'NO':
                no_token_id = token_id

        # Fallback/Validation: For binary markets, we expect both YES and NO
        if not yes_token_id or not no_token_id:
             logger.warning(f"Market {slug} missing YES/NO tokens. Found: Yes={yes_token_id}, No={no_token_id}")
             # If strictly binary, maybe skip? For now, we proceed if we have at least one or logs warning.
             # But critical for our indexer is to have both for binary.
             pass

        return {
            'slug': slug,
            'condition_id': condition_id,
            'question_id': question_id,
            'yes_token_id': yes_token_id,
            'no_token_id': no_token_id,
            'status': status
        }

    except Exception as e:
        logger.error(f"Error processing market data: {e}", exc_info=True)
        return None

def validate_market_tokens(market_data: Dict) -> bool:
    """
    Placeholder for validating market tokens against chain logic.
    """
    # TODO: Implement chain validation (Stage 1 logic)
    return True

def discover_and_store_markets(slug: str, store: Store):
    """
    Main function to discover markets and store them in DB.
    """
    markets = fetch_markets_by_slug(slug)
    count = 0
    for market_raw in markets:
        market_data = process_market_data(market_raw)
        if market_data and validate_market_tokens(market_data):
            store.upsert_market(market_data)
            count += 1
            logger.info(f"Stored market: {market_data['slug']}")
    
    logger.info(f"Finished discovery for {slug}. stored {count} markets.")
    return count
