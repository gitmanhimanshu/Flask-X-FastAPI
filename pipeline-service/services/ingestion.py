import httpx
import os
from datetime import datetime
from database import SessionLocal
from models.customer import Customer
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
import logging
from typing import List, Dict, Any

# Configure logging
logger = logging.getLogger(__name__)

MOCK_SERVER_URL = os.getenv("MOCK_SERVER_URL", "http://mock-server:5000")
MAX_RETRIES = 3
TIMEOUT = 30.0

class IngestionError(Exception):
    """Custom exception for ingestion errors"""
    pass

async def fetch_all_customers_from_mock() -> List[Dict[str, Any]]:
    """
    Fetch all customers from Flask mock server with pagination handling
    
    Returns:
        List of customer dictionaries
    
    Raises:
        IngestionError: If fetching fails after retries
    """
    all_customers = []
    page = 1
    limit = 10
    retries = 0
    
    logger.info(f"Starting to fetch customers from {MOCK_SERVER_URL}")
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        while True:
            try:
                response = await client.get(
                    f"{MOCK_SERVER_URL}/api/customers",
                    params={"page": page, "limit": limit}
                )
                response.raise_for_status()
                
                data = response.json()
                customers = data.get("data", [])
                
                if not customers:
                    logger.info(f"No more customers to fetch. Total fetched: {len(all_customers)}")
                    break
                
                all_customers.extend(customers)
                logger.info(f"Fetched page {page}: {len(customers)} customers")
                
                # Check if we've fetched all records
                total = data.get("total", 0)
                if len(all_customers) >= total:
                    logger.info(f"Fetched all {len(all_customers)} customers")
                    break
                
                page += 1
                retries = 0  # Reset retries on successful fetch
            
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error on page {page}: {e.response.status_code}")
                retries += 1
                if retries >= MAX_RETRIES:
                    raise IngestionError(f"Failed to fetch data after {MAX_RETRIES} retries: {str(e)}")
            
            except httpx.RequestError as e:
                logger.error(f"Request error on page {page}: {e}")
                retries += 1
                if retries >= MAX_RETRIES:
                    raise IngestionError(f"Failed to connect to mock server: {str(e)}")
            
            except Exception as e:
                logger.error(f"Unexpected error on page {page}: {e}")
                raise IngestionError(f"Unexpected error while fetching data: {str(e)}")
    
    if not all_customers:
        logger.warning("No customers fetched from mock server")
    
    return all_customers

def parse_date(date_str: str) -> datetime.date:
    """
    Parse date string to date object
    
    Args:
        date_str: Date string in ISO format
    
    Returns:
        datetime.date object or None
    """
    if not date_str:
        return None
    try:
        # Handle various date formats
        if 'T' in date_str:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
        else:
            return datetime.fromisoformat(date_str).date()
    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse date '{date_str}': {e}")
        return None

def parse_timestamp(timestamp_str: str) -> datetime:
    """
    Parse timestamp string to datetime object
    
    Args:
        timestamp_str: Timestamp string in ISO format
    
    Returns:
        datetime object or None
    """
    if not timestamp_str:
        return None
    try:
        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
        return None

def validate_customer_data(customer_data: Dict[str, Any]) -> bool:
    """
    Validate customer data before insertion
    
    Args:
        customer_data: Customer dictionary
    
    Returns:
        True if valid, False otherwise
    """
    required_fields = ['customer_id', 'first_name', 'last_name', 'email']
    
    for field in required_fields:
        if not customer_data.get(field):
            logger.warning(f"Missing required field '{field}' in customer data")
            return False
    
    return True

async def ingest_customers_from_mock() -> int:
    """
    Ingest customers from mock server into PostgreSQL with upsert logic
    
    Returns:
        Number of records processed
    
    Raises:
        IngestionError: If ingestion fails
    """
    try:
        # Fetch all customers from mock server
        customers_data = await fetch_all_customers_from_mock()
        
        if not customers_data:
            logger.warning("No customers to ingest")
            return 0
        
        logger.info(f"Starting ingestion of {len(customers_data)} customers")
        
        db = SessionLocal()
        try:
            records_processed = 0
            records_skipped = 0
            
            for idx, customer_data in enumerate(customers_data, 1):
                try:
                    # Validate customer data
                    if not validate_customer_data(customer_data):
                        logger.warning(f"Skipping invalid customer at index {idx}")
                        records_skipped += 1
                        continue
                    
                    # Prepare customer data
                    customer_dict = {
                        "customer_id": customer_data.get("customer_id"),
                        "first_name": customer_data.get("first_name"),
                        "last_name": customer_data.get("last_name"),
                        "email": customer_data.get("email"),
                        "phone": customer_data.get("phone"),
                        "address": customer_data.get("address"),
                        "date_of_birth": parse_date(customer_data.get("date_of_birth")),
                        "account_balance": customer_data.get("account_balance"),
                        "created_at": parse_timestamp(customer_data.get("created_at"))
                    }
                    
                    # Upsert logic using PostgreSQL's INSERT ... ON CONFLICT
                    stmt = insert(Customer).values(**customer_dict)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['customer_id'],
                        set_={
                            "first_name": stmt.excluded.first_name,
                            "last_name": stmt.excluded.last_name,
                            "email": stmt.excluded.email,
                            "phone": stmt.excluded.phone,
                            "address": stmt.excluded.address,
                            "date_of_birth": stmt.excluded.date_of_birth,
                            "account_balance": stmt.excluded.account_balance,
                            "created_at": stmt.excluded.created_at
                        }
                    )
                    
                    db.execute(stmt)
                    records_processed += 1
                    
                    # Commit in batches for better performance
                    if records_processed % 10 == 0:
                        db.commit()
                        logger.info(f"Committed batch: {records_processed} records")
                
                except Exception as e:
                    logger.error(f"Error processing customer at index {idx}: {e}")
                    records_skipped += 1
                    continue
            
            # Final commit
            db.commit()
            
            logger.info(
                f"Ingestion complete: {records_processed} processed, "
                f"{records_skipped} skipped"
            )
            
            return records_processed
        
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Database error during ingestion: {e}")
            raise IngestionError(f"Database error: {str(e)}")
        
        except Exception as e:
            db.rollback()
            logger.error(f"Unexpected error during ingestion: {e}")
            raise IngestionError(f"Unexpected error: {str(e)}")
        
        finally:
            db.close()
    
    except IngestionError:
        raise
    except Exception as e:
        logger.error(f"Fatal error in ingestion process: {e}")
        raise IngestionError(f"Fatal error: {str(e)}")
