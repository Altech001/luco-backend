import africastalking
from dotenv import load_dotenv
import os
import sys
from pathlib import Path
# from smspayload import SMSMessage
from functions.smspayload import SMSMessage

project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

load_dotenv()


class LucoSMS:
    def __init__(self, api_key=None, username=None, sender_id=None):
        
        self.username = username or os.getenv("AT_LIVE_USERNAME")
        if not self.username:
            raise ValueError("Live username must be provided either in constructor or as AT_LIVE_USERNAME environment variable")

        self.api_key = api_key or os.getenv("AT_LIVE_API_KEY")
        if not self.api_key:
            raise ValueError("API key must be provided either in constructor or as AT_LIVE_API_KEY environment variable")

        self.sender_id = sender_id or os.getenv("AT_SENDER_ID")
        if not self.sender_id:
            raise ValueError("Sender ID must be provided either in constructor or as AT_SENDER_ID environment variable")
        
        africastalking.initialize(username=self.username, api_key=self.api_key)
        self.sms = africastalking.SMS

    def send_message(self, message: str, recipients: list[str], sender_id: str = None):
        effective_sender_id = sender_id or self.sender_id
        if not effective_sender_id:
            raise ValueError("Sender ID must be specified for live environment")

        sms_data = SMSMessage(message=message, recipients=recipients)

        try:
            response = self.sms.send(sms_data.message, sms_data.recipients, sender_id=effective_sender_id)
            return response
        except Exception as e:

            raise Exception(f"Failed to send SMS: {str(e)}")
