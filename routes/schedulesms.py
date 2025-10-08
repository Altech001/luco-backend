
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, field_validator
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
import pytz  # Add this import

from database.maindb import get_db, SessionLocal, DB_URI
from models.models import Users, ScheduledMessages, Messages, Transactions, Contact, ContactGroup
from routes.authclerk import get_current_user
from functions.sms import LucoSMS

schedule = APIRouter(
    prefix="/api/v1/schedule",
    tags=["Schedule Message"]
)

# Set timezone (EAT = UTC+3)
EAT_TZ = pytz.timezone('Africa/Nairobi')

# ============= APScheduler Setup =============

jobstores = {
    'default': SQLAlchemyJobStore(url=DB_URI)
}

executors = {
    'default': ThreadPoolExecutor(10)
}

scheduler = BackgroundScheduler(
    jobstores=jobstores, 
    executors=executors,
    job_defaults={
        'coalesce': True,
        'max_instances': 1
    },
    timezone=EAT_TZ  # Set scheduler timezone to EAT
)

# ============= Schemas =============

class ScheduleSMSRequest(BaseModel):
    message: str
    recipient: str
    scheduled_time: datetime
    sender_id: Optional[str] = None
    
    @field_validator('message')
    @classmethod
    def validate_message(cls, v):
        if not v or not v.strip():
            raise ValueError('Message cannot be empty')
        if len(v) > 160:
            raise ValueError('Message cannot exceed 160 characters')
        return v.strip()
    
    @field_validator('recipient')
    @classmethod
    def validate_recipient(cls, v):
        if not v.startswith('+'):
            raise ValueError('Phone number must start with +')
        if not v[1:].isdigit():
            raise ValueError('Phone number must contain only digits after +')
        if not (10 <= len(v) <= 15):
            raise ValueError('Phone number must be between 10 and 15 characters')
        return v
    
    @field_validator('scheduled_time')
    @classmethod
    def validate_time(cls, v):
        # Ensure v is timezone-aware
        if not v.tzinfo:
            v = EAT_TZ.localize(v)  # Make naive datetime aware with EAT timezone
        # Compare with current time in EAT
        if v <= datetime.now(EAT_TZ):
            raise ValueError('Scheduled time must be in the future')
        return v

class BulkScheduleSMSRequest(BaseModel):
    message: str
    group_ids: List[int]
    scheduled_time: datetime
    sender_id: Optional[str] = None
    
    @field_validator('message')
    @classmethod
    def validate_message(cls, v):
        if not v or not v.strip():
            raise ValueError('Message cannot be empty')
        if len(v) > 160:
            raise ValueError('Message cannot exceed 160 characters')
        return v.strip()
    
    @field_validator('scheduled_time')
    @classmethod
    def validate_time(cls, v):
        # Ensure v is timezone-aware
        if not v.tzinfo:
            v = EAT_TZ.localize(v)
        if v <= datetime.now(EAT_TZ):
            raise ValueError('Scheduled time must be in the future')
        return v

class ScheduledMessageResponse(BaseModel):
    id: int
    user_id: str
    recipient: str
    message: str
    sender_id: Optional[str]
    scheduled_time: datetime
    status: str
    cost: float
    attempts: int
    error_message: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class ScheduleUpdateRequest(BaseModel):
    message: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    sender_id: Optional[str] = None

    @field_validator('scheduled_time')
    @classmethod
    def validate_time(cls, v):
        if v is None:
            return v
        # Ensure v is timezone-aware
        if not v.tzinfo:
            v = EAT_TZ.localize(v)
        if v <= datetime.now(EAT_TZ):
            raise ValueError('Scheduled time must be in the future')
        return v

# ============= Helper Functions =============

async def get_current_user_id(request: Request, db: Session = Depends(get_db)) -> str:
    """Get user_id from existing auth"""
    session = await get_current_user(request, db) =session.userid
    # session_userid = "user_2xQ4wGyrwRavEZmeadP4vd5Sx8z"
    
    # Get user from database
    db_user = db.query(Users).filter(Users.clerk_user_id == session.user_id).first()
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

def verify_schedule_ownership(db: Session, schedule_id: int, user_id: str) -> ScheduledMessages:
    """Verify scheduled message belongs to user"""
    scheduled = db.query(ScheduledMessages).filter(
        ScheduledMessages.id == schedule_id,
        ScheduledMessages.user_id == user_id
    ).first()
    
    if not scheduled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scheduled message not found or access denied"
        )
    return scheduled

# ============= SCHEDULE ENDPOINTS =============

@schedule.post("/", response_model=ScheduledMessageResponse, status_code=status.HTTP_201_CREATED)
def schedule_sms(
    schedule_data: ScheduleSMSRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Schedule an SMS for future delivery"""
    user = get_user(db, user_id)
    
    cost = 32.0
    if user.wallet_balance < cost:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Required: {cost}, Available: {user.wallet_balance}"
        )
    
    user.wallet_balance -= cost
    
    transaction = Transactions(
        user_id=user_id,
        amount=-cost,
        transaction_type="sms_scheduled"
    )
    db.add(transaction)
    
    scheduled_msg = ScheduledMessages(
        user_id=user_id,
        recipient=schedule_data.recipient,
        message=schedule_data.message,
        sender_id=schedule_data.sender_id,
        scheduled_time=schedule_data.scheduled_time,
        cost=cost,
        status="pending"
    )
    
    db.add(scheduled_msg)
    db.commit()
    db.refresh(scheduled_msg)
    
    return scheduled_msg

@schedule.post("/bulk", status_code=status.HTTP_201_CREATED)
def schedule_bulk_sms(
    bulk_data: BulkScheduleSMSRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Schedule SMS to contact groups"""
    user = get_user(db, user_id)
    
    contacts = db.query(Contact).join(
        Contact.groups
    ).filter(
        ContactGroup.id.in_(bulk_data.group_ids),
        ContactGroup.user_id == user_id,
        Contact.is_active == True
    ).distinct().all()
    
    if not contacts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active contacts found in selected groups"
        )
    
    total_cost = len(contacts) * 32.0
    if user.wallet_balance < total_cost:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Required: {total_cost}, Available: {user.wallet_balance}"
        )
    
    user.wallet_balance -= total_cost
    
    transaction = Transactions(
        user_id=user_id,
        amount=-total_cost,
        transaction_type="sms_scheduled"
    )
    db.add(transaction)
    
    scheduled_msgs = []
    for contact in contacts:
        scheduled_msg = ScheduledMessages(
            user_id=user_id,
            recipient=contact.phone_number,
            message=bulk_data.message,
            sender_id=bulk_data.sender_id,
            scheduled_time=bulk_data.scheduled_time,
            cost=32.0,
            status="pending"
        )
        db.add(scheduled_msg)
        scheduled_msgs.append(scheduled_msg)
    
    db.commit()
    
    return {
        "total_scheduled": len(scheduled_msgs),
        "total_cost": total_cost,
        "scheduled_time": bulk_data.scheduled_time,
        "message": f"Successfully scheduled {len(scheduled_msgs)} messages"
    }

@schedule.get("/", response_model=List[ScheduledMessageResponse])
def get_scheduled_messages(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get all scheduled messages"""
    query = db.query(ScheduledMessages).filter(ScheduledMessages.user_id == user_id)
    
    if status:
        query = query.filter(ScheduledMessages.status == status)
    
    scheduled = query.order_by(ScheduledMessages.scheduled_time).offset(skip).limit(limit).all()
    return scheduled

@schedule.get("/{schedule_id}", response_model=ScheduledMessageResponse)
def get_scheduled_message(
    schedule_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get specific scheduled message"""
    scheduled = verify_schedule_ownership(db, schedule_id, user_id)
    return scheduled

@schedule.put("/{schedule_id}", response_model=ScheduledMessageResponse)
def update_scheduled_message(
    schedule_id: int,
    update_data: ScheduleUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Update scheduled message (only if pending)"""
    scheduled = verify_schedule_ownership(db, schedule_id, user_id)
    
    if scheduled.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only update pending messages"
        )
    
    if update_data.message:
        scheduled.message = update_data.message
    if update_data.scheduled_time:
        scheduled.scheduled_time = update_data.scheduled_time
    if update_data.sender_id is not None:
        scheduled.sender_id = update_data.sender_id
    
    db.commit()
    db.refresh(scheduled)
    return scheduled

@schedule.delete("/{schedule_id}", status_code=status.HTTP_200_OK)
def cancel_scheduled_message(
    schedule_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Cancel scheduled message and refund"""
    scheduled = verify_schedule_ownership(db, schedule_id, user_id)
    
    if scheduled.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only cancel pending messages"
        )
    
    user = get_user(db, user_id)
    user.wallet_balance += scheduled.cost
    
    transaction = Transactions(
        user_id=user_id,
        amount=scheduled.cost,
        transaction_type="sms_refund"
    )
    db.add(transaction)
    
    scheduled.status = "cancelled"
    
    db.commit()
    
    return {
        "message": "Scheduled message cancelled and refunded",
        "refunded_amount": scheduled.cost
    }

# ============= BACKGROUND PROCESSOR =============

def process_scheduled_messages(db: Session):
    """Process due scheduled messages - Run via APScheduler"""
    now = datetime.now(EAT_TZ)  # Use timezone-aware datetime
    
    due_messages = db.query(ScheduledMessages).filter(
        ScheduledMessages.status == "pending",
        ScheduledMessages.scheduled_time <= now
    ).all()
    
    if not due_messages:
        return
    
    sms_service = LucoSMS()
    
    for scheduled in due_messages:
        scheduled.status = "processing"
        scheduled.attempts += 1
        scheduled.last_attempt_at = now
        
        try:
            response = sms_service.send_message(
                message=scheduled.message,
                recipients=[scheduled.recipient],
                sender_id=scheduled.sender_id
            )
            
            message = Messages(
                user_id=scheduled.user_id,
                recipient=scheduled.recipient,
                message=scheduled.message,
                sender_id=scheduled.sender_id,
                status="sent",
                cost=scheduled.cost
            )
            db.add(message)
            db.flush()
            
            scheduled.status = "sent"
            scheduled.sent_message_id = message.id
            scheduled.processed_at = now
            
        except Exception as e:
            scheduled.status = "failed"
            scheduled.error_message = str(e)
            
            user = db.query(Users).filter(Users.id == scheduled.user_id).first()
            if user:
                user.wallet_balance += scheduled.cost
                transaction = Transactions(
                    user_id=scheduled.user_id,
                    amount=scheduled.cost,
                    transaction_type="sms_refund"
                )
                db.add(transaction)
    
    db.commit()

def check_scheduled_sms():
    """Wrapper for scheduler - manages DB session"""
    db = SessionLocal()
    try:
        process_scheduled_messages(db)
    except Exception as e:
        print(f"Scheduler error: {str(e)}")
    finally:
        db.close()

scheduler.add_job(
    check_scheduled_sms, 
    'interval', 
    minutes=1,
    id='process_scheduled_sms',
    replace_existing=True
)

def start_scheduler():
    """Start the scheduler - call this in main.py startup"""
    if not scheduler.running:
        scheduler.start()
        print("✓ APScheduler started - processing scheduled SMS every minute")

def shutdown_scheduler():
    """Shutdown scheduler - call this in main.py shutdown"""
    if scheduler.running:
        scheduler.shutdown()
        print("✓ APScheduler stopped")

@schedule.post("/process-due", status_code=status.HTTP_200_OK)
def trigger_process_scheduled(db: Session = Depends(get_db)):
    """Manually trigger processing of due messages (for testing)"""
    process_scheduled_messages(db)
    return {"message": "Processed due scheduled messages"}

@schedule.get("/scheduler-status")
def get_scheduler_status():
    """Get scheduler status and next run info"""
    jobs = scheduler.get_jobs()
    return {
        "running": scheduler.running,
        "jobs": [
            {
                "id": job.id,
                "next_run": job.next_run_time,
                "trigger": str(job.trigger)
            }
            for job in jobs
        ]
    }



