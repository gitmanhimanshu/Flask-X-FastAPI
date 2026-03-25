from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import os
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@postgres:5432/customer_db"
)

# Database connection configuration
MAX_RETRIES = 30
RETRY_DELAY = 2
POOL_SIZE = 5
MAX_OVERFLOW = 10
POOL_TIMEOUT = 30
POOL_RECYCLE = 3600

def create_db_engine():
    """
    Create database engine with retry logic and connection pooling
    
    Returns:
        SQLAlchemy engine
    
    Raises:
        Exception: If connection fails after max retries
    """
    retry_count = 0
    
    while retry_count < MAX_RETRIES:
        try:
            logger.info(f"Attempting database connection (attempt {retry_count + 1}/{MAX_RETRIES})")
            
            engine = create_engine(
                DATABASE_URL,
                pool_pre_ping=True,  # Verify connections before using
                pool_size=POOL_SIZE,
                max_overflow=MAX_OVERFLOW,
                pool_timeout=POOL_TIMEOUT,
                pool_recycle=POOL_RECYCLE,
                echo=False  # Set to True for SQL query logging
            )
            
            # Test connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info("Database connection successful!")
            return engine
        
        except SQLAlchemyError as e:
            retry_count += 1
            logger.warning(
                f"Database connection attempt {retry_count}/{MAX_RETRIES} failed: {e}"
            )
            
            if retry_count >= MAX_RETRIES:
                logger.error("Max retries reached. Could not connect to database.")
                raise Exception(
                    f"Could not connect to database after {MAX_RETRIES} retries: {str(e)}"
                )
            
            time.sleep(RETRY_DELAY)
        
        except Exception as e:
            logger.error(f"Unexpected error during database connection: {e}")
            raise

# Create engine
engine = create_db_engine()

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for models
Base = declarative_base()

# Connection pool event listeners for logging
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Log when a new connection is created"""
    logger.debug("New database connection established")

@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    """Log when a connection is checked out from the pool"""
    logger.debug("Connection checked out from pool")

def get_db():
    """
    Dependency function for FastAPI to get database session
    
    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def init_db():
    """
    Initialize database by creating all tables
    
    Raises:
        Exception: If table creation fails
    """
    try:
        logger.info("Initializing database tables...")
        
        # Import all models to ensure they're registered
        from models.customer import Customer
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        
        logger.info("Database tables created successfully!")
        
        # Log table information
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        logger.info(f"Available tables: {tables}")
    
    except SQLAlchemyError as e:
        logger.error(f"Failed to initialize database: {e}")
        raise Exception(f"Database initialization failed: {str(e)}")
    
    except Exception as e:
        logger.error(f"Unexpected error during database initialization: {e}")
        raise

def check_db_health():
    """
    Check database health and connectivity
    
    Returns:
        bool: True if database is healthy, False otherwise
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
