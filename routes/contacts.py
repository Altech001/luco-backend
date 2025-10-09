from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List

from database.maindb import get_db
from models.models import Contact, ContactGroup, Users, contact_group_association
from schemas.schema import (
    ContactCreate, ContactUpdate, ContactResponse, ContactWithGroups,
    ContactGroupCreate, ContactGroupUpdate, ContactGroupResponse, 
    ContactGroupWithContacts, AddContactsToGroup, PaginationParams
)
# Import your existing auth
from routes.authclerk import get_current_user

contacts = APIRouter(
    prefix="/api/v1/contacts",
    tags=["Contact Management"]
)

groups = APIRouter(
    prefix="/api/v1/groups",
    tags=["Contact Groups"]
)


# ============= Helper Functions =============

async def get_current_user_id(request: Request, db: Session = Depends(get_db)) -> str:
    """Get user_id from your existing auth"""
    session = await get_current_user(request, db)
    # session_userid = "user_2xQ4wGyrwRavEZmeadP4vd5Sx8z"
    
    # Get user from database
    db_user = db.query(Users).filter(Users.clerk_user_id == session.userid).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in database"
        )
    
    return db_user.id


def verify_contact_ownership(db: Session, contact_id: int, user_id: str) -> Contact:
    """Verify contact belongs to user"""
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.user_id == user_id
    ).first()
    
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found or access denied"
        )
    return contact


def verify_group_ownership(db: Session, group_id: int, user_id: str) -> ContactGroup:
    """Verify group belongs to user"""
    group = db.query(ContactGroup).filter(
        ContactGroup.id == group_id,
        ContactGroup.user_id == user_id
    ).first()
    
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found or access denied"
        )
    return group


# ============= CONTACT ENDPOINTS =============

@contacts.post("/", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    contact_data: ContactCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Create a new contact"""
    
    # Check if contact already exists for this user
    existing = db.query(Contact).filter(
        Contact.user_id == user_id,
        Contact.phone_number == contact_data.phone_number
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact with this phone number already exists"
        )
    
    # Create contact
    contact = Contact(
        user_id=user_id,
        phone_number=contact_data.phone_number,
        name=contact_data.name,
        email=contact_data.email
    )
    
    db.add(contact)
    db.commit()
    db.refresh(contact)
    
    return contact


@contacts.get("/", response_model=List[ContactResponse])
def get_all_contacts(
    skip: int = 0,
    limit: int = 100,
    is_active: bool = None,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get all contacts for the current user"""
    
    query = db.query(Contact).filter(Contact.user_id == user_id)
    
    if is_active is not None:
        query = query.filter(Contact.is_active == is_active)
    
    contacts = query.offset(skip).limit(limit).all()
    return contacts


@contacts.get("/{contact_id}", response_model=ContactWithGroups)
def get_contact(
    contact_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get a specific contact with their groups"""
    
    contact = verify_contact_ownership(db, contact_id, user_id)
    
    # Manually construct response with groups
    return ContactWithGroups(
        id=contact.id,
        user_id=contact.user_id,
        phone_number=contact.phone_number,
        name=contact.name,
        email=contact.email,
        is_active=contact.is_active,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        groups=[ContactGroupResponse.model_validate(g) for g in contact.groups]
    )


@contacts.put("/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: int,
    contact_data: ContactUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Update a contact"""
    
    contact = verify_contact_ownership(db, contact_id, user_id)
    
    # Check if phone number is being changed to an existing one
    if contact_data.phone_number and contact_data.phone_number != contact.phone_number:
        existing = db.query(Contact).filter(
            Contact.user_id == user_id,
            Contact.phone_number == contact_data.phone_number,
            Contact.id != contact_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Another contact with this phone number already exists"
            )
    
    # Update fields
    update_data = contact_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contact, field, value)
    
    db.commit()
    db.refresh(contact)
    
    return contact


@contacts.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(
    contact_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Delete a contact"""
    
    contact = verify_contact_ownership(db, contact_id, user_id)
    
    db.delete(contact)
    db.commit()
    
    return None


# ============= CONTACT GROUP ENDPOINTS =============

@groups.post("/", response_model=ContactGroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    group_data: ContactGroupCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Create a new contact group"""
    
    # Check if group name already exists for this user
    existing = db.query(ContactGroup).filter(
        ContactGroup.user_id == user_id,
        ContactGroup.name == group_data.name
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group with this name already exists"
        )
    
    # Create group
    group = ContactGroup(
        user_id=user_id,
        name=group_data.name,
        description=group_data.description
    )
    
    db.add(group)
    db.commit()
    db.refresh(group)
    
    return group


@groups.get("/", response_model=List[ContactGroupResponse])
def get_all_groups(
    skip: int = 0,
    limit: int = 100,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get all contact groups for the current user"""
    
    groups = db.query(ContactGroup).filter(
        ContactGroup.user_id == user_id
    ).offset(skip).limit(limit).all()
    
    return groups


@groups.get("/{group_id}", response_model=ContactGroupWithContacts)
def get_group(
    group_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get a specific group with all its contacts"""
    
    group = verify_group_ownership(db, group_id, user_id)
    
    return ContactGroupWithContacts(
        id=group.id,
        user_id=group.user_id,
        name=group.name,
        description=group.description,
        created_at=group.created_at,
        updated_at=group.updated_at,
        contacts=[ContactResponse.model_validate(c) for c in group.contacts],
        contact_count=len(group.contacts)
    )


@groups.put("/{group_id}", response_model=ContactGroupResponse)
def update_group(
    group_id: int,
    group_data: ContactGroupUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Update a contact group"""
    
    group = verify_group_ownership(db, group_id, user_id)
    
    # Check if name is being changed to an existing one
    if group_data.name and group_data.name != group.name:
        existing = db.query(ContactGroup).filter(
            ContactGroup.user_id == user_id,
            ContactGroup.name == group_data.name,
            ContactGroup.id != group_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Another group with this name already exists"
            )
    
    # Update fields
    update_data = group_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(group, field, value)
    
    db.commit()
    db.refresh(group)
    
    return group


@groups.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Delete a contact group (contacts remain)"""
    
    group = verify_group_ownership(db, group_id, user_id)
    
    db.delete(group)
    db.commit()
    
    return None


# ============= GROUP MEMBERSHIP ENDPOINTS =============

@groups.post("/{group_id}/contacts", status_code=status.HTTP_200_OK)
def add_contacts_to_group(
    group_id: int,
    data: AddContactsToGroup,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Add multiple contacts to a group"""
    
    group = verify_group_ownership(db, group_id, user_id)
    
    # Verify all contacts belong to user
    contacts = db.query(Contact).filter(
        Contact.id.in_(data.contact_ids),
        Contact.user_id == user_id
    ).all()
    
    if len(contacts) != len(data.contact_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Some contact IDs are invalid or don't belong to you"
        )
    
    # Add contacts to group (skip if already exists)
    added_count = 0
    for contact in contacts:
        if contact not in group.contacts:
            group.contacts.append(contact)
            added_count += 1
    
    db.commit()
    
    return {
        "message": f"Successfully added {added_count} contact(s) to group",
        "total_contacts_in_group": len(group.contacts)
    }


@groups.delete("/{group_id}/contacts/{contact_id}", status_code=status.HTTP_200_OK)
def remove_contact_from_group(
    group_id: int,
    contact_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Remove a contact from a group"""
    
    group = verify_group_ownership(db, group_id, user_id)
    contact = verify_contact_ownership(db, contact_id, user_id)
    
    if contact not in group.contacts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact is not in this group"
        )
    
    group.contacts.remove(contact)
    db.commit()
    
    return {
        "message": "Contact removed from group successfully",
        "remaining_contacts": len(group.contacts)
    }


@groups.get("/{group_id}/contacts", response_model=List[ContactResponse])
def get_group_contacts(
    group_id: int,
    skip: int = 0,
    limit: int = 100,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get all contacts in a specific group"""
    
    group = verify_group_ownership(db, group_id, user_id)
    
    # Paginate contacts
    contacts = group.contacts[skip:skip + limit]
    
    return contacts


# ============= BULK OPERATIONS =============

@contacts.post("/bulk", response_model=dict, status_code=status.HTTP_201_CREATED)
def bulk_create_contacts(
    contacts_data: List[ContactCreate],
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Bulk create contacts"""
    
    if len(contacts_data) > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create more than 1000 contacts at once"
        )
    
    created_contacts = []
    skipped = []
    
    for contact_data in contacts_data:
        # Check if exists
        existing = db.query(Contact).filter(
            Contact.user_id == user_id,
            Contact.phone_number == contact_data.phone_number
        ).first()
        
        if existing:
            skipped.append(contact_data.phone_number)
            continue
        
        contact = Contact(
            user_id=user_id,
            phone_number=contact_data.phone_number,
            name=contact_data.name,
            email=contact_data.email
        )
        created_contacts.append(contact)
        db.add(contact)
    
    db.commit()
    
    return {
        "created": len(created_contacts),
        "skipped": len(skipped),
        "skipped_numbers": skipped,
        "message": f"Successfully created {len(created_contacts)} contacts"
    }