#!/usr/bin/env python3
"""Publish the marketing dashboard to Cloudflare.

Syncs reports/*.md and brand/*.md into dashboard/public/content/, writes the
manifest the page reads, then deploys the assets-only worker with wrangler
(same account/pattern as is1-coverage-dashboard).

Usage:
    python3 publish.py             # sync + deploy
    python3 publish.py --dry-run   # sync only, skip the deploy
"""

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTENT = HERE / "dashboard" / "public" / "content"


def title_of(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"#+\s+(.*)", line.strip())
        if m:
            return m.group(1)
    return path.stem.replace("-", " ").replace("_", " ")


def sync(src_dir: Path, dest_name: str) -> list:
    dest = CONTENT / dest_name
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("*.md"):
        old.unlink()
    entries = []
    for f in sorted(src_dir.glob("*.md")) if src_dir.exists() else []:
        shutil.copy2(f, dest / f.name)
        entries.append({
            "file": f.name,
            "title": title_of(f),
            "modified": datetime.fromtimestamp(f.stat().st_mtime)
                                .strftime("%Y-%m-%d %H:%M"),
        })
    return entries


def main():
    manifest = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "reports": sync(HERE / "reports", "reports"),
        "brand": sync(HERE / "brand", "brand"),
    }
    (CONTENT / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"synced {len(manifest['reports'])} reports, "
          f"{len(manifest['brand'])} brand assets")

    if "--dry-run" in sys.argv:
        print("dry run — skipping deploy")
        return
    subprocess.run(["npx", "wrangler", "deploy"],
                   cwd=HERE / "dashboard", check=True)


if __name__ == "__main__":
    main()
