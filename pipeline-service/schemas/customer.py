from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

class CustomerBase(BaseModel):
    """Base customer schema"""
    customer_id: str = Field(..., min_length=1, max_length=50)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None
    date_of_birth: Optional[date] = None
    account_balance: Optional[Decimal] = Field(None, ge=0)
    created_at: Optional[datetime] = None

class CustomerResponse(CustomerBase):
    """Customer response schema"""
    
    class Config:
        from_attributes = True
        json_encoders = {
            date: lambda v: v.isoformat() if v else None,
            datetime: lambda v: v.isoformat() if v else None,
            Decimal: lambda v: float(v) if v else 0.0
        }

class PaginatedResponse(BaseModel):
    """Paginated response schema"""
    data: list
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    limit: int = Field(..., ge=1)
    total_pages: int = Field(..., ge=0)

class IngestionResponse(BaseModel):
    """Ingestion response schema"""
    status: str
    records_processed: int = Field(..., ge=0)
    message: str

class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str
    message: str
    details: Optional[dict] = None
