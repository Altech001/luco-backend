from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Table, Text, UniqueConstraint, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from database.maindb import Base
import enum


class Users(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    wallet_balance = Column(Float, default=0.0)
    clerk_user_id = Column(String(50), unique=True, nullable=False)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    transactions = relationship("Transactions", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Messages", back_populates="user", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="user", cascade="all, delete-orphan")
    contact_groups = relationship("ContactGroup", back_populates="user", cascade="all, delete-orphan")
    templates = relationship("Templates", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("APIKeys", back_populates="user", cascade="all, delete-orphan")
    scheduled_messages = relationship("ScheduledMessages", back_populates="user", cascade="all, delete-orphan")

      
class Transactions(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    transaction_type = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=func.now(), index=True)
    
    # Relationship
    user = relationship("Users", back_populates="transactions")


class Messages(Base):
    __tablename__ = "sms_messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient = Column(String(20), nullable=False, index=True)
    message = Column(String(160), nullable=False)
    status = Column(String(20), default="pending", index=True)
    cost = Column(Float, default=32.0)
    sender_id = Column(String(20))  # For sender identification
    created_at = Column(DateTime, default=func.now(), index=True)
    
    # Relationships
    user = relationship("Users", back_populates="messages")
    delivery_reports = relationship("DeliveryReports", back_populates="message", cascade="all, delete-orphan")


#==========Contacts ===========================================

contact_group_association = Table(
    'contact_group_members',
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('contact_id', Integer, ForeignKey('contacts.id', ondelete='CASCADE'), index=True),
    Column('group_id', Integer, ForeignKey('contact_groups.id', ondelete='CASCADE'), index=True),
    Column('user_id', String(36), ForeignKey('users.id', ondelete='CASCADE'), index=True),  # Added for better queries
    Column('added_at', DateTime, default=func.now()),
    Index('idx_contact_group_user', 'contact_id', 'group_id', 'user_id')
)


class Contact(Base):
    __tablename__ = "contacts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    name = Column(String(100))
    email = Column(String(100))
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Unique constraint: one phone number per user
    __table_args__ = (
        UniqueConstraint('user_id', 'phone_number', name='uix_user_phone'),
    )
    
    # Relationships
    user = relationship("Users", back_populates="contacts")
    groups = relationship(
        "ContactGroup",
        secondary=contact_group_association,
        back_populates="contacts"
    )


class ContactGroup(Base):
    __tablename__ = "contact_groups"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Unique constraint: one group name per user
    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uix_user_group_name'),
    )
    
    # Relationships
    user = relationship("Users", back_populates="contact_groups")
    contacts = relationship(
        "Contact",
        secondary=contact_group_association,
        back_populates="groups"
    )
    
#====================================================================


class Templates(Base):
    __tablename__ = "sms_templates"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(50), nullable=False)
    content = Column(String(160), nullable=False)
    created_at = Column(DateTime, default=func.now())
    
    # Unique constraint: one template name per user
    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uix_user_template_name'),
    )
    
    # Relationship
    user = relationship("Users", back_populates="templates")


class DeliveryReports(Base):
    __tablename__ = "sms_delivery_reports"
    id = Column(Integer, primary_key=True)
    sms_id = Column(Integer, ForeignKey("sms_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)
    updated_at = Column(DateTime, default=func.now())
    
    # Relationship
    message = relationship("Messages", back_populates="delivery_reports")
    
#===== Developer API ==========================================================   
    

class APIKeys(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=func.now())
    last_used = Column(DateTime)
    
    # Relationship
    user = relationship("Users", back_populates="api_keys")
    
    
#==============Schedule sms===========================

class ScheduleStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    
class ScheduledMessages(Base):
    __tablename__ = "scheduled_messages"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Message details
    recipient = Column(String(20), nullable=False, index=True)
    message = Column(String(160), nullable=False)
    sender_id = Column(String(20))
    
    # Scheduling details
    scheduled_time = Column(DateTime, nullable=False, index=True)
    status = Column(String(20), default="pending", index=True)
    
    # Cost and processing
    cost = Column(Float, default=32.0)
    attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime)
    error_message = Column(Text)
    
    # Link to actual message once sent
    sent_message_id = Column(Integer, ForeignKey("sms_messages.id", ondelete="SET NULL"))
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    processed_at = Column(DateTime)
    
    # Relationships
    user = relationship("Users", back_populates="scheduled_messages")
    sent_message = relationship("Messages", foreign_keys=[sent_message_id])
    
    