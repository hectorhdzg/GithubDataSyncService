#!/usr/bin/env python3
"""
Repository Data Population Script

Populates the database with repository configurations loaded from
setup/data/repositories.json.

Run this AFTER running setup_database.py (or use setup.py for both).
"""

import sqlite3
import json
import os
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = (BASE_DIR / 'data' / 'github_issues.db').resolve()
DATABASE_PATH = os.getenv('DATABASE_PATH', str(DEFAULT_DATABASE_PATH))
REPOSITORIES_JSON = Path(__file__).resolve().parent / 'data' / 'repositories.json'


def load_repositories(json_path=None):
    """Load repository definitions from JSON file."""
    path = Path(json_path) if json_path else REPOSITORIES_JSON
    if not path.exists():
        raise FileNotFoundError(f"Repository data file not found: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def populate_repositories(json_path=None):
    """Populate database with repository configurations from JSON."""
    repositories = load_repositories(json_path)

    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM repositories')
    existing_count = cursor.fetchone()[0]

    if existing_count > 0:
        logger.info(f"Found {existing_count} existing repositories — skipping population")
        conn.close()
        return

    logger.info(f"Loading {len(repositories)} repositories from {REPOSITORIES_JSON.name}")

    added = 0
    for repo in repositories:
        try:
            cursor.execute('''
                INSERT INTO repositories
                (repo, display_name, main_category, classification, priority, is_active, filters)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                repo['repo'],
                repo['display_name'],
                repo['main_category'],
                repo['classification'],
                repo['priority'],
                1 if repo.get('is_active', True) else 0,
                json.dumps(repo.get('filters', {}))
            ))
            logger.info(f"  Added: {repo['repo']} ({repo['main_category']})")
            added += 1
        except sqlite3.IntegrityError:
            logger.info(f"  Skipped (already exists): {repo['repo']}")

    conn.commit()
    conn.close()
    logger.info(f"Populated {added} repositories")


def main():
    """Main population function"""
    try:
        logger.info("Populating GitHub Sync Service repository data...")
        populate_repositories()
    except Exception as e:
        logger.error(f"Data population failed: {e}")
        raise


if __name__ == "__main__":
    main()