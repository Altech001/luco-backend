from fastapi import APIRouter, HTTPException, Depends, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime
import pytz

from database.maindb import get_db
from models.models import Users, Messages, DeliveryReports, Transactions, APIKeys
from routes.authclerk import get_current_user

from functions.sms import LucoSMS

devsms = APIRouter(
    prefix="/api/v1/client",
    tags=["Dev API SMS"]
)

SMS_COST = 32.0  # Aligned with models.py
EAT_TZ = pytz.timezone('Africa/Nairobi')

# ============= Helper Functions =============

async def get_current_user_id(request: Request, db: Session = Depends(get_db)) -> str:
    """Get user_id from existing auth"""
    # session = await get_current_user(request, db)
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

class SMSMessageCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=160)
    recipients: List[str] = Field(..., min_items=1)

class SMSMessageResponse(BaseModel):
    id: str
    user_id: str
    recipient: str
    message: str
    status: str
    cost: float
    created_at: str
    delivery_status: str

    class Config:
        from_attributes = True

class SMSBulkResponse(BaseModel):
    status: str
    message: str
    recipients: List[str]
    recipients_count: int
    total_cost: float
    messages: List[SMSMessageResponse]

# Custom dependency for API key authentication
async def get_api_user(request: Request, db: Session = Depends(get_db)):
    """Validate API key and return associated user"""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key missing")

    key = db.query(APIKeys).filter(
        APIKeys.key == api_key,
        APIKeys.is_active == True
    ).first()
    
    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive API key")

    user = db.query(Users).filter(Users.id == key.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Update last_used timestamp
    key.last_used = datetime.now(EAT_TZ)
    db.commit()

    return user

# ============= Endpoint =============

@devsms.post("/send-sms", response_model=SMSBulkResponse)
async def client_send_sms(
    sms: SMSMessageCreate,
    current_user: Users = Depends(get_api_user),
    db: Session = Depends(get_db)
):
    """Send SMS to multiple recipients via API"""
    total_cost = SMS_COST * len(sms.recipients)
    if current_user.wallet_balance < total_cost:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Required: {total_cost}, Available: {current_user.wallet_balance}"
        )

    try:
        sms_client = LucoSMS()
        response = sms_client.send_message(sms.message, sms.recipients)
        
        if not response or 'SMSMessageData' not in response:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SMS sending failed - No response data"
            )
        
        recipients = response.get('SMSMessageData', {}).get('Recipients', [])
        if not recipients or not any(recipient.get('status') == 'Success' for recipient in recipients):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SMS sending failed - Delivery error"
            )

        # Update wallet balance
        current_user.wallet_balance -= total_cost
        
        # Record SMS messages
        sms_messages = []
        for recipient_number in sms.recipients:
            sms_message = Messages(
                user_id=current_user.id,
                recipient=recipient_number,
                message=sms.message,
                status="sent",
                cost=SMS_COST
            )
            sms_messages.append(sms_message)
            db.add(sms_message)

        # Record transaction
        transaction = Transactions(
            user_id=current_user.id,
            amount=-total_cost,
            transaction_type="sms_deduction"
        )
        db.add(transaction)
        db.commit()

        # Create delivery reports
        response_messages = []
        for sms_message in sms_messages:
            sms_delivery_report = DeliveryReports(
                sms_id=sms_message.id,
                status="delivered",
                updated_at=datetime.now(EAT_TZ)
            )
            db.add(sms_delivery_report)
            response_messages.append(SMSMessageResponse(
                id=str(sms_message.id),
                user_id=current_user.id,
                recipient=sms_message.recipient,
                message=sms_message.message,
                status=sms_message.status,
                cost=sms_message.cost,
                created_at=sms_message.created_at.isoformat(),
                delivery_status="delivered"
            ))
        
        db.commit()
        
        return {
            "status": "success",
            "message": "SMS sent successfully",
            "recipients": sms.recipients,
            "recipients_count": len(sms.recipients),
            "total_cost": total_cost,
            "messages": response_messages
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SMS sending failed: {str(e)}"
        )