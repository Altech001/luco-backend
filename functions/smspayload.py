from pydantic import BaseModel, Field, validator
from typing import List



class SMSMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=160)
    recipients: List[str] = Field(..., min_items=1)

    @validator('recipients')
    def validate_phone_numbers(cls, v):
        for phone in v:
            if not phone.startswith('+'):
                raise ValueError('Phone numbers must start with +')
            if not phone[1:].isdigit():
                raise ValueError('Phone numbers must contain only digits after +')
            if not (10 <= len(phone) <= 15):
                raise ValueError('Phone numbers must be between 10 and 15 characters')
        return v
     