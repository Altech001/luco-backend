from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List

from database.maindb import get_db
from models.models import Templates, Users
from schemas.schema import TemplateCreate, TemplateUpdate, TemplateResponse
from routes.authclerk import get_current_user

templates = APIRouter(
    prefix="/api/v1/templates",
    tags=["Templates"]
)


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


def verify_template_ownership(db: Session, template_id: int, user_id: str) -> Templates:
    """Verify template belongs to user"""
    template = db.query(Templates).filter(
        Templates.id == template_id,
        Templates.user_id == user_id
    ).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found or access denied"
        )
    return template


# ============= TEMPLATE ENDPOINTS =============

@templates.post("/", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    template_data: TemplateCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Create a new SMS template"""
    
    # Check if template name already exists for this user
    existing = db.query(Templates).filter(
        Templates.user_id == user_id,
        Templates.name == template_data.name
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template with this name already exists"
        )
    
    template = Templates(
        user_id=user_id,
        name=template_data.name,
        content=template_data.content
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    
    return template


@templates.get("/", response_model=List[TemplateResponse])
def get_all_templates(
    skip: int = 0,
    limit: int = 100,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get all templates for the current user"""
    
    templates = db.query(Templates).filter(
        Templates.user_id == user_id
    ).offset(skip).limit(limit).all()
    
    return templates


@templates.get("/{template_id}", response_model=TemplateResponse)
def get_template(
    template_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get a specific template by ID"""
    
    template = verify_template_ownership(db, template_id, user_id)
    return template


@templates.put("/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: int,
    template_data: TemplateUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Update an existing template"""
    
    template = verify_template_ownership(db, template_id, user_id)
    
    # Check if new name conflicts with existing template
    if template_data.name and template_data.name != template.name:
        existing = db.query(Templates).filter(
            Templates.user_id == user_id,
            Templates.name == template_data.name,
            Templates.id != template_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Another template with this name already exists"
            )
    
    # Update fields
    update_data = template_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)
    
    db.commit()
    db.refresh(template)
    
    return template


@templates.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Delete a template"""
    
    template = verify_template_ownership(db, template_id, user_id)
    
    db.delete(template)
    db.commit()
    
    return None


# ============= SEARCH & BULK OPERATIONS =============

@templates.get("/search/{search_term}", response_model=List[TemplateResponse])
def search_templates(
    search_term: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Search templates by name (case-insensitive)"""
    
    templates = db.query(Templates).filter(
        Templates.user_id == user_id,
        Templates.name.ilike(f"%{search_term}%")
    ).all()
    
    return templates


@templates.post("/bulk", response_model=dict, status_code=status.HTTP_201_CREATED)
def bulk_create_templates(
    templates_data: List[TemplateCreate],
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Bulk create templates"""
    
    if len(templates_data) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create more than 100 templates at once"
        )
    
    created_templates = []
    skipped = []
    
    for template_data in templates_data:
        # Check if exists
        existing = db.query(Templates).filter(
            Templates.user_id == user_id,
            Templates.name == template_data.name
        ).first()
        
        if existing:
            skipped.append(template_data.name)
            continue
        
        template = Templates(
            user_id=user_id,
            name=template_data.name,
            content=template_data.content
        )
        created_templates.append(template)
        db.add(template)
    
    db.commit()
    
    return {
        "created": len(created_templates),
        "skipped": len(skipped),
        "skipped_names": skipped,
        "message": f"Successfully created {len(created_templates)} templates"
    }