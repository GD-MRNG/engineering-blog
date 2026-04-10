"""
JEKYLL BATCH POST GENERATOR
============================================

DESCRIPTION:
    This script automates the creation of Jekyll post stubs by reading metadata
    from a 'manifest.txt' file using '|' as a separator.

FORMAT (manifest.txt):
    title | date | image | [tags]
    Example: 3.4 Cost Awareness | 2026-01-14 | tier_3.jpg | [Tier 3, Concept]

USAGE:
    1. Place 'manifest.txt' in the /scripts folder.
    2. Run: python batch_post.py
"""

import os
import re

# --- Global Constants ---
AUTHOR = "Glenn Lum"
CATEGORIES = "journal"
TIME_SUFFIX = "11:00:00 +0800"
POSTS_DIR = "../_posts"
MANIFEST_FILE = "manifest.txt"


def slugify(text):
    """
    Converts title to a URL-friendly slug for filenames and URLs.
    Example: "3.4 Cost Awareness" -> "34-cost-awareness"
    """
    text = text.lower()
    # Remove special characters (dots, parens, etc)
    text = re.sub(r"[^\w\s-]", "", text)
    # Replace spaces/underscores with hyphens and collapse multiples
    return re.sub(r"[-\s]+", "-", text).strip("-")


def parse_line(line):
    """
    Splits the line by the pipe character and cleans whitespace.
    Expected format: title | date | image | [tags]
    """
    parts = [p.strip() for p in line.split("|")]

    # Extracting with defaults in case a line is incomplete
    title = parts[0] if len(parts) > 0 else "Untitled"
    date_val = parts[1] if len(parts) > 1 else "2026-01-01"
    image_val = parts[2] if len(parts) > 2 else "default.jpg"
    tags_str = parts[3] if len(parts) > 3 else "[]"

    return title, date_val, image_val, tags_str


def generate_post_content(title, date_val, image_val, tags_str):
    """Constructs the full string for the Markdown file."""
    full_date = f"{date_val} {TIME_SUFFIX}"

    return f"""---
layout: post
title: "{title}"
author: "{AUTHOR}"
date:   {full_date}
categories: {CATEGORIES}
image: {image_val}
tags: {tags_str}
---

insert content here

[← Back to Home]({{{{ "/" | relative_url }}}})
"""


def create_files():
    if not os.path.exists(MANIFEST_FILE):
        print(f"Error: {MANIFEST_FILE} not found.")
        return []

    if not os.path.exists(POSTS_DIR):
        os.makedirs(POSTS_DIR)

    created_links = []

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        # Filter out empty lines
        lines = [line.strip() for line in f if line.strip()]

    for line in lines:
        title, date_val, image_val, tags_str = parse_line(line)

        slug = slugify(title)
        filename = f"{date_val}-{slug}.md"
        filepath = os.path.join(POSTS_DIR, filename)

        content = generate_post_content(title, date_val, image_val, tags_str)

        try:
            with open(filepath, "w", encoding="utf-8") as f_out:
                f_out.write(content)

            # Prepare the Liquid relative URL for the summary report
            jekyll_url = f'[{title}]({{{{ "/{slug}" | relative_url }}}})'
            created_links.append(jekyll_url)

            print(f"Generated: {filename}")
        except Exception as e:
            print(f"Failed to create {filename}: {e}")

    return created_links


def main():
    print("--- Batch Jekyll Post Generator (Pipe-Delimited) ---")
    links = create_files()

    if links:
        print("\n--- Generated Relative URLs ---")
        for link in links:
            print(link)
    else:
        print("\nNo files were created. Ensure manifest.txt is populated.")


if __name__ == "__main__":
    main()
