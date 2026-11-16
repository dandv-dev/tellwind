"""Roles: owner > member > viewer, and outsiders can't see a workspace exists."""

import uuid

import pytest
from sqlalchemy import select

from app import db
from app.models import Invitation

pytestmark = pytest.mark.asyncio
PW = "correct-horse-battery"


async def signup(make_client, name: str):
    c = await make_client()
    email = f"{name}-{uuid.uuid4().hex[:6]}@example.com"
    r = await c.post("/api/auth/signup", json={"email": email, "password": PW, "name": name})
    assert r.status_code == 200, r.text
    return c, email


async def invite_and_join(owner, ws_id: str, member_client, email: str, role: str):
    r = await owner.post(f"/api/workspaces/{ws_id}/invitations", json={"email": email, "role": role})
    assert r.status_code == 200, r.text
    inv_id = r.json()["id"]
    r = await member_client.post(f"/api/invitations/{inv_id}/accept")
    assert r.status_code == 200, r.text


@pytest.fixture
async def team(make_client):
    owner, _ = await signup(make_client, "owner")
    r = await owner.post(
        "/api/workspaces",
        json={"name": "Radar", "subject": "AI developer tools", "topics": [{"name": "MCP"}]},
    )
    assert r.status_code == 200, r.text
    ws = r.json()["id"]
    member, m_email = await signup(make_client, "member")
    viewer, v_email = await signup(make_client, "viewer")
    outsider, _ = await signup(make_client, "outsider")
    await invite_and_join(owner, ws, member, m_email, "member")
    await invite_and_join(owner, ws, viewer, v_email, "viewer")
    return {"ws": ws, "owner": owner, "member": member, "viewer": viewer, "outsider": outsider}


async def test_outsider_gets_404_everywhere(team):
    out, ws = team["outsider"], team["ws"]
    for path in ("", "/members", "/files", "/runs", "/briefs/latest", "/items", "/questions"):
        r = await out.get(f"/api/workspaces/{ws}{path}")
        assert r.status_code == 404, (path, r.status_code)
    r = await out.post(f"/api/workspaces/{ws}/runs")
    assert r.status_code == 404
    r = await out.get("/api/workspaces")
    assert all(w["id"] != ws for w in r.json()["workspaces"])


async def test_anonymous_gets_401(make_client, team):
    anon = await make_client()
    r = await anon.get(f"/api/workspaces/{team['ws']}")
    assert r.status_code == 401


async def test_viewer_reads_but_cannot_change_anything(team):
    v, ws = team["viewer"], team["ws"]
    assert (await v.get(f"/api/workspaces/{ws}/files")).status_code == 200
    assert (await v.get(f"/api/workspaces/{ws}/briefs/latest")).status_code == 200
    files = {"file": ("notes.txt", b"Some notes about MCP adoption in our team.", "text/plain")}
    assert (await v.post(f"/api/workspaces/{ws}/files", files=files)).status_code == 403
    assert (await v.post(f"/api/workspaces/{ws}/runs")).status_code == 403
    r = await v.put(f"/api/workspaces/{ws}/schedule", json={"enabled": True, "time": "07:30"})
    assert r.status_code == 403
    r = await v.post(f"/api/workspaces/{ws}/invitations", json={"email": "x@example.com", "role": "viewer"})
    assert r.status_code == 403


async def test_member_uploads_and_schedules_but_cannot_manage_people_or_settings(team):
    m, ws = team["member"], team["ws"]
    files = {"file": ("notes.txt", b"Our pilot of MCP servers went well and we plan to expand it.", "text/plain")}
    r = await m.post(f"/api/workspaces/{ws}/files", files=files)
    assert r.status_code == 200, r.text
    file_id = r.json()["id"]
    r = await m.put(f"/api/workspaces/{ws}/schedule", json={"enabled": False, "time": "07:30"})
    assert r.status_code == 200, r.text
    assert (await m.patch(f"/api/workspaces/{ws}", json={"name": "Mine now"})).status_code == 403
    r = await m.put(f"/api/workspaces/{ws}/topics", json={"topics": [{"name": "Other"}]})
    assert r.status_code == 403
    r = await m.post(f"/api/workspaces/{ws}/invitations", json={"email": "x@example.com", "role": "viewer"})
    assert r.status_code == 403
    # Everyone in the workspace can download what a member uploaded.
    r = await team["viewer"].get(f"/api/workspaces/{ws}/files/{file_id}/download")
    assert r.status_code == 200
    assert b"pilot of MCP" in r.content
    # ...but not someone outside it.
    r = await team["outsider"].get(f"/api/workspaces/{ws}/files/{file_id}/download")
    assert r.status_code == 404


async def test_owner_changes_roles_and_last_owner_is_protected(team):
    o, ws = team["owner"], team["ws"]
    members = (await o.get(f"/api/workspaces/{ws}/members")).json()["members"]
    me = next(x for x in members if x["role"] == "owner")
    viewer = next(x for x in members if x["role"] == "viewer")
    r = await o.patch(f"/api/workspaces/{ws}/members/{viewer['id']}", json={"role": "member"})
    assert r.status_code == 200
    r = await o.patch(f"/api/workspaces/{ws}/members/{me['id']}", json={"role": "viewer"})
    assert r.status_code == 400
    assert r.json()["detail"] == "last_owner"


async def test_invitation_only_works_for_the_invited_email(make_client, team):
    o, ws = team["owner"], team["ws"]
    r = await o.post(f"/api/workspaces/{ws}/invitations", json={"email": "sara@example.com", "role": "viewer"})
    inv_id = r.json()["id"]
    # The outsider has the link (the id/token) but a different email.
    r = await team["outsider"].post(f"/api/invitations/{inv_id}/accept")
    assert r.status_code == 404
    async with db.SessionLocal() as s:
        inv = (await s.execute(select(Invitation).where(Invitation.id == inv_id))).scalar_one()
        assert inv.status == "pending"


async def test_members_see_no_invitation_list(team):
    r = await team["member"].get(f"/api/workspaces/{team['ws']}/members")
    assert r.json()["invitations"] == []
    r = await team["owner"].get(f"/api/workspaces/{team['ws']}/members")
    assert len(r.json()["invitations"]) == 0  # both invites were accepted


async def test_member_starts_a_run_and_everyone_sees_who_started_it(team):
    m, ws = team["member"], team["ws"]
    r = await m.post(f"/api/workspaces/{ws}/runs")
    assert r.status_code == 200, r.text
    assert r.json()["by"] == "member"
    runs = (await team["viewer"].get(f"/api/workspaces/{ws}/runs")).json()["runs"]
    assert runs[0]["by"] == "member"
