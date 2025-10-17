"""
HMAC utilities for secure message signing and verification.
Same logic as Site Agent for consistent security.
"""

import hmac
import hashlib
import json
import time
import os
import logging

logger = logging.getLogger(__name__)


def compute_hmac(ts: int, nonce: str, payload: dict) -> str:
    """
    Compute HMAC-SHA256 signature for a message.
    
    Args:
        ts: Unix timestamp
        nonce: Unique nonce (UUID)
        payload: Message payload (dict)
    
    Returns:
        Hex-encoded HMAC signature
    
    Example:
        sig = compute_hmac(1734370000, "uuid-here", {"id": 123, "data": "..."})
    """
    secret = os.getenv('HMAC_SECRET')
    if not secret:
        raise ValueError("HMAC_SECRET not set in environment")
    
    secret_bytes = secret.encode('utf-8')
    
    # Compact JSON (sorted keys, no whitespace)
    compact_json = json.dumps(
        payload,
        separators=(',', ':'),
        sort_keys=True,
        ensure_ascii=False
    )
    
    # Message format: "{ts}.{nonce}.{compact_json}"
    message = f"{ts}.{nonce}.{compact_json}"
    message_bytes = message.encode('utf-8')
    
    # Compute HMAC-SHA256
    signature = hmac.new(
        secret_bytes,
        message_bytes,
        hashlib.sha256
    ).hexdigest()
    
    return signature


def verify_hmac(ts: int, nonce: str, payload: dict, sig: str, ttl: int = 45) -> bool:
    """
    Verify HMAC signature for a message.
    
    Args:
        ts: Unix timestamp from message
        nonce: Nonce from message
        payload: Message payload
        sig: Signature to verify
        ttl: Time-to-live in seconds (default 45)
    
    Returns:
        True if signature is valid and not expired, False otherwise
    
    Example:
        is_valid = verify_hmac(1734370000, "uuid", {...}, "abc123def456")
    """
    # Check TTL (message not too old or from future)
    now = int(time.time())
    if abs(now - ts) > ttl:
        logger.warning(f"Message expired: ts={ts}, now={now}, diff={abs(now-ts)}s")
        return False
    
    # Compute expected signature
    try:
        expected_sig = compute_hmac(ts, nonce, payload)
    except Exception as e:
        logger.error(f"Failed to compute HMAC: {e}")
        return False
    
    # Constant-time comparison
    is_valid = hmac.compare_digest(expected_sig, sig)
    
    if not is_valid:
        logger.warning(f"HMAC mismatch: expected={expected_sig[:16]}..., got={sig[:16]}...")
    
    return is_valid


def create_signed_message(msg_type: str, payload: dict) -> dict:
    """
    Create a signed message ready to send.
    
    Args:
        msg_type: Message type (e.g., "feedback_result")
        payload: Message payload
    
    Returns:
        Complete message with ts, nonce, sig fields
    
    Example:
        msg = create_signed_message("feedback_result", {
            "id": "uuid",
            "ok": True,
            "result": {...}
        })
    """
    import uuid
    
    ts = int(time.time())
    nonce = str(uuid.uuid4())
    sig = compute_hmac(ts, nonce, payload)
    
    return {
        'type': msg_type,
        **payload,
        'ts': ts,
        'nonce': nonce,
        'sig': sig
    }

