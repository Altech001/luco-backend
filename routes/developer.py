from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import secrets
import string
from typing import List
from datetime import datetime
import pytz

from database.maindb import get_db
from models.models import APIKeys, Users
from routes.authclerk import get_current_user
from pydantic import BaseModel


developer_api = APIRouter(
    prefix="/api/v1/api_key",
    tags=["Developer Key"]
)

EAT_TZ = pytz.timezone('Africa/Nairobi')

# ============= Helper Functions =============

async def get_current_user_id(request: Request, db: Session = Depends(get_db)) -> str:
    """Get user_id from existing auth"""
    # session = await get_current_user(request, db) = session.userid
    session_userid = "user_2xQ4wGyrwRavEZmeadP4vd5Sx8z"
    
    db_user = db.query(Users).filter(Users.clerk_user_id == session_userid).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in database"
        )
    
    return db_user.id


def get_user(db: Session, user_id: str) -> Users:
    """Get user object"""
    user = db.query(Users).filter(Users.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user



# ============= Schemas =============

class APIKeyResponse(BaseModel):
    id: int
    key: str
    is_active: bool
    created_at: str
    last_used: str | None

    class Config:
        from_attributes = True

class APIKeyGenerateResponse(BaseModel):
    api_key: str
    message: str

class APIKeyListResponse(BaseModel):
    id: int
    key: str
    full_key: str
    is_active: bool

class APIKeyActionResponse(BaseModel):
    message: str

# ============= Utility Functions =============

def generate_api_key(length: int = 32) -> str:
    """Generate a secure random API key"""
    alphabet = string.ascii_letters + string.digits
    random_key = ''.join(secrets.choice(alphabet) for _ in range(length))
    return f"Luco_{random_key}"

# ============= Endpoints =============

@developer_api.post("/generate", response_model=APIKeyGenerateResponse, status_code=status.HTTP_201_CREATED)

async def generate_user_api_key(user_id=Depends(get_current_user_id), db: Session = Depends(get_db)):
    """
    Generate a new API key for a user
    """
    user = get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    api_key = generate_api_key()
    
    existing_key = db.query(APIKeys).filter(APIKeys.key == api_key).first()
    if existing_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API key generation collision occurred")

    new_api_key = APIKeys(
        user_id=user.id,
        key=api_key,
        is_active=True,
        created_at=datetime.now(EAT_TZ)
    )
    
    db.add(new_api_key)
    db.commit()
    db.refresh(new_api_key)
    
    return {
        "api_key": new_api_key.key,
        "message": "API key generated successfully",
    }

@developer_api.get("/list", response_model=List[APIKeyListResponse])

async def list_api_keys(user_id=Depends(get_current_user_id), db: Session = Depends(get_db)):
    """
    List all API keys for a user
    """
    user = get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    api_keys = db.query(APIKeys).filter(APIKeys.user_id == user.id).all()
    
    return [{
        "id": key.id,
        "key": key.key[-8:],
        "full_key": key.key,
        "is_active": key.is_active,
    } for key in api_keys]

@developer_api.put("/deactivate/{key_id}", response_model=APIKeyActionResponse)
async def deactivate_api_key(key_id: int, user_session=Depends(get_current_user_id), db: Session = Depends(get_db)):
    """
    Deactivate an existing API key
    """
    api_key = db.query(APIKeys).filter(
        APIKeys.id == key_id,
        APIKeys.user_id == db.query(Users.id).filter(Users.clerk_user_id == user_session.user_id).scalar_subquery()
    ).first()
    
    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found or not owned by user")
    
    if not api_key.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API key already deactivated")
    
    api_key.is_active = False
    db.commit()
    
    return {"message": "API key deactivated successfully"}

@developer_api.delete("/delete/{key_id}", response_model=APIKeyActionResponse)

async def delete_api_key(key_id: int, user_id=Depends(get_current_user_id), db: Session = Depends(get_db)):
    """
    Delete an existing API key
    """
    user = get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    api_key = db.query(APIKeys).filter(
        APIKeys.id == key_id,
        APIKeys.user_id == user.id
    ).first()
    
    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found or not owned by user")
    
    db.delete(api_key)
    db.commit()
    
    return {"message": "API key deleted successfully"}

