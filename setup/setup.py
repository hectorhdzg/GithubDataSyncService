#!/usr/bin/env python3
"""
Unified Setup Runner

Creates the database schema and populates initial repository data in one step.

Usage:
    python setup/setup.py              # Full setup (schema + data)
    python setup/setup.py --schema     # Schema only
    python setup/setup.py --data       # Data only
"""

import argparse
import logging
import sys

from setup_database import create_database_schema
from populate_repositories import populate_repositories

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="GitHub Sync Service — Initial Setup")
    parser.add_argument('--schema', action='store_true', help='Create database schema only')
    parser.add_argument('--data', action='store_true', help='Populate repository data only')
    args = parser.parse_args()

    # Default: run both when no flags specified
    run_schema = args.schema or not (args.schema or args.data)
    run_data = args.data or not (args.schema or args.data)

    try:
        if run_schema:
            logger.info("── Step 1: Database schema ──")
            create_database_schema()

        if run_data:
            logger.info("── Step 2: Repository data ──")
            populate_repositories()

        logger.info("Setup complete.")
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
