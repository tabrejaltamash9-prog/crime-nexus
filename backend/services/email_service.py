"""
Email Service for OTP Verification
Handles sending emails using SMTP via Google Mail (or any configured SMTP server).
"""

import os
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465

def generate_otp(length: int = 6) -> str:
    """Generate a secure random numeric OTP of the specified length."""
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])

def send_otp_email(to_email: str, otp: str):
    """
    Send an OTP to the specified email address using smtplib.
    """
    if not EMAIL_USER or not EMAIL_PASS:
        print("Warning: EMAIL_USER or EMAIL_PASS is not set. Cannot send email.")
        return False
        
    subject = "Your Verification Code"
    body = f"Your verification code is: {otp}\n\nThis code will expire in 5 minutes."

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        print(f"DEBUG: Connecting to SMTP server {SMTP_SERVER}:{SMTP_PORT} using SSL...")
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=10)
        print("DEBUG: SMTP_SSL connected. Logging in...")
        server.login(EMAIL_USER, EMAIL_PASS)
        text = msg.as_string()
        server.sendmail(EMAIL_USER, to_email, text)
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")
        return False
