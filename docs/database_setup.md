# Database Setup Guide for Game Design Team

## Overview
Your application now uses SQLite database to persist session data for the Game Design Team agents. This allows conversations and game design progress to be saved and resumed across different runs.

## Database Configuration

### Current Setup
- **Database Type**: SQLite (file-based, no server required)
- **Database File**: `design_team_sessions.db` (created in the project root)
- **Connection**: Synchronous SQLite via SQLAlchemy
- **Session Service**: Google ADK's `DatabaseSessionService`

### Files Modified
1. `main.py` - Added database initialization and updated DB URL
2. `__main__.py` - Added database initialization call
3. `requirements.txt` - Added SQLAlchemy and aiosqlite dependencies
4. `database_manager.py` - Created for database inspection and management

## Database Tables
The ADK `DatabaseSessionService` automatically creates these tables:
- **sessions**: Stores session metadata and state
- **app_states**: Application-level state data
- **user_states**: User-specific state data  
- **events**: Conversation events and interactions

## Database Management

### Check Database Status
```bash
python -m design_team.database_manager
```

### Access Database Directly
```bash
sqlite3 design_team_sessions.db
```

Common SQLite commands:
- `.tables` - List all tables
- `.schema` - Show table schemas
- `SELECT * FROM sessions;` - View all sessions
- `SELECT * FROM events LIMIT 10;` - View recent events

### Clear Database Data
```python
from design_team.database_manager import clear_database
clear_database()  # Removes all data but keeps tables
```

### Delete Specific Entries
```python
from design_team.database_manager import delete_session, delete_user_data, delete_old_sessions

# Delete a specific session
delete_session('session_001')

# Delete all data for a user
delete_user_data('user_1')

# Delete sessions older than 7 days
delete_old_sessions(7)
```

### SQL Commands for Direct Database Access
```sql
-- Delete a specific session
DELETE FROM sessions WHERE id = 'session_001';

-- Delete sessions by user
DELETE FROM sessions WHERE user_id = 'user_1';

-- Delete old sessions (older than 7 days)
DELETE FROM sessions WHERE create_time < datetime('now', '-7 days');

-- Delete all events for a session
DELETE FROM events WHERE session_id = 'session_001';

-- Delete user states
DELETE FROM user_states WHERE user_id = 'user_1';

-- Delete app states
DELETE FROM app_states WHERE app_name = 'game_design_team_app';
```

### Delete Database
```python
from design_team.database_manager import delete_database
delete_database()  # Removes entire database file
```

## Environment Variables
Create a `.env` file for configuration:
```
# Optional: Override database URL
# DB_URL=sqlite:///custom_database.db

# Google AI API configuration
# GOOGLE_API_KEY=your_key_here
GOOGLE_GENAI_USE_VERTEXAI=False
```

## Benefits of Database Persistence
1. **Session Continuity**: Conversations resume where they left off
2. **Progress Tracking**: Game design progress is saved automatically
3. **Multi-User Support**: Different users can have separate sessions
4. **Audit Trail**: All interactions are logged for review
5. **Crash Recovery**: No data loss if application stops unexpectedly

## Troubleshooting

### Common Issues
1. **Permission Errors**: Ensure write permissions in project directory
2. **Database Corruption**: Delete database file and restart
3. **Connection Errors**: Check that SQLite is available in Python environment

### Database Location
The database file is created in the same directory where you run the application. If you run from different directories, multiple database files may be created.

### Backup Strategy
Simply copy the `design_team_sessions.db` file to backup your data:
```bash
cp design_team_sessions.db backup_$(date +%Y%m%d_%H%M%S).db
```

## Next Steps
- The database is now fully configured and working
- Your game design sessions will persist automatically
- Use the database manager to monitor and maintain your data
- Consider implementing session cleanup for old/unused sessions
