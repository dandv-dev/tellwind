"""The three made-up documents the demo team "uploaded".

They are written to agree with each other and with the period's news: a
leadership survey (early November), an analyst note arguing app builders are
cooling (9 Nov) and the team's notes from an MCP pilot (12 Nov).
"""

from pathlib import Path

SURVEY_TITLE = "Engineering leadership survey: AI developer tooling, Q4 2026"
SURVEY = [
    ("h", SURVEY_TITLE),
    ("p", "Prepared by the DevTools Radar team. Fieldwork 20-31 October 2026. 46 engineering leads at companies with 50-2,000 engineers responded. This is an internal summary; percentages are of respondents."),
    ("h2", "Headline findings"),
    ("p", "Coding agents moved from curiosity to budget line. 61% of teams now run at least one coding agent on real tickets, up from 38% when we asked the same question in Q2. Most use them for well-scoped maintenance work: dependency upgrades, test backfills and small refactors. 22% let agents open pull requests without a human starting the task."),
    ("p", "AI code review has plateaued. 72% of teams already use an AI reviewer on pull requests, almost unchanged from 70% in Q2, and only 9% plan to expand it next quarter. The most common complaint is noise: reviewers that comment on every PR train people to ignore them."),
    ("p", "Terminal and CLI agents are the fastest-growing interface among platform teams. 41% of platform and infrastructure teams use a command-line agent daily, compared with 19% of product teams. Respondents like that CLI agents fit existing scripts and CI jobs."),
    ("h2", "Where interest is growing"),
    ("p", "AI test generation is the area most respondents plan to try next (48%). Teams want agents that write and maintain end-to-end tests, and several named flaky-test triage as the job they would hand over first."),
    ("p", "Model Context Protocol (MCP) came up unprompted in 14 free-text answers, mostly as the way teams plan to connect agents to internal systems such as ticketing, feature flags and observability. Security review of MCP servers is the main blocker."),
    ("h2", "Where interest is flat or falling"),
    ("p", "Local and open-weight coding models: interest is high (55% say they are evaluating) but only 12% run one in production, the same as Q2. Cost and privacy are the reasons to look; quality on large codebases is the reason they stop."),
    ("p", "Prompt-to-app builders: 30% of respondents had tried one for internal tools in Q2; only 17% still use one. Several said the apps were quick to start but hard to maintain once requirements changed."),
    ("h2", "What we will watch"),
    ("p", "Whether agent pull requests keep their acceptance rate as volume grows (respondents report 58% merged without major changes), whether AI review vendors can cut noise, and whether MCP security tooling matures enough to unblock internal pilots."),
]

APP_BUILDERS_TITLE = "Analyst note: prompt-to-app builders are cooling off"
APP_BUILDERS = [
    ("h", APP_BUILDERS_TITLE),
    ("p", "DevTools Radar research note, 9 November 2026. Author: Jonas Lindqvist."),
    ("h2", "Summary"),
    ("p", "Vibe coding and prompt-to-app builders had the strongest hype of any AI developer tool category in the first half of the year. Our view is that the category is now cooling off: new signups are flattening, retention is weak, and buyers are shifting budget towards coding agents that work inside existing codebases."),
    ("h2", "What we see"),
    ("p", "Retention is the core problem. Usage data shared with us by two vendors under NDA shows fewer than one in four projects created in Q3 was still being edited after 30 days. Teams build a prototype quickly and then hit a wall when they need authentication, data migrations or a second developer."),
    ("p", "Signups have flattened. Public traffic estimates for the five best-known app builders were flat to down between August and October, after doubling in the first half. Discounting has increased: three vendors now offer annual plans at 40% or more off list price."),
    ("p", "Our own leadership survey points the same way: the share of engineering leads still using an app builder for internal tools fell from 30% to 17% between Q2 and Q4."),
    ("h2", "What would change our mind"),
    ("p", "A clear story for maintaining generated apps over time, for example builders that export clean code into a normal repository and keep working with it, or enterprise deals that show retention past 90 days."),
    ("h2", "Recommendation"),
    ("p", "Treat vibe coding and app builders as a cooling topic for the next quarter. Keep tracking it for consolidation news (acquisitions, shutdowns) rather than new launches."),
]

MCP_NOTES = """MCP pilot notes - platform team
Updated 12 November 2026

Context
We ran a three-week pilot connecting our coding agents to internal systems through Model Context Protocol (MCP) servers: Jira, our feature-flag service and the read-only observability API.

What worked
- Agents with the Jira MCP server closed 34 small tickets end to end during the pilot, against 11 in the three weeks before without it.
- Setting up a new MCP server took about half a day once the first one was done. Most vendors we use now ship an official MCP server, so we wrote only one ourselves.
- Developers liked that the same servers work in both the IDE and the CLI agent.

What worried security
- Two servers we tested exposed write tools by default. Security asked for an allow-list of tools per server before any wider rollout.
- Tokens were stored in plain config files on laptops in the first week. We moved them to the secrets manager.
- Prompt injection through ticket descriptions is a real risk: an agent read a ticket that told it to change a feature flag. It asked for confirmation, but only because we had turned confirmations on.

Decision
Security signed off on a wider rollout with the allow-list and confirmations required. We plan to connect three more systems in December. Our view: MCP adoption is accelerating across the vendors we use, and the security tooling is catching up.
"""


def write_pdf(path: Path, blocks) -> None:
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_margins(20, 20, 20)
    pdf.add_page()
    for kind, text in blocks:
        if kind == "h":
            pdf.set_font("Helvetica", "B", 16)
            pdf.multi_cell(0, 8, text)
            pdf.ln(3)
        elif kind == "h2":
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(0, 7, text)
            pdf.ln(1)
        else:
            pdf.set_font("Helvetica", "", 10.5)
            pdf.multi_cell(0, 5.5, text)
            pdf.ln(2)
    pdf.output(str(path))


def write_docx(path: Path, blocks) -> None:
    import docx

    d = docx.Document()
    for kind, text in blocks:
        if kind == "h":
            d.add_heading(text, level=1)
        elif kind == "h2":
            d.add_heading(text, level=2)
        else:
            d.add_paragraph(text)
    d.save(str(path))


def build(out_dir: Path) -> list[tuple[str, str]]:
    """Write the files; returns [(date, filename)] in upload order."""
    out_dir.mkdir(parents=True, exist_ok=True)
    write_pdf(out_dir / "Engineering leadership survey Q4 2026.pdf", SURVEY)
    write_docx(out_dir / "Analyst note - app builders cooling.docx", APP_BUILDERS)
    (out_dir / "MCP pilot notes.txt").write_text(MCP_NOTES, encoding="utf-8")
    return [
        ("2026-11-04", "Engineering leadership survey Q4 2026.pdf"),
        ("2026-11-09", "Analyst note - app builders cooling.docx"),
        ("2026-11-12", "MCP pilot notes.txt"),
    ]
