import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from passlib.context import CryptContext
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Property as PropertySchema, User as UserSchema, ContactMessage as ContactSchema

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static hosting for uploaded images
UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Utility

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# Models for auth
class SignupRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str  # customer | landlord

class LoginRequest(BaseModel):
    username: str
    password: str

@app.get("/")
def root():
    return {"message": "House Rental API running"}

# Auth endpoints (very simple demo auth storing hashed password in DB; no JWT for brevity)
@app.post("/api/auth/signup")
def signup(payload: SignupRequest):
    if db["user"].find_one({"username": payload.username}):
        raise HTTPException(status_code=400, detail="Username already exists")
    user_doc = {
        "username": payload.username,
        "email": payload.email,
        "role": payload.role if payload.role in ("customer", "landlord") else "customer",
        "hashed_password": hash_password(payload.password),
    }
    uid = db["user"].insert_one(user_doc).inserted_id
    return {"_id": str(uid), "username": payload.username, "role": user_doc["role"]}

@app.post("/api/auth/login")
def login(payload: LoginRequest):
    user = db["user"].find_one({"username": payload.username})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    if not pwd_context.verify(payload.password, user.get("hashed_password", "")):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    return {"_id": str(user["_id"]), "username": user["username"], "role": user.get("role", "customer")}

# Property CRUD
@app.get("/api/properties")
def list_properties(q: Optional[str] = None, city: Optional[str] = None, furnishing: Optional[str] = None,
                   min_price: Optional[float] = None, max_price: Optional[float] = None, limit: int = 100):
    query = {}
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"city": {"$regex": q, "$options": "i"}},
            {"locality": {"$regex": q, "$options": "i"}},
        ]
    if city:
        query["city"] = {"$regex": city, "$options": "i"}
    if furnishing:
        query["furnishing"] = furnishing
    if min_price is not None or max_price is not None:
        price_cond = {}
        if min_price is not None:
            price_cond["$gte"] = float(min_price)
        if max_price is not None:
            price_cond["$lte"] = float(max_price)
        query["rent_price"] = price_cond

    docs = db["property"].find(query).limit(limit)
    results = []
    for d in docs:
        d["_id"] = str(d["_id"])  # stringify
        results.append(d)
    return {"items": results}

@app.get("/api/properties/{prop_id}")
def get_property(prop_id: str):
    try:
        doc = db["property"].find_one({"_id": ObjectId(prop_id)})
    except Exception:
        doc = db["property"].find_one({"property_id": prop_id})
    if not doc:
        raise HTTPException(404, "Property not found")
    doc["_id"] = str(doc["_id"])  # stringify
    return doc

@app.post("/api/properties")
async def create_property(
    property_id: str = Form(...),
    title: str = Form(...),
    city: str = Form(...),
    locality: str = Form(...),
    rent_price: float = Form(...),
    area_sqft: int = Form(...),
    furnishing: str = Form(...),
    contact_details: str = Form(...),
    owner_id: str = Form(...),
    image: UploadFile | None = File(None)
):
    # Save image if provided
    image_url = None
    if image is not None:
        filename = f"{property_id}_{image.filename}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(await image.read())
        image_url = f"/uploads/{filename}"

    doc = {
        "property_id": property_id,
        "title": title,
        "city": city,
        "locality": locality,
        "rent_price": float(rent_price),
        "area_sqft": int(area_sqft),
        "furnishing": furnishing,
        "contact_details": contact_details,
        "image_url": image_url,
        "owner_id": owner_id,
    }

    # Uniqueness check for property_id
    if db["property"].find_one({"property_id": property_id}):
        raise HTTPException(400, "property_id must be unique")

    inserted = db["property"].insert_one(doc)
    doc["_id"] = str(inserted.inserted_id)
    return doc

@app.put("/api/properties/{prop_id}")
async def update_property(
    prop_id: str,
    title: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    locality: Optional[str] = Form(None),
    rent_price: Optional[float] = Form(None),
    area_sqft: Optional[int] = Form(None),
    furnishing: Optional[str] = Form(None),
    contact_details: Optional[str] = Form(None),
    image: UploadFile | None = File(None)
):
    try:
        query = {"_id": ObjectId(prop_id)}
    except Exception:
        query = {"property_id": prop_id}

    existing = db["property"].find_one(query)
    if not existing:
        raise HTTPException(404, "Property not found")

    updates = {}
    for key, value in {
        "title": title,
        "city": city,
        "locality": locality,
        "rent_price": float(rent_price) if rent_price is not None else None,
        "area_sqft": int(area_sqft) if area_sqft is not None else None,
        "furnishing": furnishing,
        "contact_details": contact_details,
    }.items():
        if value is not None:
            updates[key] = value

    if image is not None:
        filename = f"{existing.get('property_id', prop_id)}_{image.filename}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(await image.read())
        updates["image_url"] = f"/uploads/{filename}"

    if not updates:
        return {"message": "No changes"}

    db["property"].update_one(query, {"$set": updates})
    updated = db["property"].find_one(query)
    updated["_id"] = str(updated["_id"])  # stringify
    return updated

@app.delete("/api/properties/{prop_id}")
def delete_property(prop_id: str):
    try:
        query = {"_id": ObjectId(prop_id)}
    except Exception:
        query = {"property_id": prop_id}
    res = db["property"].delete_one(query)
    if res.deleted_count == 0:
        raise HTTPException(404, "Property not found")
    return {"deleted": True}

# Contact owner (stores message)
@app.post("/api/properties/{prop_id}/contact")
def contact_owner(prop_id: str, payload: ContactSchema):
    # verify property exists
    try:
        query = {"_id": ObjectId(prop_id)}
    except Exception:
        query = {"property_id": prop_id}
    prop = db["property"].find_one(query)
    if not prop:
        raise HTTPException(404, "Property not found")

    doc = payload.model_dump()
    db["contactmessage"].insert_one(doc)
    return {"sent": True}

