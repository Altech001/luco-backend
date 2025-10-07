from dotenv import load_dotenv
import os

load_dotenv()


# Clerk secret key for backend authentication
CLERK_SECRET_KEY = os.getenv('CLERK_SECRET_KEY')

SMS_COST = 32.0

