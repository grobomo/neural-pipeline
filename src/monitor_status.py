"""Monitor status checker.

Provides a function to check if the monitor process is running.
"""
import os
from datetime import datetime, timezone
from pathlib import Path

import psutil


def check_monitor() -> dict:
    """Check the status of the monitor process.
    
    Returns a dict with exactly these keys:
        - is_running (bool): True only if process is alive AND heartbeat is fresh (<60s)
        - pid (int|None): PID read from .tmp/monitor.pid, or None if file missing
        - heartbeat_timestamp (str|None): ISO 8601 timestamp string from heartbeat file, or None if missing
        - heartbeat_age_seconds (float): seconds since last heartbeat, or float('inf') if missing
        - status_message (str): one of 'RUNNING', 'STOPPED', or 'UNRESPONSIVE'
        - status (str): alias for status_message (for backward compatibility)
    """
    project_root = Path(__file__).parent.parent
    pid_file = project_root / ".tmp" / "monitor.pid"
    heartbeat_file = project_root / "monitor" / "health" / "heartbeat"
    
    # Initialize result dict with defaults
    result = {
        "is_running": False,
        "pid": None,
        "heartbeat_timestamp": None,
        "heartbeat_age_seconds": float('inf'),
        "status_message": "STOPPED",
        "status": "STOPPED",
    }
    
    # Step 1: Read PID from .tmp/monitor.pid
    try:
        pid_text = pid_file.read_text().strip()
        pid = int(pid_text)
        result["pid"] = pid
    except FileNotFoundError:
        # PID file missing - process is STOPPED
        result["status_message"] = "STOPPED"
        result["status"] = "STOPPED"
        return result
    except (ValueError, OSError):
        # Can't read/parse PID - process is STOPPED
        result["status_message"] = "STOPPED"
        result["status"] = "STOPPED"
        return result
    
    # Step 2: Check if process is alive
    process_alive = False
    try:
        proc = psutil.Process(pid)
        is_alive = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        process_alive = is_alive
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        process_alive = False
    
    if not process_alive:
        # Process not found - status is STOPPED
        result["status_message"] = "STOPPED"
        result["status"] = "STOPPED"
        return result
    
    # Step 3: Read heartbeat file
    try:
        heartbeat_text = heartbeat_file.read_text().strip()
        result["heartbeat_timestamp"] = heartbeat_text
    except FileNotFoundError:
        # Heartbeat file missing but process is alive - UNRESPONSIVE
        result["heartbeat_age_seconds"] = float('inf')
        result["status_message"] = "UNRESPONSIVE"
        result["status"] = "UNRESPONSIVE"
        return result
    except OSError:
        # Can't read heartbeat file but process is alive - UNRESPONSIVE
        result["heartbeat_age_seconds"] = float('inf')
        result["status_message"] = "UNRESPONSIVE"
        result["status"] = "UNRESPONSIVE"
        return result
    
    # Step 4: Parse ISO 8601 timestamp from heartbeat file
    try:
        heartbeat_time = datetime.fromisoformat(heartbeat_text)
        # Ensure it's timezone-aware (interpret as UTC if naive)
        if heartbeat_time.tzinfo is None:
            heartbeat_time = heartbeat_time.replace(tzinfo=timezone.utc)
    except (ValueError, OSError):
        # Can't parse timestamp - UNRESPONSIVE
        result["heartbeat_age_seconds"] = float('inf')
        result["status_message"] = "UNRESPONSIVE"
        result["status"] = "UNRESPONSIVE"
        return result
    
    # Step 5: Calculate age in seconds
    now = datetime.now(timezone.utc)
    age_seconds = (now - heartbeat_time).total_seconds()
    result["heartbeat_age_seconds"] = age_seconds
    
    # Step 6: Determine status based on age
    if age_seconds < 60:
        # Process alive and heartbeat recent - RUNNING
        result["is_running"] = True
        result["status_message"] = "RUNNING"
        result["status"] = "RUNNING"
    else:
        # Process alive but heartbeat old - UNRESPONSIVE
        result["status_message"] = "UNRESPONSIVE"
        result["status"] = "UNRESPONSIVE"
    
    return result


if __name__ == '__main__':
    result = check_monitor()
    print(f"Status: {result['status_message']}")
    print(f"PID: {result['pid']}")
    print(f"Heartbeat age: {result['heartbeat_age_seconds']:.1f}s")
    print(f"Last heartbeat: {result['heartbeat_timestamp']}")
    print(f"Is running: {result['is_running']}")
