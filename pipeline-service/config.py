import os
from typing import Optional

class Settings:
    """Application configuration settings"""
    
    # Application
    APP_NAME: str = "Customer Pipeline Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:password@postgres:5432/customer_db"
    )
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    
    # Mock Server
    MOCK_SERVER_URL: str = os.getenv("MOCK_SERVER_URL", "http://mock-server:5000")
    MOCK_SERVER_TIMEOUT: int = int(os.getenv("MOCK_SERVER_TIMEOUT", "30"))
    
    # Pagination
    DEFAULT_PAGE_SIZE: int = int(os.getenv("DEFAULT_PAGE_SIZE", "10"))
    MAX_PAGE_SIZE: int = int(os.getenv("MAX_PAGE_SIZE", "100"))
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Ingestion
    INGESTION_BATCH_SIZE: int = int(os.getenv("INGESTION_BATCH_SIZE", "10"))
    INGESTION_MAX_RETRIES: int = int(os.getenv("INGESTION_MAX_RETRIES", "3"))

settings = Settings()
