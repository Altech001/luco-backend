from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional
from datetime import datetime

from database.maindb import get_db
from models.models import Users, Transactions, Messages, DeliveryReports, Contact, ContactGroup
from schemas.schema import (
    TopupRequest, TransactionResponse, UserResponse,
    SMSRequest, SMSResponse, BulkSMSRequest, BulkSMSResponse,
    MessageFilter
)
from routes.authclerk import get_current_user
from functions.sms import LucoSMS

sendsms = APIRouter(
    prefix="/api/v1/account",
    tags=["Client Account"]
)


# ============= Helper Functions =============

async def get_current_user_id(request: Request, db: Session = Depends(get_db)) -> str:
    """Get user_id from existing auth"""
    session = await get_current_user(request, db) = session.userid
    # session_userid = "user_2xQ4wGyrwRavEZmeadP4vd5Sx8z"
    
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


def process_sms_sending(message_ids: List[int], db: Session):
    """Background task to send SMS via Africa's Talking"""
    try:
        sms_service = LucoSMS()
        
        messages = db.query(Messages).filter(Messages.id.in_(message_ids)).all()
        
        for message in messages:
            try:
                # Send via Africa's Talking
                response = sms_service.send_message(
                    message=message.message,
                    recipients=[message.recipient],
                    sender_id=message.sender_id
                )
                
                # Update message status based on response
                if response and response.get('SMSMessageData', {}).get('Recipients'):
                    recipient_data = response['SMSMessageData']['Recipients'][0]
                    message.status = recipient_data.get('status', 'sent')
                else:
                    message.status = "sent"
                    
            except Exception as e:
                message.status = "failed"
                print(f"Failed to send message {message.id}: {str(e)}")
        
        db.commit()
        
    except Exception as e:
        print(f"Background SMS processing error: {str(e)}")
        db.rollback()


# ============= WALLET ENDPOINTS =============

@sendsms.get("/wallet", response_model=UserResponse)
def get_wallet_balance(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get current wallet balance"""
    user = get_user(db, user_id)
    return user


@sendsms.post("/wallet/topup", response_model=TransactionResponse)
def topup_wallet(
    topup_data: TopupRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Add funds to wallet"""
    user = get_user(db, user_id)
    
    # Update wallet balance
    user.wallet_balance += topup_data.amount
    
    # Create transaction record
    transaction = Transactions(
        user_id=user_id,
        amount=topup_data.amount,
        transaction_type="topup"
    )
    
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    
    return transaction


@sendsms.get("/wallet/transactions", response_model=List[TransactionResponse])
def get_transactions(
    skip: int = 0,
    limit: int = 100,
    transaction_type: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get transaction history"""
    query = db.query(Transactions).filter(Transactions.user_id == user_id)
    
    if transaction_type:
        query = query.filter(Transactions.transaction_type == transaction_type)
    
    transactions = query.order_by(Transactions.created_at.desc()).offset(skip).limit(limit).all()
    return transactions


# ============= SEND SMS ENDPOINTS =============

@sendsms.post("/sms/send", response_model=BulkSMSResponse)
def send_sms(
    sms_data: SMSRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Send SMS to multiple recipients"""
    user = get_user(db, user_id)
    
    # Calculate total cost
    total_cost = len(sms_data.recipient) * 32.0
    
    # Check sufficient balance
    if user.wallet_balance < total_cost:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Required: {total_cost}, Available: {user.wallet_balance}"
        )
    
    # Deduct from wallet
    user.wallet_balance -= total_cost
    
    # Create transaction record
    transaction = Transactions(
        user_id=user_id,
        amount=-total_cost,
        transaction_type="sms_send"
    )
    db.add(transaction)
    
    # Create message records
    messages = []
    message_ids = []
    for recipient in sms_data.recipient:
        message = Messages(
            user_id=user_id,
            recipient=recipient,
            message=sms_data.message,
            sender_id=sms_data.sender_id,
            status="pending",
            cost=32.0
        )
        db.add(message)
        messages.append(message)
    
    db.commit()
    
    # Refresh all messages to get IDs
    for msg in messages:
        db.refresh(msg)
        message_ids.append(msg.id)
    
    # Send SMS in background
    background_tasks.add_task(process_sms_sending, message_ids, db)
    
    return BulkSMSResponse(
        total_sent=len(messages),
        total_cost=total_cost,
        messages=[SMSResponse.model_validate(msg) for msg in messages]
    )


@sendsms.post("/sms/send-bulk", response_model=BulkSMSResponse)
def send_bulk_sms(
    bulk_data: BulkSMSRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Send SMS to contact groups"""
    user = get_user(db, user_id)
    
    # Get all unique contacts from groups
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
    
    # Calculate total cost
    total_cost = len(contacts) * 32.0
    
    # Check sufficient balance
    if user.wallet_balance < total_cost:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Required: {total_cost}, Available: {user.wallet_balance}"
        )
    
    # Deduct from wallet
    user.wallet_balance -= total_cost
    
    # Create transaction record
    transaction = Transactions(
        user_id=user_id,
        amount=-total_cost,
        transaction_type="sms_send"
    )
    db.add(transaction)
    
    # Create message records
    messages = []
    message_ids = []
    for contact in contacts:
        message = Messages(
            user_id=user_id,
            recipient=contact.phone_number,
            message=bulk_data.message,
            sender_id=bulk_data.sender_id,
            status="pending",
            cost=32.0
        )
        db.add(message)
        messages.append(message)
    
    db.commit()
    
    # Refresh all messages
    for msg in messages:
        db.refresh(msg)
        message_ids.append(msg.id)
    
    # Send SMS in background
    background_tasks.add_task(process_sms_sending, message_ids, db)
    
    return BulkSMSResponse(
        total_sent=len(messages),
        total_cost=total_cost,
        messages=[SMSResponse.model_validate(msg) for msg in messages]
    )


# ============= REPORT ENDPOINTS =============

@sendsms.get("/reports/messages", response_model=List[SMSResponse])
def get_message_reports(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    recipient: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get message history with filters"""
    query = db.query(Messages).filter(Messages.user_id == user_id)
    
    if status:
        query = query.filter(Messages.status == status)
    if start_date:
        query = query.filter(Messages.created_at >= start_date)
    if end_date:
        query = query.filter(Messages.created_at <= end_date)
    if recipient:
        query = query.filter(Messages.recipient.like(f"%{recipient}%"))
    
    messages = query.order_by(Messages.created_at.desc()).offset(skip).limit(limit).all()
    return messages


@sendsms.get("/reports/summary")
def get_account_summary(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get account summary statistics"""
    user = get_user(db, user_id)
    
    # Message statistics
    total_messages = db.query(func.count(Messages.id)).filter(Messages.user_id == user_id).scalar()
    
    pending = db.query(func.count(Messages.id)).filter(
        Messages.user_id == user_id,
        Messages.status == "pending"
    ).scalar()
    
    delivered = db.query(func.count(Messages.id)).filter(
        Messages.user_id == user_id,
        Messages.status == "delivered"
    ).scalar()
    
    failed = db.query(func.count(Messages.id)).filter(
        Messages.user_id == user_id,
        Messages.status == "failed"
    ).scalar()
    
    # Transaction statistics
    total_topups = db.query(func.sum(Transactions.amount)).filter(
        Transactions.user_id == user_id,
        Transactions.transaction_type == "topup"
    ).scalar() or 0.0
    
    total_spent = db.query(func.sum(func.abs(Transactions.amount))).filter(
        Transactions.user_id == user_id,
        Transactions.transaction_type == "sms_send"
    ).scalar() or 0.0
    
    return {
        "wallet": {
            "current_balance": user.wallet_balance,
            "total_topups": total_topups,
            "total_spent": total_spent
        },
        "messages": {
            "total_sent": total_messages,
            "pending": pending,
            "delivered": delivered,
            "failed": failed
        },
        "account": {
            "username": user.username,
            "email": user.email,
            "created_at": user.created_at
        }
    }


@sendsms.get("/reports/messages/{message_id}", response_model=SMSResponse)
def get_message_details(
    message_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get specific message details"""
    message = db.query(Messages).filter(
        Messages.id == message_id,
        Messages.user_id == user_id
    ).first()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found or access denied"
        )
    
    return message


@sendsms.get("/reports/spending")
def get_spending_report(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get spending report for a date range"""
    query = db.query(Messages).filter(Messages.user_id == user_id)
    
    if start_date:
        query = query.filter(Messages.created_at >= start_date)
    if end_date:
        query = query.filter(Messages.created_at <= end_date)
    
    messages = query.all()
    
    total_spent = sum(msg.cost for msg in messages)
    total_messages = len(messages)
    
    # Group by status
    status_breakdown = {}
    for msg in messages:
        status_breakdown[msg.status] = status_breakdown.get(msg.status, 0) + 1
    
    return {
        "period": {
            "start_date": start_date,
            "end_date": end_date
        },
        "summary": {
            "total_messages": total_messages,
            "total_spent": total_spent,
            "average_cost_per_message": total_spent / total_messages if total_messages > 0 else 0
        },
        "status_breakdown": status_breakdown
    }