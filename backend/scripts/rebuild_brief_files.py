"""Rebuild the downloadable brief HTML files with the current frontend template.

A brief's HTML file is rendered once, when its run finishes. After the frontend
changes, run `npm run build` in frontend/ and then this script so existing briefs
download in the new look too. The brief data itself is not touched.

    python scripts/rebuild_brief_files.py            # every workspace
    python scripts/rebuild_brief_files.py <ws_id>    # one workspace
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import select  # noqa: E402

from app import db as dbmod  # noqa: E402
from app.agent import artifacts  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import Brief, File  # noqa: E402


async def main(workspace_id: str | None) -> None:
    tpl = get_settings().static_dir / "brief-template.html"
    if not tpl.exists():
        sys.exit(f"No template at {tpl}. Run `npm run build` in frontend/ first.")
    updated = created = 0
    async with dbmod.SessionLocal() as s:
        q = select(Brief)
        if workspace_id:
            q = q.where(Brief.workspace_id == workspace_id)
        for b in (await s.execute(q)).scalars():
            body = artifacts.brief_html(b.data).encode("utf-8")
            f = (
                await s.execute(
                    select(File).where(
                        File.workspace_id == b.workspace_id, File.kind == "brief", File.brief_date == b.date
                    )
                )
            ).scalars().first()
            if f is None:
                f = artifacts.make_file("brief", f"brief-{b.date.isoformat()}.html", "text/html; charset=utf-8", "")
                f.workspace_id, f.run_id, f.brief_date, f.created_at = b.workspace_id, b.run_id, b.date, b.created_at
                s.add(f)
                created += 1
            else:
                updated += 1
            f.data, f.size = body, len(body)
        await s.commit()
    print(f"brief files rebuilt: {updated} updated, {created} created")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
