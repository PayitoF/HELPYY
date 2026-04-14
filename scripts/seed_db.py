#!/usr/bin/env python3
"""Seed the local database with synthetic test data."""

from backend.data.seed_data import seed_database

if __name__ == "__main__":
    seed_database()
    print("Database seeded successfully.")
