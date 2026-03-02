"""Utility functions for the backend"""
from datetime import datetime, timezone


def to_iso8601(dt: datetime) -> str:
    """Convert datetime to ISO 8601 format with UTC timezone indicator.
    
    Args:
        dt: datetime object (assumed to be UTC if timezone-naive)
        
    Returns:
        ISO 8601 formatted string with 'Z' suffix (e.g., "2026-01-23T15:30:54.840110Z")
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace('+00:00', 'Z')