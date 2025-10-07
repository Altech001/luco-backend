from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime


# ============= User Schemas =============

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    username: str
    email: EmailStr
    wallet_balance: float
    clerk_user_id: str
    created_at: datetime


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    clerk_user_id: str


# ============= Transaction Schemas =============

class TransactionCreate(BaseModel):
    amount: float
    transaction_type: str


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: str
    amount: float
    transaction_type: str
    created_at: datetime


class TopupRequest(BaseModel):
    amount: float
    
    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be greater than 0')
        if v > 1000000:
            raise ValueError('Amount cannot exceed 1,000,000')
        return v


# ============= SMS/Message Schemas =============

class SMSRequest(BaseModel):
    message: str
    recipient: List[str]
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
    def validate_phone_numbers(cls, v):
        if not v:
            raise ValueError('At least one recipient is required')
        if len(v) > 1000:
            raise ValueError('Cannot send to more than 1000 recipients at once')
        
        for phone in v:
            if not phone.startswith('+'):
                raise ValueError(f'Phone number {phone} must start with +')
            if not phone[1:].isdigit():
                raise ValueError(f'Phone number {phone} must contain only digits after +')
            if not (10 <= len(phone) <= 15):
                raise ValueError(f'Phone number {phone} must be between 10 and 15 characters')
        return v


class BulkSMSRequest(BaseModel):
    message: str
    group_ids: List[int]
    sender_id: Optional[str] = None
    
    @field_validator('message')
    @classmethod
    def validate_message(cls, v):
        if not v or not v.strip():
            raise ValueError('Message cannot be empty')
        if len(v) > 160:
            raise ValueError('Message cannot exceed 160 characters')
        return v.strip()
    
    @field_validator('group_ids')
    @classmethod
    def validate_groups(cls, v):
        if not v:
            raise ValueError('At least one group is required')
        return v


class SMSResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: str
    recipient: str
    message: str
    status: str
    cost: float
    sender_id: Optional[str] = None
    created_at: datetime


class BulkSMSResponse(BaseModel):
    total_sent: int
    total_cost: float
    messages: List[SMSResponse]


# ============= Template Schemas =============

class TemplateCreate(BaseModel):
    name: str
    content: str
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Template name cannot be empty')
        if len(v) > 50:
            raise ValueError('Template name cannot exceed 50 characters')
        return v.strip()
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v):
        if not v or not v.strip():
            raise ValueError('Template content cannot be empty')
        if len(v) > 160:
            raise ValueError('Template content cannot exceed 160 characters')
        return v.strip()


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError('Template content cannot be empty')
            if len(v) > 160:
                raise ValueError('Template content cannot exceed 160 characters')
            return v.strip()
        return v


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: str
    name: str
    content: str
    created_at: datetime


# ============= Contact Schemas =============

class ContactCreate(BaseModel):
    phone_number: str
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    
    @field_validator('phone_number')
    @classmethod
    def validate_phone_number(cls, v):
        if not v.startswith('+'):
            raise ValueError('Phone number must start with +')
        if not v[1:].isdigit():
            raise ValueError('Phone number must contain only digits after +')
        if not (10 <= len(v) <= 15):
            raise ValueError('Phone number must be between 10 and 15 characters')
        return v


class ContactUpdate(BaseModel):
    phone_number: Optional[str] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: str
    phone_number: str
    name: Optional[str] = None
    email: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ContactWithGroups(ContactResponse):
    groups: List['ContactGroupResponse'] = []


# ============= Contact Group Schemas =============

class ContactGroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Group name cannot be empty')
        if len(v) > 100:
            raise ValueError('Group name cannot exceed 100 characters')
        return v.strip()


class ContactGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ContactGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ContactGroupWithContacts(ContactGroupResponse):
    contacts: List[ContactResponse] = []
    contact_count: int = 0


class AddContactsToGroup(BaseModel):
    contact_ids: List[int]
    
    @field_validator('contact_ids')
    @classmethod
    def validate_contacts(cls, v):
        if not v:
            raise ValueError('At least one contact ID is required')
        if len(v) != len(set(v)):
            raise ValueError('Duplicate contact IDs found')
        return v


# ============= API Key Schemas =============

class APIKeyCreate(BaseModel):
    pass


class APIKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: str
    key: str
    is_active: bool
    created_at: datetime
    last_used: Optional[datetime] = None


class APIKeyUpdate(BaseModel):
    is_active: bool


# ============= Delivery Report Schemas =============

class DeliveryReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    sms_id: int
    status: str
    updated_at: datetime


# ============= Pagination & Filters =============

class PaginationParams(BaseModel):
    skip: int = 0
    limit: int = 100
    
    @field_validator('skip')
    @classmethod
    def validate_skip(cls, v):
        if v < 0:
            raise ValueError('Skip must be non-negative')
        return v
    
    @field_validator('limit')
    @classmethod
    def validate_limit(cls, v):
        if v < 1:
            raise ValueError('Limit must be at least 1')
        if v > 1000:
            raise ValueError('Limit cannot exceed 1000')
        return v


class MessageFilter(BaseModel):
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    recipient: Optional[str] = None


# # ============= Stats & Analytics =============

# class WalletStats(BaseModel):
#     current_balance: float
#     total_spent: float
#     total_topups: float
#     total_messages_sent: int


# class SMSStats(BaseModel):
#     total_sent: int
#     total_pending: int
#     total_delivered: int
#     total_failed: int
#     total_cost: float
    
    