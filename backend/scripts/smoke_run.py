"""Dev smoke test: one real run on a throwaway SQLite workspace."""
import asyncio, json, os, sys
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import db as dbmod

async def main():
    dbmod.configure("sqlite+aiosqlite:///./data/smoke.db")
    await dbmod.create_all()
    from app.models import Workspace, Topic, Run
    from app.agent import runner
    async with dbmod.SessionLocal() as s:
        ws = Workspace(name="Smoke", subject="AI developer tools")
        s.add(ws); await s.flush()
        for i,(n,d) in enumerate([("Coding agents","Autonomous AI agents that write and change code"),
                                  ("Model Context Protocol","MCP servers and tool protocols for LLMs"),
                                  ("AI code review","AI tools that review pull requests")]):
            s.add(Topic(workspace_id=ws.id, name=n, description=d, position=i))
        await s.commit()
        wid = ws.id
    r = await runner.start_run(wid, trigger="manual", as_of=date(2026,11,15))
    while True:
        await asyncio.sleep(3)
        async with dbmod.SessionLocal() as s:
            run = await s.get(Run, r.id)
            print(run.status, [(st['key'], st['status'], st.get('message','')) for st in run.steps if st['status']!='pending'][-1:], round(run.cost_usd,4), flush=True)
            if run.status in ("succeeded","failed"):
                print(run.error[:2000]); 
                for st in run.steps: print(st['key'], st.get('message'), {k:v for k,v in st.get('detail',{}).items() if k!='calls'})
                break
asyncio.run(main())
