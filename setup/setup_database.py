#!/usr/bin/env python3
"""
Database Schema Setup Script

Creates the database and all required tables/schema for the GitHub Sync Service.
Run this FIRST before starting the application.
"""

import sqlite3
import os
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database path resolved relative to the repository structure for consistency
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = (BASE_DIR / 'data' / 'github_issues.db').resolve()
DATABASE_PATH = os.getenv('DATABASE_PATH', str(DEFAULT_DATABASE_PATH))

def ensure_database_directory():
    """Ensure the database directory exists"""
    db_dir = Path(DATABASE_PATH).parent
    if not db_dir.exists():
        db_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created database directory: {db_dir}")

def create_database_schema():
    """Create all required database tables and schema"""
    ensure_database_directory()
    
    # Check if database already exists
    db_exists = os.path.exists(DATABASE_PATH)
    if db_exists:
        logger.info(f"Database already exists at: {DATABASE_PATH}")
    else:
        logger.info(f"Creating new database at: {DATABASE_PATH}")
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Check if repositories table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='repositories'")
    table_exists = cursor.fetchone() is not None
    
    # Create repositories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS repositories (
            repo TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            main_category TEXT NOT NULL,
            classification TEXT NOT NULL,
            priority INTEGER NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            filters TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    if table_exists:
        logger.info("✅ Repositories table already exists")
    else:
        logger.info("✅ Created repositories table")
    
    # Check if issues table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='issues'")
    issues_exists = cursor.fetchone() is not None
    
    # Create issues table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY,
            number INTEGER,
            title TEXT,
            body TEXT,
            state TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            closed_at TIMESTAMP,
            user_login TEXT,
            user_type TEXT,
            assignee_login TEXT,
            assignee_type TEXT,
            labels TEXT,
            assignees TEXT,
            milestone_title TEXT,
            milestone_state TEXT,
            repo TEXT,
            url TEXT,
            html_url TEXT,
            user_avatar_url TEXT,
            comments_count INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            UNIQUE(repo, number)
        )
    ''')
    if issues_exists:
        logger.info("✅ Issues table already exists")
    else:
        logger.info("✅ Created issues table")

    # Check if pull_requests table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pull_requests'")
    prs_exists = cursor.fetchone() is not None
    
    # Create pull_requests table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pull_requests (
            id INTEGER PRIMARY KEY,
            number INTEGER,
            title TEXT,
            body TEXT,
            state TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            closed_at TIMESTAMP,
            merged_at TIMESTAMP,
            user_login TEXT,
            user_type TEXT,
            assignee_login TEXT,
            assignee_type TEXT,
            labels TEXT,
            assignees TEXT,
            milestone_title TEXT,
            milestone_state TEXT,
            repo TEXT,
            url TEXT,
            html_url TEXT,
            user_avatar_url TEXT,
            draft BOOLEAN DEFAULT 0,
            merged BOOLEAN DEFAULT 0,
            base_ref TEXT,
            head_ref TEXT,
            comments_count INTEGER DEFAULT 0,
            review_comments_count INTEGER DEFAULT 0,
            commits_count INTEGER DEFAULT 0,
            additions INTEGER DEFAULT 0,
            deletions INTEGER DEFAULT 0,
            changed_files INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            UNIQUE(repo, number)
        )
    ''')
    if prs_exists:
        logger.info("✅ Pull requests table already exists")
    else:
        logger.info("✅ Created pull_requests table")

    # Check if sync_history table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sync_history'")
    sync_exists = cursor.fetchone() is not None
    
    # Create comprehensive sync history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sync_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_session_id TEXT NOT NULL,
            sync_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            repository TEXT NOT NULL,
            sync_type TEXT NOT NULL,
            issues_new INTEGER DEFAULT 0,
            issues_updated INTEGER DEFAULT 0,
            issues_total INTEGER DEFAULT 0,
            prs_new INTEGER DEFAULT 0,
            prs_updated INTEGER DEFAULT 0,
            prs_total INTEGER DEFAULT 0,
            duration_seconds INTEGER DEFAULT 0,
            status TEXT DEFAULT 'success',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    if sync_exists:
        logger.info("✅ Sync history table already exists")
    else:
        logger.info("✅ Created sync_history table")
    
    # Create indexes for better performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_issues_repo_number ON issues(repo, number)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_issues_updated_at ON issues(updated_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_prs_repo_number ON pull_requests(repo, number)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_prs_updated_at ON pull_requests(updated_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sync_history_date ON sync_history(sync_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sync_history_session ON sync_history(sync_session_id)')
    logger.info("✅ Created database indexes")
    
    conn.commit()
    conn.close()
    
    if db_exists:
        logger.info("🎉 Database schema verification completed - all tables exist!")
    else:
        logger.info("🎉 Database schema setup completed successfully!")

def main():
    """Main setup function"""
    try:
        logger.info("Setting up GitHub Sync Service database schema...")
        create_database_schema()
        logger.info("Database schema setup completed!")
    except Exception as e:
        logger.error(f"Database setup failed: {e}")
        raise

if __name__ == "__main__":
    main()