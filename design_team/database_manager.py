"""
Database management utilities for the game design team application.
This module provides tools to inspect and manage the SQLite database.
"""

import asyncio
import os
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

# Database file path (same as in main.py)
DB_FILE = "design_team_sessions.db"

def get_db_path() -> Path:
    """Get the absolute path to the database file."""
    return Path.cwd() / DB_FILE

def db_exists() -> bool:
    """Check if the database file exists."""
    return get_db_path().exists()

def get_db_info() -> Dict[str, Any]:
    """Get basic information about the database."""
    db_path = get_db_path()
    if not db_path.exists():
        return {"exists": False, "path": str(db_path)}
    
    try:
        # Get file size
        size_bytes = db_path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        
        # Connect and get table info
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            
            # Get list of tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            # Get row counts for each table
            table_counts = {}
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                table_counts[table] = cursor.fetchone()[0]
        
        return {
            "exists": True,
            "path": str(db_path),
            "size_bytes": size_bytes,
            "size_mb": round(size_mb, 2),
            "tables": tables,
            "table_counts": table_counts
        }
    except Exception as e:
        return {
            "exists": True,
            "path": str(db_path),
            "error": str(e)
        }

def list_sessions() -> List[Dict[str, Any]]:
    """List all sessions stored in the database."""
    db_path = get_db_path()
    if not db_path.exists():
        return []
    
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            
            # Try to find the sessions table (name may vary)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            sessions_table = None
            for table in tables:
                if 'session' in table.lower():
                    sessions_table = table
                    break
            
            if not sessions_table:
                return []
            
            # Get all sessions
            cursor.execute(f"SELECT * FROM {sessions_table}")
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            
            return [dict(zip(columns, row)) for row in rows]
    
    except Exception as e:
        print(f"Error listing sessions: {e}")
        return []

def clear_database():
    """Clear all data from the database (but keep the structure)."""
    db_path = get_db_path()
    if not db_path.exists():
        print("Database file does not exist.")
        return
    
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            # Clear each table
            for table in tables:
                cursor.execute(f"DELETE FROM {table}")
            
            conn.commit()
            print(f"Cleared data from {len(tables)} tables.")
    
    except Exception as e:
        print(f"Error clearing database: {e}")

def delete_database():
    """Delete the entire database file."""
    db_path = get_db_path()
    if db_path.exists():
        db_path.unlink()
        print(f"Deleted database file: {db_path}")
    else:
        print("Database file does not exist.")

def delete_session(session_id: str):
    """Delete a specific session and all related data."""
    db_path = get_db_path()
    if not db_path.exists():
        print("Database file does not exist.")
        return
    
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            
            # Delete in order to maintain referential integrity
            cursor.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
            events_deleted = cursor.rowcount
            
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            sessions_deleted = cursor.rowcount
            
            conn.commit()
            
            if sessions_deleted > 0:
                print(f"Deleted session '{session_id}' and {events_deleted} related events.")
            else:
                print(f"No session found with ID '{session_id}'.")
    
    except Exception as e:
        print(f"Error deleting session: {e}")

def delete_user_data(user_id: str):
    """Delete all data for a specific user."""
    db_path = get_db_path()
    if not db_path.exists():
        print("Database file does not exist.")
        return
    
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            
            # Get session IDs for this user first
            cursor.execute("SELECT id FROM sessions WHERE user_id = ?", (user_id,))
            session_ids = [row[0] for row in cursor.fetchall()]
            
            # Delete events for all user sessions
            events_deleted = 0
            for session_id in session_ids:
                cursor.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
                events_deleted += cursor.rowcount
            
            # Delete user states
            cursor.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))
            user_states_deleted = cursor.rowcount
            
            # Delete sessions
            cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            sessions_deleted = cursor.rowcount
            
            conn.commit()
            
            print(f"Deleted {sessions_deleted} sessions, {events_deleted} events, and {user_states_deleted} user states for user '{user_id}'.")
    
    except Exception as e:
        print(f"Error deleting user data: {e}")

def delete_old_sessions(days: int = 7):
    """Delete sessions older than specified number of days."""
    db_path = get_db_path()
    if not db_path.exists():
        print("Database file does not exist.")
        return
    
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            
            # Get old session IDs first
            cursor.execute(
                "SELECT id FROM sessions WHERE create_time < datetime('now', '-{} days')".format(days)
            )
            old_session_ids = [row[0] for row in cursor.fetchall()]
            
            if not old_session_ids:
                print(f"No sessions older than {days} days found.")
                return
            
            # Delete events for old sessions
            events_deleted = 0
            for session_id in old_session_ids:
                cursor.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
                events_deleted += cursor.rowcount
            
            # Delete old sessions
            cursor.execute(
                "DELETE FROM sessions WHERE create_time < datetime('now', '-{} days')".format(days)
            )
            sessions_deleted = cursor.rowcount
            
            conn.commit()
            
            print(f"Deleted {sessions_deleted} sessions and {events_deleted} events older than {days} days.")
    
    except Exception as e:
        print(f"Error deleting old sessions: {e}")

if __name__ == "__main__":
    print("Game Design Team - Database Manager")
    print("=" * 40)
    
    info = get_db_info()
    if info["exists"]:
        print(f"Database exists: {info['path']}")
        print(f"Size: {info.get('size_mb', 0)} MB")
        
        if "tables" in info:
            print(f"Tables: {', '.join(info['tables'])}")
            for table, count in info.get('table_counts', {}).items():
                print(f"  - {table}: {count} rows")
        
        if "error" in info:
            print(f"Error reading database: {info['error']}")
        
        # List sessions
        sessions = list_sessions()
        if sessions:
            print(f"\nFound {len(sessions)} session(s):")
            for session in sessions[:5]:  # Show first 5
                print(f"  - {session}")
            if len(sessions) > 5:
                print(f"  ... and {len(sessions) - 5} more")
    else:
        print("Database does not exist yet. It will be created when you first run the application.")
