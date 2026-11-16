"""Daily schedule.

A free Render instance sleeps after 15 idle minutes, so an in-process timer
alone would miss runs. Three things cover it:

* an in-process loop checks every few minutes while the instance is awake;
* the same check runs at startup, so a sleeping instance catches up on wake;
* ``POST /api/cron/tick`` (called by a GitHub Actions schedule) wakes it.

``run_due`` is idempotent per day: ``last_scheduled_on`` is set before the
run starts, so overlapping triggers can't start a workspace twice.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, update

from . import db as dbmod
from .agent import runner
from .models import Workspace, utcnow

log = logging.getLogger("tellwind.scheduler")
INTERVAL_SECONDS = 300


async def run_due() -> list[str]:
    now = utcnow()
    today = now.date()
    hhmm = now.strftime("%H:%M")
    started: list[str] = []
    async with dbmod.SessionLocal() as s:
        due = list(
            (
                await s.execute(
                    select(Workspace.id).where(
                        Workspace.schedule_enabled.is_(True),
                        Workspace.schedule_time <= hhmm,
                        (Workspace.last_scheduled_on.is_(None)) | (Workspace.last_scheduled_on < today),
                    )
                )
            ).scalars()
        )
        for wid in due:
            # Claim the day atomically; another trigger may have got there first.
            res = await s.execute(
                update(Workspace)
                .where(
                    Workspace.id == wid,
                    (Workspace.last_scheduled_on.is_(None)) | (Workspace.last_scheduled_on < today),
                )
                .values(last_scheduled_on=today)
            )
            await s.commit()
            if res.rowcount:
                started.append(wid)
    for wid in started:
        await runner.start_run(wid, trigger="schedule", as_of=today)
        log.info("scheduled run started for %s", wid)
    return started


async def loop() -> None:
    await asyncio.sleep(20)  # let startup (seeding) finish first
    while True:
        try:
            await run_due()
        except Exception:  # noqa: BLE001
            log.exception("scheduler tick failed")
        await asyncio.sleep(INTERVAL_SECONDS)
