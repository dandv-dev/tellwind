"""Every conclusion must point at something real in the workspace."""

import asyncio
from datetime import date

from app.agent import companies, llm, narrate
from app.agent.classify import verify_quote
from app.agent.scoring import Point, score_topic
from app.api import qa


def test_verbatim_quote_is_accepted():
    text = "During the pilot, agents with the Jira MCP server closed 34 small tickets end to end."
    assert verify_quote("agents with the Jira MCP server closed 34 small tickets", "Pilot notes", text)
    # Typographic quotes and case don't matter.
    assert verify_quote("“During the pilot, agents with the jira MCP server”", "", text)


def test_paraphrased_quote_is_rejected():
    text = "During the pilot, agents with the Jira MCP server closed 34 small tickets end to end."
    assert not verify_quote("Agents closed dozens of Jira tickets on their own", "", text)
    assert not verify_quote("short", "", text)


def test_elided_quote_needs_every_part_to_be_real():
    text = "Adoption grew fast in October. Several teams then paused their rollouts because of cost."
    assert verify_quote("Adoption grew fast ... paused their rollouts", "", text)
    assert not verify_quote("Adoption grew fast ... abandoned the tool", "", text)


def _topic(n_ev: int = 3) -> narrate.TopicInput:
    pts = [Point(f"i{k}", date(2026, 11, 16 - k), 0.9, 1, f"s{k}.com") for k in range(6)]
    ev = [
        narrate.EvidenceView(f"ev-real-{k}", f"i{k}", f"Title {k}", f"s{k}.com", "2026-11-16", 1, 0.9, "q", "n", False)
        for k in range(n_ev)
    ]
    return narrate.TopicInput("topic-1", "MCP", "", score_topic(pts, date(2026, 11, 16)), "steady", ev)


def test_narrator_citations_are_mapped_and_invented_ones_dropped(monkeypatch):
    async def fake_structured(meter, **kw):
        return {
            "headline": "MCP is moving.",
            "topics": [
                {
                    "topic": "T1",
                    "summary": "s",
                    "watch": "w",
                    "points": [
                        {"text": "Real point (E1).", "sources": ["E1", "[E2]"]},
                        {"text": "Made-up point.", "sources": ["E9", "item-123"]},
                        {"text": "Coverage up 20% in 14 days. [E2, E3]", "sources": ["E2", "E3"]},
                    ],
                }
            ],
        }

    monkeypatch.setattr(narrate.llm, "structured", fake_structured)
    _, out, stats = asyncio.run(narrate.narrate(llm.Meter(), "AI dev tools", [_topic()], [], False))
    t = out["topic-1"]
    assert t["validated"] is True
    assert t["points"] == [
        {"text": "Real point.", "sources": ["ev-real-0", "ev-real-1"]},
        {"text": "Coverage up 20% in 14 days.", "sources": ["ev-real-1", "ev-real-2"]},
    ]
    assert stats["dropped_citations"] == 2
    assert stats["dropped_points"] == 1


def test_narrator_falls_back_to_template_when_nothing_validates(monkeypatch):
    async def fake_structured(meter, **kw):
        return {"headline": "", "topics": [{"topic": "T1", "summary": "", "watch": "", "points": [{"text": "x", "sources": ["E42"]}]}]}

    monkeypatch.setattr(narrate.llm, "structured", fake_structured)
    _, out, stats = asyncio.run(narrate.narrate(llm.Meter(), "AI dev tools", [_topic()], [], False))
    t = out["topic-1"]
    assert t["validated"] is False
    assert t["points"] and all(set(p["sources"]) <= {"ev-real-0", "ev-real-1", "ev-real-2"} for p in t["points"])
    assert stats["fallback_topics"] == ["MCP"]


def test_answer_claims_without_a_valid_source_are_dropped():
    claims = [
        {"text": "Backed.", "refs": [1, 2]},
        {"text": "Partly backed.", "refs": [2, 99]},
        {"text": "Not backed.", "refs": [7]},
        {"text": "No refs.", "refs": []},
    ]
    out = qa.validate_claims(claims, {1, 2, 3})
    assert out == [{"text": "Backed.", "refs": [1, 2]}, {"text": "Partly backed.", "refs": [2]}]


def test_web_answer_sentences_cite_their_pages_and_uncited_ones_are_dropped():
    t = (
        "Maxon ships an MCP server. ([maxon.net](https://maxon.net/a?utm_source=openai)) "
        "ObservePoint cut onboarding by 80%. ([op.com](https://op.com/b)) "
        "This sentence has no source."
    )
    cites = [
        {"url": "https://maxon.net/a?utm_source=openai", "title": "Maxon", "start": t.index("([maxon"), "end": t.index("openai))") + 8},
        {"url": "https://op.com/b", "title": "OP", "start": t.index("([op"), "end": t.index("/b))") + 4},
    ]
    claims, sources = qa.web_claims(t, cites, first_ref=4)
    assert claims == [
        {"text": "Maxon ships an MCP server.", "refs": [4]},
        {"text": "ObservePoint cut onboarding by 80%.", "refs": [5]},
    ]
    assert [s["url"] for s in sources] == ["https://maxon.net/a", "https://op.com/b"]
    assert all(s["kind"] == "web" for s in sources)


def test_answer_sources_are_renumbered_in_citation_order():
    claims = [{"text": "a", "refs": [5, 2]}, {"text": "b", "refs": [2]}]
    sources = [{"ref": r, "kind": "workspace", "title": str(r)} for r in (1, 2, 5)]
    c, s = qa.renumber(claims, sources)
    assert c == [{"text": "a", "refs": [1, 2]}, {"text": "b", "refs": [2]}]
    assert [(x["ref"], x["title"]) for x in s] == [(1, "5"), (2, "2")]


def test_company_spellings_collapse_to_one():
    assert companies.norm_key("Stripe") == companies.norm_key("Stripe, Inc.") == companies.norm_key("stripe.com")
    assert companies.norm_key("The Anthropic PBC") == companies.norm_key("Anthropic")
    known = {companies.norm_key("Informa TechTarget"): "c1"}
    assert companies.resolve("Informa Tech Target", known) == companies.norm_key("Informa TechTarget")
    assert companies.display_name(["Stripe, Inc.", "Stripe"]) == "Stripe"


def test_short_company_names_are_not_fuzzy_matched():
    known = {companies.norm_key("xAI"): "c1"}
    assert companies.resolve("Arc", known) is None
