"""
Security Service — Input validation and prompt injection detection.
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Basic patterns often used in prompt injection attacks
INJECTION_PATTERNS = [
    r"(?i)\bignore\b.*\bprevious\b.*\binstructions\b",
    r"(?i)\bignore\b.*\babove\b.*\binstructions\b",
    r"(?i)\bsystem\b.*\bprompt\b",
    r"(?i)\byou\b.*\bare\b.*\bnow\b",
    r"(?i)\bforget\b.*\beverything\b",
    r"(?i)\boverride\b.*\binstructions\b",
    r"(?i)\bprint\b.*\binstructions\b",
    r"(?i)\btranslate\b.*\bto\b.*\benglish\b", # Often used to bypass filters
]

def check_prompt_injection(text: str) -> Tuple[bool, str]:
    """
    Check input text for common prompt injection patterns.
    
    Args:
        text: The user input to check.
        
    Returns:
        Tuple of (is_safe, reason). If is_safe is False, the query should be rejected.
    """
    if not text:
        return True, ""
        
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text):
            logger.warning(f"Potential prompt injection detected: {text[:50]}...")
            return False, "Query rejected: Potential prompt injection or policy violation detected."
            
    return True, ""
