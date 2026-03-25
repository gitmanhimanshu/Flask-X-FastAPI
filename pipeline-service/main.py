from fastapi import FastAPI, HTTPException, Query, Depends, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from services.ingestion import ingest_customers_from_mock, IngestionError
from database import get_db, init_db
from models.customer import Customer
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from contextlib import asynccontextmanager
import logging
import math
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting FastAPI Pipeline Service")
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down FastAPI Pipeline Service")

app = FastAPI(
    title="Customer Pipeline Service",
    description="Data ingestion pipeline for customer data",
    version="1.0.0",
    lifespan=lifespan
)

# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """Handle validation errors"""
    logger.warning(f"Validation error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "message": "Invalid request parameters",
            "details": exc.errors()
        }
    )

@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request, exc):
    """Handle database errors"""
    logger.error(f"Database error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Database error",
            "message": "An error occurred while accessing the database"
        }
    )

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "Customer Pipeline Service",
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint with database connectivity check"""
    try:
        # Test database connection
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        customer_count = db.query(Customer).count()
        
        return {
            "status": "healthy",
            "service": "pipeline-service",
            "database": "connected",
            "customers_in_db": customer_count
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "service": "pipeline-service",
                "database": "disconnected",
                "error": str(e)
            }
        )

@app.post("/api/ingest")
async def ingest_data():
    """
    Ingest customer data from Flask mock server into PostgreSQL
    
    Returns:
        - status: success or error
        - records_processed: number of records ingested
        - message: additional information
    """
    try:
        logger.info("Starting data ingestion from mock server")
        records_processed = await ingest_customers_from_mock()
        
        logger.info(f"Successfully ingested {records_processed} records")
        return {
            "status": "success",
            "records_processed": records_processed,
            "message": f"Successfully ingested {records_processed} customer records"
        }
    
    except IngestionError as e:
        logger.error(f"Ingestion error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Ingestion failed",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error during ingestion: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal server error",
                "message": "An unexpected error occurred during ingestion"
            }
        )

@app.get("/api/customers")
def get_customers(
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    limit: int = Query(10, ge=1, le=100, description="Number of records per page"),
    db: Session = Depends(get_db)
):
    """
    Get paginated list of customers from database
    
    Parameters:
        - page: Page number (minimum 1)
        - limit: Records per page (1-100)
    
    Returns:
        - data: List of customer records
        - total: Total number of customers
        - page: Current page number
        - limit: Records per page
        - total_pages: Total number of pages
    """
    try:
        offset = (page - 1) * limit
        
        # Get total count
        total = db.query(Customer).count()
        
        # Check if page is out of range
        if offset >= total and total > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Page out of range",
                    "message": f"Requested page {page} exceeds available data"
                }
            )
        
        # Fetch customers
        customers = db.query(Customer).offset(offset).limit(limit).all()
        
        logger.info(f"Retrieved {len(customers)} customers (page {page})")
        
        return {
            "data": [
                {
                    "customer_id": c.customer_id,
                    "first_name": c.first_name,
                    "last_name": c.last_name,
                    "email": c.email,
                    "phone": c.phone,
                    "address": c.address,
                    "date_of_birth": c.date_of_birth.isoformat() if c.date_of_birth else None,
                    "account_balance": float(c.account_balance) if c.account_balance else 0.0,
                    "created_at": c.created_at.isoformat() if c.created_at else None
                }
                for c in customers
            ],
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": math.ceil(total / limit) if total > 0 else 0
        }
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error while fetching customers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Database error",
                "message": "Failed to retrieve customers from database"
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal server error",
                "message": "An unexpected error occurred"
            }
        )

@app.get("/api/customers/{customer_id}")
def get_customer(customer_id: str, db: Session = Depends(get_db)):
    """
    Get single customer by ID
    
    Parameters:
        - customer_id: Unique customer identifier
    
    Returns:
        - data: Customer record
    
    Raises:
        - 404: Customer not found
    """
    try:
        # Validate customer_id
        if not customer_id or not customer_id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Invalid customer ID",
                    "message": "Customer ID cannot be empty"
                }
            )
        
        customer = db.query(Customer).filter(
            Customer.customer_id == customer_id
        ).first()
        
        if not customer:
            logger.warning(f"Customer not found: {customer_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "Customer not found",
                    "message": f"No customer found with ID: {customer_id}"
                }
            )
        
        logger.info(f"Retrieved customer: {customer_id}")
        
        return {
            "data": {
                "customer_id": customer.customer_id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "email": customer.email,
                "phone": customer.phone,
                "address": customer.address,
                "date_of_birth": customer.date_of_birth.isoformat() if customer.date_of_birth else None,
                "account_balance": float(customer.account_balance) if customer.account_balance else 0.0,
                "created_at": customer.created_at.isoformat() if customer.created_at else None
            }
        }
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error while fetching customer {customer_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Database error",
                "message": "Failed to retrieve customer from database"
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal server error",
                "message": "An unexpected error occurred"
            }
        )
