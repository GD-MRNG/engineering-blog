import os
import re

# --- Global Constants ---
AUTHOR = "Glenn Lum"
CATEGORIES = "journal"
TIME_SUFFIX = "11:00:00 +0800"
POSTS_DIR = "../_posts"


def slugify(text):
    """Converts title to a URL-friendly slug for the filename."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-")


def create_post():
    print("--- Jekyll Post Generator (Metadata Only) ---")

    # 1. Gather Inputs
    title = input("Enter Title: ").strip()
    date_str = input("Enter Date (YYYY-MM-DD): ").strip()
    tags_input = input("Enter Tags (comma separated): ").strip()

    # 2. Process Tags
    # Clean up tags into a list for YAML and a formatted string for the body
    tag_list = [t.strip() for t in tags_input.split(",") if t.strip()]
    formatted_tags_line = f"[{', '.join(tag_list)}]"
    yaml_tags = f"[{', '.join(tag_list)}]"

    # 3. Prepare File Metadata
    slug = slugify(title)
    filename = f"{date_str}-{slug}.md"
    filepath = os.path.join(POSTS_DIR, filename)
    full_date = f"{date_str} {TIME_SUFFIX}"

    # 4. Construct File Content
    # The body now only contains the tags wrapped in backticks
    file_template = f"""---
layout: post
title: "{title}"
author: "{AUTHOR}"
date:   {full_date}
categories: {CATEGORIES}
tags: {yaml_tags}
---

`{formatted_tags_line}`
"""

    # 5. Write to File
    try:
        # Ensure the _posts directory exists relative to the script
        if not os.path.exists(POSTS_DIR):
            os.makedirs(POSTS_DIR)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(file_template)

        print(f"\n[Success] Post created: {filepath}")
    except Exception as e:
        print(f"\n[Error] Could not write file: {e}")


if __name__ == "__main__":
    create_post()
