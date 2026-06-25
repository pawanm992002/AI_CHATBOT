#!/usr/bin/env python3
"""Export crawled URLs to a markdown file."""

import asyncio
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "chatbot_db"


async def export_urls(tenant_id: str, crawl_id: str, output_file: str = "guru.md"):
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]

    pages = await db.pages.find(
        {"tenant_id": tenant_id, "crawl_id": crawl_id},
        {"url": 1, "title": 1}
    ).sort("url", 1).to_list(length=10000)

    if not pages:
        print(f"No pages found for tenant={tenant_id}, crawl_id={crawl_id}")
        return

    with open(output_file, "w") as f:
        f.write(f"# Crawled URLs\n\n")
        f.write(f"**Tenant ID:** {tenant_id}\n")
        f.write(f"**Crawl ID:** {crawl_id}\n")
        f.write(f"**Total Pages:** {len(pages)}\n")
        f.write(f"**Exported:** {datetime.utcnow().isoformat()}\n\n")
        f.write("## URLs\n\n")
        for i, page in enumerate(pages, 1):
            url = page.get("url", "")
            title = page.get("title", "No title")
            f.write(f"{i}. [{title}]({url})\n")

    print(f"Exported {len(pages)} URLs to {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python export_urls.py <tenant_id> <crawl_id> [output_file]")
        sys.exit(1)

    tenant_id = sys.argv[1]
    crawl_id = sys.argv[2]
    output = sys.argv[3] if len(sys.argv) > 3 else "guru.md"

    asyncio.run(export_urls(tenant_id, crawl_id, output))
