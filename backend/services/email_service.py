"""
Email Service for OTP Verification
Handles sending emails using SendGrid HTTP API to bypass Render SMTP restrictions.
"""

import os
import json
import urllib.request
import urllib.error
import random

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER") # Must be a verified sender in SendGrid

def generate_otp(length: int = 6) -> str:
    """Generate a secure random numeric OTP of the specified length."""
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])

def send_otp_email(to_email: str, otp: str):
    """
    Send an OTP to the specified email address using SendGrid's HTTP API.
    Bypasses SMTP port restrictions on Render's free tier.
    """
    if not SENDGRID_API_KEY or not EMAIL_USER:
        print("Warning: SENDGRID_API_KEY or EMAIL_USER is missing.")
        return False
        
    url = "https://api.sendgrid.com/v3/mail/send"
    
    data = {
        "personalizations": [
            {
                "to": [{"email": to_email}],
                "subject": "Your Verification Code"
            }
        ],
        "from": {"email": EMAIL_USER},
        "content": [
            {
                "type": "text/plain",
                "value": f"Your verification code is: {otp}\n\nThis code will expire in 5 minutes."
            }
        ]
    }
    
    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }
    
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST")
    
    try:
        print("DEBUG: Sending OTP via SendGrid HTTP API...")
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status in (200, 201, 202):
                print("DEBUG: SendGrid email sent successfully!")
                return True
            else:
                print(f"DEBUG: SendGrid returned status {response.status}")
                return False
    except urllib.error.HTTPError as e:
        print(f"SendGrid HTTP Error: {e.code} - {e.read().decode('utf-8')}")
        return False
    except Exception as e:
        print(f"Error sending email via SendGrid: {e}")
        return False
