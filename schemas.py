"""
House Rental Schemas (MongoDB via Pydantic)
Each model = one collection (lowercased name)
- User -> user
- Property -> property
- ContactMessage -> contactmessage
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal
from datetime import datetime

Role = Literal["customer", "landlord"]
Furnishing = Literal["unfurnished", "semi", "furnished"]

class User(BaseModel):
    username: str = Field(..., min_length=3, max_length=30)
    email: EmailStr
    role: Role = "customer"
    hashed_password: str

class Property(BaseModel):
    property_id: str = Field(..., min_length=1, max_length=20)
    title: str = Field(..., max_length=200)
    city: str = Field(..., max_length=100)
    locality: str = Field(..., max_length=150)
    rent_price: float = Field(..., ge=0)
    area_sqft: int = Field(..., ge=0)
    furnishing: Furnishing
    contact_details: str = Field(..., max_length=255)
    image_url: Optional[str] = None
    owner_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ContactMessage(BaseModel):
    property_id: str
    sender_id: str
    sender_name: str
    sender_email: EmailStr
    message: str = Field(..., min_length=1, max_length=2000)
    created_at: Optional[datetime] = None
