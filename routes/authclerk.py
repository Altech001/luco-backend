from fastapi import APIRouter, Depends, Request, HTTPException
from clerk_backend_api import Clerk
from clerk_backend_api.models import ClerkErrors, SDKError
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from database.maindb import get_db
from models.models import Users
import jwt
from config.config import CLERK_SECRET_KEY

print(CLERK_SECRET_KEY)

load_dotenv()

auth_router = APIRouter()

clerk_client = Clerk(bearer_auth=CLERK_SECRET_KEY)


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    auth_header = request.headers.get("Authorization", "")

    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    if not auth_header.startswith("Bearer "):

        raise HTTPException(
            status_code=401, detail="Invalid authorization header format"
        )

    session_token = auth_header.replace("Bearer ", "")

    try:
        try:
            session = clerk_client.sessions.get_session(session_token)

        except Exception as session_error:

            try:
                decoded_token = jwt.decode(
                    session_token, options={"verify_signature": False}
                )

                session_id = decoded_token.get("sid")
                if not session_id:
                    raise HTTPException(
                        status_code=401, detail="Invalid session token: No session ID"
                    )
                session = clerk_client.sessions.get(session_id=session_id)
            except Exception as jwt_error:
                raise HTTPException(
                    status_code=401,
                    detail=f"Failed to validate session token: {str(jwt_error)}",
                )

        user_details = clerk_client.users.get(user_id=session.user_id)

        email = (
            user_details.email_addresses[0].email_address
            if user_details.email_addresses
            else None
        )
        username = (
            user_details.username
            or user_details.first_name
            or f"user_{session.user_id}"
        )

        db_user = db.query(Users).filter(Users.email == email).first()

        if not db_user:
            new_user = Users(
                username=username, email=email, clerk_user_id=session.user_id
            )

            db.add(new_user)
            db.commit()
            db.refresh(new_user)
        else:
            print(f"User exists: {db_user.__dict__}")

        return session

    except ClerkErrors as e:

        raise HTTPException(
            status_code=401, detail=f"Invalid or expired session token: {str(e)}"
        )
    except SDKError as e:

        raise HTTPException(status_code=500, detail=f"SDK error: {str(e)}")
    except Exception as e:

        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@auth_router.get("/protected")
async def protected_route(user=Depends(get_current_user)):
    try:
        user_details = clerk_client.users.get(user_id=user.user_id)
        return {
            "message": f"Hello, {user_details.first_name}!",
            "user_id": user_details.id,
            "session": user_details.profile_image_url,
            "email": (
                user_details.email_addresses[0].email_address
                if user_details.email_addresses
                else None
            ),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching user details: {str(e)}"
        )
