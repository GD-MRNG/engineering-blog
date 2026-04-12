"""
MANIFEST BUILDER
============================================

DESCRIPTION:
    This script generates manifest entries for Jekyll posts using
    pipe-delimited format and appends them to 'manifest.txt'.

FORMAT (manifest.txt):
    number title | date | image | [tags]
    Example:
    3.4.1 Cost Awareness | 2026-01-14 | tier_3.jpg | [Tier 3, Concept]

USAGE:
    Run: python manifest_builder.py
"""

import os
from datetime import datetime, timedelta

# --- Global Constants ---
MANIFEST_FILE = "manifest.txt"


def increment_version(version):
    """
    Increments the last segment of a semantic version.
    Example: 2.3.1 -> 2.3.2
    """
    parts = version.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def build_manifest_entries(starting_number, starting_date, image, tags, topics):
    """
    Generates formatted manifest lines.
    """
    current_version = starting_number
    current_date = datetime.strptime(starting_date, "%Y-%m-%d")

    lines = []

    for topic in topics:
        line = f"{current_version} {topic}|{current_date.strftime('%Y-%m-%d')}|{image}|{tags}"
        lines.append(line)

        # Increment for next iteration
        current_version = increment_version(current_version)
        current_date += timedelta(days=1)

    return lines


def append_to_manifest(lines):
    """
    Appends generated lines to manifest.txt.
    """
    with open(MANIFEST_FILE, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def main():
    print("--- Manifest Builder ---")

    starting_number = input("Starting number (e.g., 2.1.1): ").strip()
    starting_date = input("Starting date (YYYY-MM-DD): ").strip()
    image = input("Image filename (e.g., tier_1.jpg): ").strip()
    tags = input("Tags (include brackets, e.g., [Tier 1,Concept]): ").strip()

    topics_input = input("Topics (comma-separated): ").strip()
    topics = [t.strip() for t in topics_input.split(",") if t.strip()]

    if not topics:
        print("No topics provided. Exiting.")
        return

    lines = build_manifest_entries(starting_number, starting_date, image, tags, topics)

    append_to_manifest(lines)

    print("\n--- Entries Appended to manifest.txt ---")
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
