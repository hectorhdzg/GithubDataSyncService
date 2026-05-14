#!/usr/bin/env python3
"""
Database Schema Setup Script

Creates the database and all required tables/indexes for the GitHub Sync Service.
The schema here mirrors app.py's _init_database exactly so that either path
(setup script first, or cold-start via the app) produces the same result.

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
    """Create all required database tables and indexes.

    This must stay in sync with GitHubSyncService._init_database in src/app.py.
    """
    ensure_database_directory()

    db_exists = os.path.exists(DATABASE_PATH)
    if db_exists:
        logger.info(f"Database already exists at: {DATABASE_PATH}")
    else:
        logger.info(f"Creating new database at: {DATABASE_PATH}")

    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    # ── repositories ─────────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS repositories (
            repo TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            main_category TEXT NOT NULL,
            classification TEXT NOT NULL,
            language_group TEXT DEFAULT 'Other',
            priority INTEGER NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            filters TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    logger.info("✅ repositories table ready")

    # ── issues ───────────────────────────────────────────────────────────
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
            repo TEXT,
            html_url TEXT,
            labels TEXT,
            assignees TEXT,
            milestone TEXT,
            repository TEXT,
            url TEXT,
            assignee_login TEXT,
            user_login TEXT,
            user_avatar_url TEXT,
            comments_count INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            UNIQUE(id)
        )
    ''')
    logger.info("✅ issues table ready")

    # ── pull_requests ────────────────────────────────────────────────────
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
            repo TEXT,
            url TEXT,
            html_url TEXT,
            labels TEXT,
            assignees TEXT,
            assignee_login TEXT,
            assignee_type TEXT,
            milestone TEXT,
            repository TEXT,
            user_login TEXT,
            user_avatar_url TEXT,
            draft BOOLEAN DEFAULT 0,
            merged BOOLEAN DEFAULT 0,
            base_ref TEXT,
            head_ref TEXT,
            comments_count INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            UNIQUE(id)
        )
    ''')
    logger.info("✅ pull_requests table ready")

    # ── sync_metadata ────────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sync_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_type TEXT,
            repository TEXT,
            last_sync TIMESTAMP,
            status TEXT,
            items_synced INTEGER DEFAULT 0,
            error_message TEXT
        )
    ''')
    logger.info("✅ sync_metadata table ready")

    # ── sync_history ─────────────────────────────────────────────────────
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
    logger.info("✅ sync_history table ready")

    # ── repository_labels ────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS repository_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repository TEXT NOT NULL,
            name TEXT NOT NULL,
            color TEXT,
            description TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    logger.info("✅ repository_labels table ready")

    # ── indexes ──────────────────────────────────────────────────────────
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sync_history_date ON sync_history(sync_date DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sync_history_session ON sync_history(sync_session_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sync_history_repo ON sync_history(repository)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_repository_labels_repo ON repository_labels(repository)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_repository_labels_repo_name ON repository_labels(repository, name)')
    logger.info("✅ indexes ready")

    conn.commit()
    conn.close()

    logger.info("🎉 Database schema setup completed successfully!")


def main():
    """Main setup function"""
    try:
        logger.info("Setting up GitHub Sync Service database schema...")
        create_database_schema()
    except Exception as e:
        logger.error(f"Schema setup failed: {e}")
        raise


if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()