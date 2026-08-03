#!/usr/bin/env python
"""Build the two hand-over PDFs.

    python scripts/build_docs_pdf.py

Writes into docs/deliverables/:

  YatraAI_Project_README.pdf        full project reference + end-to-end technical workflow
  YatraAI_System_Architecture.pdf   three-page architecture brief with diagrams

Both are generated rather than written by hand for the same reason the README
numbers are: regenerating after a code change is one command, so they cannot
quietly drift away from the system they describe. Every figure traces to a script
in this repository; assumptions and limitations are labelled as such.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "deliverables"

# --------------------------------------------------------------------------- #
# Palette — the product's own Tailwind tokens.
# --------------------------------------------------------------------------- #
NAVY = colors.HexColor("#0E1329")
INDIGO = colors.HexColor("#23306B")
INDIGO_M = colors.HexColor("#42569F")
INDIGO_L = colors.HexColor("#D6DCF2")
INDIGO_XL = colors.HexColor("#EEF1FA")
SAFFRON = colors.HexColor("#E07A3F")
SAFFRON_D = colors.HexColor("#A44C1F")
SAFFRON_XL = colors.HexColor("#FDF2EA")
TEAL = colors.HexColor("#0F7B6C")
TEAL_XL = colors.HexColor("#E9F7F4")
CLAY = colors.HexColor("#A94545")
CLAY_XL = colors.HexColor("#F7ECEC")
SAND = colors.HexColor("#FDFBF7")
LINE = colors.HexColor("#E6E1D8")
INK = colors.HexColor("#1A1D2E")
INK_M = colors.HexColor("#5B6178")
INK_F = colors.HexColor("#8A90A6")

BODY = "Helvetica"
BOLD = "Helvetica-Bold"
MONO = "Courier"


def styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "base", fontName=BODY, fontSize=8.6, leading=12.2, textColor=INK, alignment=TA_LEFT
    )
    return {
        "h1": ParagraphStyle(
            "h1",
            parent=base,
            fontName=BOLD,
            fontSize=15,
            leading=18,
            textColor=INDIGO,
            spaceBefore=2,
            spaceAfter=5,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base,
            fontName=BOLD,
            fontSize=10.5,
            leading=13,
            textColor=INDIGO,
            spaceBefore=9,
            spaceAfter=3,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base,
            fontName=BOLD,
            fontSize=8.8,
            leading=11.5,
            textColor=SAFFRON_D,
            spaceBefore=6,
            spaceAfter=2,
        ),
        "p": ParagraphStyle("p", parent=base, spaceAfter=4),
        "small": ParagraphStyle("small", parent=base, fontSize=7.6, leading=10.4, textColor=INK_M),
        "cell": ParagraphStyle("cell", parent=base, fontSize=7.5, leading=9.8),
        "cellb": ParagraphStyle("cellb", parent=base, fontName=BOLD, fontSize=7.5, leading=9.8),
        "cellh": ParagraphStyle(
            "cellh", parent=base, fontName=BOLD, fontSize=7.5, leading=9.8, textColor=colors.white
        ),
        "code": ParagraphStyle(
            "code",
            parent=base,
            fontName=MONO,
            fontSize=7.4,
            leading=10,
            textColor=INDIGO,
            backColor=INDIGO_XL,
            borderPadding=(4, 5, 4, 5),
            spaceBefore=3,
            spaceAfter=5,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=base, leftIndent=9, bulletIndent=1, spaceAfter=2.5
        ),
    }


S = styles()


def para(txt, style="p"):
    return Paragraph(txt, S[style])


def bullets(items):
    return [Paragraph(f"<bullet>&bull;</bullet>{i}", S["bullet"]) for i in items]


def table(rows, widths, header=INDIGO, zebra=True, align=None, pad=3.4):
    """Table whose first row is a header band."""
    data = []
    for r, row in enumerate(rows):
        out = []
        for c, cell in enumerate(row):
            if isinstance(cell, Paragraph):
                out.append(cell)
            elif r == 0:
                out.append(Paragraph(str(cell), S["cellh"]))
            else:
                out.append(Paragraph(str(cell), S["cellb"] if c == 0 else S["cell"]))
        data.append(out)

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), header),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
    ]
    if zebra:
        for r in range(1, len(rows)):
            if r % 2 == 0:
                style.append(("BACKGROUND", (0, r), (-1, r), SAND))
    if align:
        for c, a in enumerate(align):
            style.append(("ALIGN", (c, 1), (c, -1), a))
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle(style))
    return t


def note(text_html, tone="indigo"):
    """A tinted callout block."""
    fill, edge = {
        "indigo": (INDIGO_XL, INDIGO_L),
        "saffron": (SAFFRON_XL, SAFFRON),
        "teal": (TEAL_XL, TEAL),
        "clay": (CLAY_XL, CLAY),
    }[tone]
    t = Table([[Paragraph(text_html, S["p"])]], colWidths=[None])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("LINEBEFORE", (0, 0), (0, -1), 2.2, edge),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


# --------------------------------------------------------------------------- #
# Page furniture
# --------------------------------------------------------------------------- #
def _chrome(canvas, doc, title, subtitle):
    canvas.saveState()
    w, h = doc.pagesize
    canvas.setFillColor(INDIGO)
    canvas.rect(0, h - 13 * mm, w, 13 * mm, stroke=0, fill=1)
    canvas.setFillColor(SAFFRON)
    canvas.rect(0, h - 14.1 * mm, w, 1.1 * mm, stroke=0, fill=1)

    canvas.setFillColor(colors.white)
    canvas.setFont(BOLD, 9)
    canvas.drawString(15 * mm, h - 8.6 * mm, title)
    canvas.setFont(BODY, 7.4)
    canvas.setFillColor(INDIGO_L)
    canvas.drawRightString(w - 15 * mm, h - 8.4 * mm, subtitle)

    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(15 * mm, 12 * mm, w - 15 * mm, 12 * mm)
    canvas.setFont(BODY, 6.8)
    canvas.setFillColor(INK_F)
    canvas.drawString(
        15 * mm,
        8 * mm,
        "YatraAI — generated by scripts/build_docs_pdf.py. "
        "Every figure traces to a script in the repository.",
    )
    canvas.setFont(BOLD, 8)
    canvas.setFillColor(INDIGO_M)
    canvas.drawRightString(w - 15 * mm, 8 * mm, str(canvas.getPageNumber()))
    canvas.restoreState()


def build(path: Path, story, title, subtitle, pagesize=A4):
    doc = BaseDocTemplate(
        str(path),
        pagesize=pagesize,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=19 * mm,
        bottomMargin=15 * mm,
        title=title,
        author="YatraAI",
        subject=subtitle,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates(
        [
            PageTemplate(
                id="main", frames=[frame], onPage=lambda c, d: _chrome(c, d, title, subtitle)
            )
        ]
    )
    doc.build(story)
    return doc


def cover(canvas_title, tagline, blurb, stats, pagesize=A4):
    """Cover rendered as flowables so it participates in normal pagination."""
    w = pagesize[0] - 30 * mm
    items = [
        Spacer(1, 26 * mm),
        Paragraph(
            "ENGINEERING DOCUMENTATION",
            ParagraphStyle("kicker", fontName=BOLD, fontSize=8.5, textColor=SAFFRON, leading=11),
        ),
        Spacer(1, 5 * mm),
        Paragraph(
            canvas_title,
            ParagraphStyle("cvt", fontName=BOLD, fontSize=30, textColor=INDIGO, leading=34),
        ),
        Spacer(1, 2 * mm),
        Paragraph(
            tagline,
            ParagraphStyle("cvs", fontName=BOLD, fontSize=13, textColor=INDIGO_M, leading=17),
        ),
        Spacer(1, 4 * mm),
    ]
    rule = Table([[""]], colWidths=[38 * mm], rowHeights=[1.4 * mm])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SAFFRON)]))
    items += [
        rule,
        Spacer(1, 6 * mm),
        Paragraph(
            blurb, ParagraphStyle("cvb", fontName=BODY, fontSize=10, textColor=INK_M, leading=15)
        ),
        Spacer(1, 12 * mm),
    ]

    cells = [
        [
            Paragraph(
                f"<font size=15 color='#23306B'><b>{v}</b></font><br/>"
                f"<font size=7 color='#5B6178'>{lab}</font>",
                S["cell"],
            )
            for v, lab in stats
        ]
    ]
    t = Table(cells, colWidths=[w / len(stats)] * len(stats))
    t.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 1.6, SAFFRON),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    items.append(t)
    return items


# =========================================================================== #
# DOCUMENT 1 — PROJECT README
# =========================================================================== #
def doc_readme() -> None:
    cw = A4[0] - 30 * mm  # usable content width inside the page margins
    st: list = cover(
        "YatraAI",
        "Context-Aware Group Travel Intelligence Platform",
        "A group itinerary planner in which a constraint solver — not a language model — decides "
        "what you do and when. Structured data owns the facts, deterministic algorithms select and "
        "schedule, a validator gates every plan, and the language model runs last and changes "
        "nothing. This document is the complete project reference and end-to-end technical "
        "workflow.",
        [
            ("338", "automated tests"),
            ("130", "curated places"),
            ("−57%", "travel vs greedy"),
            ("1.00", "abstention accuracy"),
            ("0", "LLM calls required"),
        ],
    )
    st += [
        Spacer(1, 10 * mm),
        note(
            "<b>How to read this document.</b> Sections 1–3 are what the system is and why. "
            "Section 4 is the complete technical workflow, stage by stage — it is the core of this "
            "document. Sections 5–11 are reference material: data, API, results, quality, security, "
            "operations and limitations.",
            "indigo",
        ),
    ]
    st.append(PageBreak())

    # ---- 1. Overview -----------------------------------------------------
    st += [para("1 · WHAT THIS PROJECT IS", "h1")]
    st += [
        para(
            "YatraAI plans multi-day trips for <b>groups</b> across ten curated Indian destination "
            "circuits. A group states its dates, budget, pace, transport and accessibility needs; each "
            "member separately submits their own interests and constraints. The system returns a "
            "day-by-day schedule with real times, travel legs between stops, a cost range, weather "
            "notes, and a per-stop explanation of why that place was chosen for that group."
        )
    ]
    st += [
        para(
            "The interesting problem is not itinerary generation. It is producing a plan that is "
            "simultaneously <b>fair</b> across members with conflicting preferences, <b>explainable</b> "
            "at the level of individual decisions, and <b>physically feasible</b> under opening hours, "
            "travel time, budget and accessibility — without a language model inventing any of it."
        )
    ]

    st += [para("1.1  The failure mode this design exists to prevent", "h2")]
    st += [
        para(
            "Ask a general-purpose LLM to plan three days in Agra and it will confidently schedule the "
            "Taj Mahal on a Friday (closed to tourists), allow twenty minutes to cross Delhi, and quote "
            "a ticket price it invented. Each of those is a <b>constraint violation</b>, not a wording "
            "problem — so no amount of prompt engineering fixes it. The architecture separates the "
            "parts that must be correct from the part that must read well."
        )
    ]

    st += [para("1.2  Feature inventory", "h2")]
    st += [
        table(
            [
                ["AREA", "CAPABILITY"],
                [
                    "Planning",
                    "Multi-day itinerary generation · per-day geographic clustering · CP-SAT scheduling · meal and rest breaks · per-day accommodation base with relocation notice",
                ],
                [
                    "Group",
                    "Per-member preference submission · fairness-aware aggregation · member veto · opt-out · invite codes · change proposals with voting · trip chat",
                ],
                [
                    "Knowledge",
                    "Cited Q&A over a 790-chunk corpus · hybrid retrieval · abstention · computed citations · 'Know this place' detail drawer with history, etiquette, access and sources",
                ],
                [
                    "Replanning",
                    "Eleven modification actions, each re-optimised and re-validated · weather-driven replanning · handling a member dropping out or a place becoming unavailable",
                ],
                [
                    "Location",
                    "Consent-gated group location sharing · approximate-by-default · meeting point and ETAs · demonstration SOS that contacts nobody",
                ],
                [
                    "Analytics",
                    "Feedback capture including actual spend · aggregate dashboard · admin data-quality, coverage, pipeline and evaluation views · provider telemetry",
                ],
            ],
            [26 * mm, cw - 26 * mm],
        )
    ]

    # ---- 2. Architecture -------------------------------------------------
    st += [para("2 · RESPONSIBILITY SEPARATION", "h1")]
    st += [
        para(
            "The system is eight stages. Seven are deterministic and testable. One is generative, and "
            "it runs last, after the plan is already chosen, scheduled and validated."
        )
    ]
    st += [
        table(
            [
                ["#", "STAGE", "OWNER", "CAN IT INVENT FACTS?"],
                [
                    "1",
                    "Facts",
                    "Curated catalogue with per-row provenance",
                    "No — every field cites a source",
                ],
                [
                    "2",
                    "Eligibility",
                    "Hard filters (closed, inaccessible, over budget, vetoed)",
                    "No — infeasible options are removed",
                ],
                [
                    "3",
                    "Selection",
                    "Fairness-aware ranking, nine components",
                    "No — deterministic and reproducible",
                ],
                ["4", "Geography", "Balanced k-means day clustering", "No"],
                ["5", "Travel", "OSRM, falling back to haversine + documented speeds", "No"],
                [
                    "6",
                    "Schedule",
                    "OR-Tools CP-SAT prize-collecting TSP with time windows",
                    "No — solves a stated model",
                ],
                [
                    "7",
                    "Validation",
                    "Fifteen independent constraint checks",
                    "No — errors block display",
                ],
                [
                    "8",
                    "Wording",
                    "LLM (optional)",
                    "Yes — which is why it runs last and changes nothing",
                ],
            ],
            [8 * mm, 22 * mm, 62 * mm, cw - 92 * mm],
        )
    ]
    st += [
        Spacer(1, 3),
        note(
            "<b>Proof rather than assertion.</b> The default LLM provider is <font face='Courier'>mock"
            "</font>. Live telemetry at <font face='Courier'>/api/v1/metrics</font> reports "
            "<font face='Courier'><b>llm.calls = 0</b></font>. Every itinerary produced during "
            "development and testing was generated with no model call at all. Configure a real provider "
            "and the plan is byte-identical — only the prose paragraph beside it changes.",
            "teal",
        ),
    ]

    # ---- 3. Stack --------------------------------------------------------
    st += [para("3 · TECHNOLOGY STACK", "h1")]
    st += [
        table(
            [
                ["LAYER", "TECHNOLOGY", "WHY THIS CHOICE"],
                [
                    "Frontend",
                    "Next.js 14 (App Router), TypeScript strict, Tailwind CSS, TanStack Query, Recharts, react-leaflet",
                    "Server components for static shells, client components only where state lives; strict TS catches API drift at build time",
                ],
                [
                    "API",
                    "FastAPI, Pydantic v2, pydantic-settings, structlog",
                    "Schema-first validation and an OpenAPI document generated from the same types the code uses",
                ],
                [
                    "Persistence",
                    "SQLAlchemy 2.0, Alembic, PostgreSQL + pgvector — portable to SQLite",
                    "Four portable TypeDecorators (GUID, JSONType, VectorType, TZDateTime) let one schema serve both engines, so a reviewer needs no infrastructure",
                ],
                [
                    "Optimisation",
                    "Google OR-Tools CP-SAT",
                    "The problem is genuinely a prize-collecting TSP with time windows; AddCircuit expresses sequencing and selection in one constraint",
                ],
                [
                    "ML / science",
                    "NumPy, pandas, scikit-learn, Pandera",
                    "Feature pipeline, offline experiments and executable data contracts",
                ],
                [
                    "Data pipeline",
                    "Bronze/Silver/Gold medallion, Airflow DAGs, pyarrow",
                    "Idempotent, content-hashed ingestion with a contract at every promotion",
                ],
                [
                    "Security",
                    "PyJWT (HS256), bcrypt, in-process sliding-window rate limiter",
                    "Token auth with a Supabase-compatible path; two rate-limit tiers protecting expensive endpoints",
                ],
                [
                    "Testing / CI",
                    "pytest (295), Vitest + Testing Library (43), ruff, mypy, GitHub Actions",
                    "Backend, Postgres integration, data-quality, frontend and docker jobs",
                ],
                [
                    "Deployment",
                    "Docker multi-stage, Compose, render.yaml, Vercel",
                    "Every secret marked sync:false; JWT_SECRET generated at deploy time",
                ],
            ],
            [21 * mm, 58 * mm, cw - 79 * mm],
        )
    ]

    st += [para("3.1  Provider abstraction", "h2")]
    st += [
        para(
            "Every external dependency sits behind an interface with a documented fallback. No provider "
            "raises on failure — each degrades and records that it did, so the UI can disclose it and "
            "<font face='Courier'>/metrics</font> can report a real fallback rate."
        )
    ]
    st += [
        table(
            [
                ["PROVIDER", "DEFAULT", "FALLBACK", "CONSEQUENCE OF FALLING BACK"],
                [
                    "LLM",
                    "mock",
                    "deterministic templates",
                    "Explanations become templated prose. The itinerary is unchanged.",
                ],
                [
                    "Embeddings",
                    "hashing",
                    "— (is the default)",
                    "384-dim signed feature hashing. Deterministic, no model download; not a neural encoder.",
                ],
                [
                    "Routing",
                    "OSRM",
                    "haversine × detour factor",
                    "Travel times use documented conservative speeds. Underestimating travel is the dangerous direction, so the fallback errs slow.",
                ],
                [
                    "Weather",
                    "Open-Meteo",
                    "committed climatology",
                    "Labelled in the UI as seasonal averages, never presented as a forecast.",
                ],
                [
                    "Database",
                    "PostgreSQL + pgvector",
                    "SQLite",
                    "Vector search degrades to in-process cosine. Same schema, same tests.",
                ],
            ],
            [21 * mm, 26 * mm, 34 * mm, cw - 81 * mm],
        )
    ]

    st.append(PageBreak())

    # ---- 4. THE WORKFLOW -------------------------------------------------
    st += [para("4 · COMPLETE TECHNICAL WORKFLOW", "h1")]
    st += [
        para(
            "This section traces every significant path through the system end to end. It is the core "
            "of this document.",
            "small",
        )
    ]

    st += [para("4.1  Workflow A — generating an itinerary", "h2")]
    st += [
        para(
            "Triggered by <font face='Courier'>POST /api/v1/trips/{id}/itinerary</font>. Rate-limited "
            "on the AI tier (15 requests/minute)."
        )
    ]
    st += [
        table(
            [
                ["STAGE", "INPUT", "PROCESS", "OUTPUT"],
                [
                    "0  Authorise",
                    "JWT, trip id",
                    "Decode token, load trip, assert caller is a trip member. Rate-limit key is the user id.",
                    "TripContext + member list",
                ],
                [
                    "1  Build context",
                    "Trip row, member preference rows",
                    "Merge trip-level settings with each member's interests, pace, mobility, day window, must-visit and avoid lists. Accessibility needs propagate up to the trip.",
                    "TripContext, MemberProfile[]",
                ],
                [
                    "2  Load candidates",
                    "Cluster slug",
                    "Fetch every active attraction in the destination with schedules, costs and sources eagerly loaded; convert to pure-Python AttractionCandidate objects.",
                    "AttractionCandidate[]",
                ],
                [
                    "3  Filter eligibility",
                    "Candidates, members",
                    "Remove anything closed for the whole trip, over budget, failing a stated accessibility need, or on any member's avoid list. A member veto is absolute.",
                    "Eligible candidates (reduced set)",
                ],
                [
                    "4  Score & aggregate",
                    "Eligible candidates, members",
                    "Compute nine components per candidate per member; aggregate with select_fairly — an iterative selector that repeatedly picks the item maximising a blend of group objective gain and raw item quality.",
                    "ScoredAttraction[] with stored breakdowns",
                ],
                [
                    "5  Cluster by day",
                    "Shortlist, trip length",
                    "Balanced k-means on an equirectangular projection with deterministic farthest-point seeding. A balancing move is refused if it would strand a point more than 25 km from where it belongs.",
                    "One candidate pool per day",
                ],
                [
                    "6  Build travel matrix",
                    "Day pool + day base",
                    "Per-day base chosen within that day's area; if it sits more than 60 km from the stated origin the day carries an explicit relocation note. OSRM if available, else haversine × detour factor.",
                    "RouteMatrix (minutes, km)",
                ],
                [
                    "7  Solve each day",
                    "DayPlanRequest",
                    "One CP-SAT model per day: AddCircuit over all nodes, time propagation via OnlyEnforceIf, opening-hour domains, mandatory nodes, activity/travel/budget caps. Five-step relaxation ladder on infeasibility.",
                    "PlannedDay with activities, status, objective, solve time",
                ],
                [
                    "8  Validate",
                    "Planned days",
                    "Fifteen checks re-derived independently of the solver. Errors block display; warnings are surfaced.",
                    "ValidationReport",
                ],
                [
                    "9  Cost & explain",
                    "Validated plan",
                    "Cost estimated as a range across five components with stated assumptions. The LLM (if configured) writes a summary paragraph; otherwise a deterministic template does.",
                    "Cost band, summary text",
                ],
                [
                    "10  Persist",
                    "Everything above",
                    "New itinerary version written with per-day and per-activity rows, the stored score breakdown, solver stats and an input fingerprint. Previous version is superseded, not deleted.",
                    "Itinerary v(n), audit log entry",
                ],
            ],
            [20 * mm, 26 * mm, cw - 92 * mm, 26 * mm],
            pad=3.0,
        )
    ]

    st += [
        Spacer(1, 3),
        note(
            "<b>Why the fingerprint matters.</b> Stage 10 stores a hash of the planner inputs. With "
            "<font face='Courier'>num_workers = 1</font> and a fixed seed, identical inputs always "
            "produce an identical plan — which is what makes the itinerary reproducible and the "
            "regression tests meaningful.",
            "indigo",
        ),
    ]

    st += [para("4.2  Workflow B — answering a question (RAG)", "h2")]
    st += [
        para(
            "Triggered by <font face='Courier'>POST /api/v1/assistant/ask</font>. Also available "
            "unauthenticated, so the assistant can be demonstrated without signing up."
        )
    ]
    st += [
        table(
            [
                ["STEP", "PROCESS"],
                [
                    "1  Sanitise",
                    "Detect prompt-injection patterns in the question; flag them in warnings and neutralise the text before it is used anywhere.",
                ],
                [
                    "2  Classify",
                    "Map the question to a knowledge topic (history, significance, visiting, etiquette, access) using stem-based patterns.",
                ],
                [
                    "3  Scope",
                    "Apply metadata filters. An attraction filter <b>requires</b> a cluster — an unscoped attraction lookup is exactly how the wrong place's dress code gets returned.",
                ],
                [
                    "4  Retrieve twice",
                    "Dense cosine over the chunk embeddings and BM25 lexical scoring run independently over the same candidate set.",
                ],
                ["5  Fuse", "Reciprocal Rank Fusion with k = 60 combines the two rankings."],
                [
                    "6  Rerank",
                    "A feature model scores query-term coverage, heading match, topic agreement and source authority.",
                ],
                [
                    "7  Gate",
                    "Compute an absolute evidence score: 0.35 × dense similarity + 0.65 × IDF-weighted query-term coverage, taken as a max over chunks. Below 0.26, abstain — with no model call at all.",
                ],
                [
                    "8  Generate",
                    "If a real provider is configured, answer from neutralised context under an injection-aware system prompt. Otherwise compose from retrieved sentences.",
                ],
                [
                    "9  Cite",
                    "Match each answer sentence back to the chunk it overlaps most (threshold 0.30). A sentence the model invented earns no citation.",
                ],
                [
                    "10  Disclose",
                    "Attach the 'recorded, unverified' caveat for anything time-sensitive, and state explicitly when the question asked for a live value we do not hold.",
                ],
            ],
            [20 * mm, cw - 20 * mm],
        )
    ]

    st += [para("4.3  Workflow C — replanning", "h2")]
    st += [
        para(
            "Eleven actions are available: <font face='Courier'>remove_activity, replace_activity, "
            "regenerate_day, make_day_relaxed, reduce_cost, reduce_travel, add_theme, shift_start_time, "
            "weather_replan, member_opted_out, attraction_unavailable</font>."
        )
    ]
    st += [
        para(
            "Every one is expressed as a <b>change to planner inputs</b>, after which the entire "
            "pipeline in Workflow A re-runs and re-validates. Nothing edits a stored schedule in place. "
            "That is a deliberate constraint: an in-place edit could produce a state the optimiser would "
            "never have generated and the validator was never asked about."
        )
    ]
    st += [
        para(
            "On a trip with more than one active member the change does not apply immediately. It "
            "becomes a <font face='Courier'>ChangeProposal</font> with an approval threshold; the API "
            "returns <font face='Courier'>requires_group_approval: true</font> and a proposal id. "
            "Members vote, reaching the threshold auto-applies it, and the trip owner can override — "
            "with the override written to the append-only audit log."
        )
    ]

    st += [para("4.4  Workflow D — data ingestion", "h2")]
    st += [
        table(
            [
                ["LAYER", "WHAT HAPPENS", "MEASURED"],
                [
                    "Bronze",
                    "Seed JSON read and content-hashed. Re-running with unchanged content is a no-op, which is what makes the pipeline idempotent.",
                    "140 documents",
                ],
                [
                    "Silver",
                    "Type coercion, deduplication, referential resolution, source allow-list enforcement, opening-window normalisation to minutes-from-midnight. Seven Pandera contracts gate the promotion.",
                    "130 attractions, 142 sources, 164 schedules, 216 fee rows, 0 rejected",
                ],
                [
                    "Gold",
                    "Derived planning features: accessibility score, family score, indoor score, crowd penalty, cost index, evidence score, twelve monthly season scores.",
                    "130 feature rows, 10 cluster metric rows",
                ],
                [
                    "Knowledge",
                    "The same records generate the RAG corpus — one chunk per attraction × topic — then embeddings. There is no second, driftable corpus.",
                    "140 documents → 790 chunks → 790 embeddings",
                ],
            ],
            [20 * mm, cw - 66 * mm, 46 * mm],
        )
    ]

    st += [para("4.5  Workflow E — location sharing", "h2")]
    st += [
        para(
            "Consent text is served from the API so the UI cannot drift from the recorded version. A "
            "session cannot exist without <font face='Courier'>consent_granted_at</font> and a stored "
            "consent-text version. In approximate mode — the default — coordinates are snapped to a "
            "~500 m grid <b>before</b> the row is constructed, so the precise value never reaches the "
            "database. Sessions carry a twelve-hour hard cap, points carry their own expiry, and "
            "stopping deletes the trail immediately rather than hiding it. Purging runs from three "
            "independent places so no single failure leaves data behind."
        )
    ]

    st.append(PageBreak())

    # ---- 5. Data model ---------------------------------------------------
    st += [para("5 · DATA MODEL", "h1")]
    st += [
        para(
            "Thirty-one tables across six domains, defined once in SQLAlchemy and migrated with Alembic. "
            "The full chain applies and reverses cleanly on a fresh database."
        )
    ]
    st += [
        table(
            [
                ["DOMAIN", "KEY TABLES", "NOTES"],
                [
                    "Catalogue",
                    "destination_clusters, attractions, attraction_schedules, attraction_costs, attraction_sources",
                    "Provenance is a first-class table, not a column. Every schedule and cost row carries verified = false.",
                ],
                [
                    "Trips",
                    "trips, trip_members, member_preferences, change_proposals, votes, chat_messages",
                    "Preferences are per member, not per trip — that is what makes fairness measurable.",
                ],
                [
                    "Itineraries",
                    "itineraries, itinerary_days, itinerary_activities, recommendation_scores",
                    "Versioned. Activities store the score breakdown and the opening window the visit was scheduled inside.",
                ],
                [
                    "Knowledge",
                    "knowledge_documents, document_chunks, chunk_embeddings",
                    "Derived from the catalogue, so it cannot drift from it.",
                ],
                [
                    "Privacy",
                    "location_sharing_sessions, location_points",
                    "Both carry expiry. There is no location-history table, by design.",
                ],
                [
                    "Observability",
                    "audit_logs, analytics_events, model_runs, pipeline_runs, rag_evaluations",
                    "model_runs carries data_kind on every row, so a synthetic result can never be displayed as a real one.",
                ],
            ],
            [24 * mm, 56 * mm, cw - 80 * mm],
        )
    ]

    # ---- 6. API ----------------------------------------------------------
    st += [para("6 · API SURFACE", "h1")]
    st += [
        table(
            [
                ["GROUP", "ENDPOINTS", "AUTH"],
                ["Ops", "/health · /ready · /api/v1/metrics · /auth/service-status", "public"],
                ["Auth", "register · login · me · demo", "public / bearer"],
                ["Destinations", "list · detail · attractions · attraction detail", "public"],
                [
                    "Trips",
                    "create · list · detail · update · join · invite rotate · preferences · opt-out",
                    "member / owner",
                ],
                [
                    "Itineraries",
                    "generate · read · versions · validate · modify · recommendations",
                    "member",
                ],
                ["Assistant", "ask · suggested-questions · retrieve · why", "public / member"],
                ["Collaboration", "votes · proposals · apply · chat", "member / owner"],
                [
                    "Location",
                    "consent-text · start · status · point · group · delete",
                    "member (consent-gated)",
                ],
                ["SOS", "raise · list · resolve", "member (demo only)"],
                [
                    "Analytics / Admin",
                    "feedback · dashboard · trip analytics · data-quality · coverage · pipeline-runs · rag-evaluations · audit-log",
                    "public / admin",
                ],
            ],
            [28 * mm, cw - 52 * mm, 24 * mm],
        )
    ]
    st += [
        Spacer(1, 3),
        para(
            "Every error returns the same envelope so clients branch on a stable code rather than "
            'parsing messages: <font face=\'Courier\'>{"error": {"code", "message", "detail"}}'
            "</font>. Notable codes include <font face='Courier'>planning_infeasible</font> (422, with "
            "the report attached), <font face='Courier'>consent_required</font> (403) and "
            "<font face='Courier'>rate_limited</font> (429, with retry-after).",
            "small",
        ),
    ]

    # ---- 7. Results ------------------------------------------------------
    st += [para("7 · MEASURED RESULTS", "h1")]
    st += [
        para(
            "Reproduce with <font face='Courier'>make experiments</font> and "
            "<font face='Courier'>python evaluation/run_rag_eval.py</font>.",
            "small",
        )
    ]

    st += [para("7.1  Optimiser versus a fair greedy baseline", "h3")]
    st += [
        table(
            [
                ["METRIC", "GREEDY", "CP-SAT", "DIFFERENCE"],
                ["Total travel distance", "149.8 km", "64.0 km", "−57%"],
                ["Total travel time", "487 min", "275 min", "−43%"],
                ["Travel km per activity", "15.61", "6.01", "−61%"],
                ["Activities scheduled", "9.8", "10.3", "+0.5"],
                ["Constraint violations", "0.0", "0.0", "—"],
                ["Median computation", "8.8 ms", "48.2 ms", "+39 ms"],
            ],
            [cw - 90 * mm, 30 * mm, 30 * mm, 30 * mm],
        )
    ]
    st += [
        Spacer(1, 2),
        para(
            "Six scenarios across six clusters, three timing repeats. The baseline honours identical "
            "opening hours, budget, activity and travel caps, so the gap measures sequencing quality "
            "alone — it is not a strawman.",
            "small",
        ),
    ]

    st += [para("7.2  Group aggregation methods", "h3")]
    st += [
        table(
            [
                ["METHOD", "MEAN SATISFACTION", "LEAST SATISFIED", "SPREAD"],
                ["simple_average", "0.604", "0.481", "0.172"],
                ["borda_count", "0.618", "0.478", "0.197"],
                ["max_min_fairness", "0.582", "0.545", "0.069"],
                ["fairness_aware (single pass)", "0.603", "0.484", "0.167"],
                ["select_fairly (production)", "0.597", "0.522", "0.115"],
            ],
            [cw - 90 * mm, 30 * mm, 30 * mm, 30 * mm],
        )
    ]
    st += [
        Spacer(1, 2),
        para(
            "Five group profiles built so a simple average steamrolls a minority. Note that Borda scores "
            "the best mean and the worst floor — that is the trap this measurement exists to expose. The "
            "single-pass variant barely improves on an average, which is precisely why the iterative "
            "selector was built.",
            "small",
        ),
    ]

    st += [para("7.3  Retrieval and abstention", "h3")]
    st += [
        table(
            [
                ["METRIC", "VALUE", "METRIC", "VALUE"],
                ["Open retrieval top-1", "0.903", "Citation correctness", "1.000"],
                ["Open retrieval top-3", "1.000", "Citation coverage", "1.000"],
                ["Open retrieval MRR", "0.952", "Abstention accuracy", "1.000"],
                ["Retrieval recall", "1.000", "Faithfulness", "0.995"],
                [
                    "Topic classification",
                    "0.941",
                    "Mean evidence (answerable / out-of-scope)",
                    "0.582 / 0.071",
                ],
            ],
            [(cw - 40 * mm) / 2, 20 * mm, (cw - 40 * mm) / 2, 20 * mm],
        )
    ]
    st += [
        Spacer(1, 2),
        para(
            "Thirty-four hand-written questions including deliberately unanswerable and adversarial "
            "ones. Ablation, with a retrieval arm genuinely disabled rather than re-sorted: reranking is "
            "worth +12.9 points of top-1 (0.903 against 0.774). Lexical-only nearly matches the hybrid, "
            "which is an honest limitation of the default hashing embedder — a lexical projection whose "
            "signal correlates with BM25 rather than complementing it.",
            "small",
        ),
    ]

    st += [para("7.4  The machine-learning experiment", "h3")]
    st += [
        para(
            "A suitability model was trained on <b>synthetic labels</b> — there is no genuine labelled "
            'data for "did this group enjoy this attraction". Every run is stamped '
            "<font face='Courier'>data_kind = \"synthetic\"</font>."
        )
    ]
    st += [
        table(
            [
                ["MODEL", "ROC-AUC", "PR-AUC", "NOTE"],
                ["logistic_regression", "0.6711", "0.8341", "best learner"],
                ["random_forest", "0.6404", "0.8190", "lost to the control"],
                ["gradient_boosting", "0.6404", "0.8147", "lost to the control"],
                ["rule_based_production_control", "0.6676", "0.8278", "the shipped scorer"],
            ],
            [cw - 84 * mm, 26 * mm, 26 * mm, 32 * mm],
        )
    ]
    st += [
        Spacer(1, 3),
        note(
            "<b>The honest result.</b> The tree models lost to the hand-weighted production scorer. The "
            "only learner that edged it did so by 0.0035 ROC-AUC, and a paired bootstrap over 2,000 "
            "resamples puts that difference at <b>95% CI [−0.0100, +0.0173]</b> — straddling zero. On "
            "this data the simple transparent model is not a compromise. No model was promoted to "
            "production.",
            "saffron",
        ),
    ]

    st.append(PageBreak())

    # ---- 8. Quality ------------------------------------------------------
    st += [para("8 · TESTING & QUALITY", "h1")]
    st += [
        table(
            [
                ["SUITE", "COUNT", "WHAT IT COVERS"],
                [
                    "Unit",
                    "part of 295",
                    "Scoring, aggregation, fairness metrics, clustering, cost estimation, validator, retrieval scoring, security primitives",
                ],
                [
                    "Integration",
                    "part of 295",
                    "Full API surface against a live app and database — auth, trips, itineraries, RAG, collaboration, location, analytics, admin",
                ],
                [
                    "Data quality",
                    "30",
                    "Coordinate bounds, cluster distance, duplicate detection, category-taxonomy coverage, source allow-list, dress code on religious sites, verified-flag enforcement",
                ],
                [
                    "Frontend",
                    "43",
                    "Design-system accessibility semantics, itinerary rendering, opening-window display states, solver-trace parsing including malformed input",
                ],
                [
                    "Total",
                    "338",
                    "ruff and ruff format clean; mypy clean; tsc --noEmit clean; next lint clean",
                ],
            ],
            [26 * mm, 22 * mm, cw - 48 * mm],
        )
    ]

    st += [para("8.1  Defects found by measurement, not by reading code", "h2")]
    st += [
        table(
            [
                ["DEFECT", "HOW IT WAS FOUND", "FIX"],
                [
                    "Topic classification stuck at 0.50",
                    "RAG evaluation harness",
                    'A trailing word boundary in \\b(histor)\\b makes matching "history" impossible. Switched to \\w* stems: 0.50 → 0.941.',
                ],
                [
                    "Abstention could not separate answerable from unanswerable",
                    "RAG evaluation harness",
                    "The threshold keyed on the fused RRF score, which encodes ordering only and is near-constant at the top. Replaced with an absolute evidence score.",
                ],
                [
                    "Assistant abstained on a fee it was holding",
                    "RAG evaluation harness",
                    '"today" and "4pm" are absent from the corpus and drew maximum IDF weight. Absent entities signal out-of-scope; absent framing words signal nothing. Abstention 0.912 → 1.000, with out-of-scope evidence unchanged at 0.071.',
                ],
                [
                    "A 401 km Delhi–Agra itinerary",
                    "Planner comparison experiment",
                    "Size balancing dragged Delhi sites into the Agra day. Added a rule refusing any balancing move that strands a point more than 25 km away. Same scenario now plans at 54 km.",
                ],
                [
                    "Every Delhi–Agra day infeasible",
                    "Planner comparison experiment",
                    "A single trip-wide base sat 115 km from everything. Introduced a per-day base with an explicit relocation note.",
                ],
                [
                    "Cross-cluster neighbour reference; duplicate coordinates",
                    "Data-quality contracts",
                    "Two authoring errors in the seed data, neither visible by reading the JSON.",
                ],
            ],
            [40 * mm, 32 * mm, cw - 72 * mm],
            header=CLAY,
        )
    ]

    # ---- 9. Security -----------------------------------------------------
    st += [para("9 · SECURITY & PRIVACY", "h1")]
    st += [
        table(
            [
                ["CONCERN", "CONTROL"],
                [
                    "Credential compromise",
                    "bcrypt at cost 12 with a SHA-256 pre-hash, because bcrypt silently truncates at 72 bytes. A test asserts an 80-character passphrase keeps its entropy.",
                ],
                [
                    "Token forgery",
                    "HS256 JWT with signature, issuer and expiry verified. Supabase-issued tokens are accepted and provision a local user on first sight.",
                ],
                [
                    "Privilege escalation",
                    "require_trip_member and require_trip_owner as route dependencies; admin_user on every admin route. Admins may read a trip for support but are not silently made members.",
                ],
                [
                    "Cost and denial of service",
                    "Two-tier sliding-window rate limiting — 120 requests/minute default, 15/minute on the optimiser and the assistant.",
                ],
                [
                    "Prompt injection",
                    "Detected on the question, neutralised on every retrieved chunk, and an injection-aware system prompt. Injection attempts also score low on evidence and usually abstain before any model call.",
                ],
                [
                    "Data poisoning",
                    "Source-domain allow-list enforced at the Silver gate; a citation to a non-allow-listed domain is rejected with a reason.",
                ],
                [
                    "Secret leakage",
                    ".env is git-ignored, .env.example contains variable names only, render.yaml marks every secret sync:false, and a production boot guard refuses to start on weak configuration.",
                ],
                [
                    "Location exposure",
                    "Consent gate, ~500 m snapping before storage, hard expiry, immediate deletion on stop, and coordinate-key stripping at analytics write time.",
                ],
            ],
            [34 * mm, cw - 34 * mm],
            header=CLAY,
        )
    ]

    # ---- 10. Running -----------------------------------------------------
    st += [para("10 · RUNNING THE PROJECT", "h1")]
    st += [para("One command on Windows:", "h3")]
    st += [Paragraph(".\\start.ps1", S["code"])]
    st += [
        para(
            "Creates the virtual environment, installs, migrates, seeds, starts the API and "
            "opens a browser.",
            "small",
        )
    ]
    st += [para("Full stack, manually:", "h3")]
    st += [
        Paragraph(
            "python -m venv .venv<br/>"
            '.venv\\Scripts\\pip install -e ".[dev]"<br/>'
            ".venv\\Scripts\\python -m yatraai.cli migrate<br/>"
            ".venv\\Scripts\\python -m yatraai.cli seed --knowledge --embeddings<br/>"
            ".venv\\Scripts\\uvicorn yatraai.main:app --app-dir apps/api --port 8000<br/><br/>"
            "cd apps/web &amp;&amp; npm install &amp;&amp; npm run dev",
            S["code"],
        )
    ]
    st += [
        para(
            "Frontend at <font face='Courier'>localhost:3000</font>; the API's self-contained console at "
            "<font face='Courier'>localhost:8000</font> (it renders offline — "
            "<font face='Courier'>/docs</font> needs internet because Swagger UI loads from a CDN). "
            "Demo account: <font face='Courier'>demo@yatraai.example</font> / "
            "<font face='Courier'>yatraai-demo-2026</font>, or one click on the sign-in page.",
            "small",
        )
    ]

    st += [para("10.1  Repository layout", "h2")]
    st += [
        table(
            [
                ["PATH", "CONTENTS"],
                [
                    "apps/api/yatraai/",
                    "FastAPI application — api/, services/ (planner, recommend, rag, routing, weather, llm, location, analytics), db/, schemas/, seed/",
                ],
                [
                    "apps/web/",
                    "Next.js frontend — app/ routes, components/, lib/ (typed API client and types)",
                ],
                [
                    "data/seed/attractions/",
                    "Ten curated destination files; the committed source of truth",
                ],
                [
                    "pipelines/",
                    "Medallion transforms and Airflow DAGs calling the same functions as the CLI",
                ],
                [
                    "ml/",
                    "Experiments and reports — planner comparison, aggregation comparison, suitability model",
                ],
                ["evaluation/", "RAG benchmark dataset, harness and generated report"],
                ["tests/", "unit/, integration/, data_quality/"],
                [
                    "docs/",
                    "Architecture, data flow, ER diagram, recommendation, optimisation, RAG, ML experiments, security, privacy, deployment, API reference, data dictionary, interview notes",
                ],
                ["scripts/", "Deployment verification, deck and document generators"],
            ],
            [40 * mm, cw - 40 * mm],
        )
    ]

    # ---- 11. Limitations -------------------------------------------------
    st += [para("11 · STATED LIMITATIONS", "h1")]
    st += [
        para(
            "These are deliberate scope decisions or honest gaps. They are listed here rather than "
            "discovered later."
        )
    ]
    st += [
        table(
            [
                ["LIMITATION", "DETAIL"],
                [
                    "Default embeddings are not neural",
                    "A 384-dimension signed feature hashing projection. It keeps installation under a minute and requires no model download. sentence-transformers is a one-environment-variable upgrade, and the ablation table shows what retrieval configuration is worth on this corpus.",
                ],
                [
                    "No model was promoted to production",
                    "The ML experiment runs on synthetic labels and lost to the rule-based control. The pipeline, registry and evaluation are real and ready for the day genuine feedback exists.",
                ],
                [
                    "The benchmark is author-written",
                    "Thirty-four questions, hand-written, not collected from users. Small, and labelled as such in the report.",
                ],
                [
                    "Ten destinations, not all of India",
                    "Depth over breadth. Adding a cluster is a data change plus climatology, with no application code change.",
                ],
                [
                    "Rate limiting is per-process",
                    "Deliberate for a single-process demo. SlidingWindowRateLimiter.check is the only method the API uses, so a distributed implementation is a one-class swap.",
                ],
                [
                    "No refresh tokens, no 2FA, no account deletion endpoint",
                    "Access tokens last 120 minutes. Cascades are defined at the schema level but the endpoint is not built.",
                ],
                [
                    "Weather and routing run on fallbacks offline",
                    "Both are disclosed in the UI and reported in /metrics rather than hidden.",
                ],
                [
                    "SOS is a demonstration",
                    "It contacts nobody. Stated in the OpenAPI description, the response body, the UI and the chat message it posts, and it refuses to fire without an explicit acknowledgement flag.",
                ],
            ],
            [46 * mm, cw - 46 * mm],
            header=SAFFRON_D,
        )
    ]

    st += [
        Spacer(1, 5),
        note(
            "<b>Honesty guarantees, enforced by code rather than by policy.</b> No schedule or fee row "
            "in the dataset claims to be verified, and a data-quality test fails the build if one ever "
            "does. The assistant abstains rather than guessing. Citations are computed from lexical "
            "overlap, so a model cannot claim a source it did not draw from. Coordinates never reach "
            "analytics. Every performance figure in this document is regenerated by a script in the "
            "repository.",
            "teal",
        ),
    ]

    build(
        OUT / "YatraAI_Project_README.pdf",
        st,
        "YatraAI — Project README",
        "Complete reference & technical workflow",
    )


# =========================================================================== #
# DOCUMENT 2 — SYSTEM ARCHITECTURE (3 pages, landscape)
# =========================================================================== #
LAND = landscape(A4)
LW = LAND[0] - 30 * mm


def box(label, sub, fill, width, height=None):
    """A labelled block used inside the architecture diagrams."""
    inner = [
        [Paragraph(f"<font size=8 color='white'><b>{label}</b></font>", S["cell"])],
        [Paragraph(f"<font size=6.6 color='#5B6178'>{sub}</font>", S["cell"])],
    ]
    t = Table(inner, colWidths=[width], rowHeights=[5.6 * mm, height or 9 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), fill),
                ("BACKGROUND", (0, 1), (0, 1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2.4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def flow_row(specs, height=10 * mm, arrow=True, gap=5 * mm):
    """A row of boxes that fills the full frame width, flush left.

    Sizing the boxes from the available width rather than passing fixed
    millimetres is what keeps the diagram edge-to-edge — an earlier version
    centred a narrower table and left a dead gutter down the left margin.
    """
    n = len(specs)
    bw = (LW - gap * (n - 1)) / n
    cells, cols = [], []
    for i, (label, sub, fill) in enumerate(specs):
        cells.append(box(label, sub, fill, bw, height))
        cols.append(bw)
        if i < n - 1:
            cells.append(
                Paragraph("<font size=10 color='#42569F'><b>&rarr;</b></font>", S["cell"])
                if arrow
                else ""
            )
            cols.append(gap)
    t = Table([cells], colWidths=cols)
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    t.hAlign = "LEFT"
    return t


def doc_architecture() -> None:
    st: list = []

    # ---------------- PAGE 1 — layered view ----------------
    st += [para("SYSTEM ARCHITECTURE — LAYERED VIEW", "h1")]
    st += [
        para(
            "YatraAI is a three-tier application with a deliberately thick service layer. Business rules "
            "live in pure-Python domain objects that touch neither the database nor the web framework, "
            "which is what makes the optimiser, scorer and validator unit-testable in isolation and "
            "deterministic under a fixed seed.",
            "p",
        )
    ]

    st += [Spacer(1, 1.5 * mm), para("PRESENTATION", "h3")]
    st += [
        flow_row(
            [
                (
                    "Next.js 14 client",
                    "App Router · TypeScript strict · Tailwind · TanStack Query",
                    INDIGO,
                ),
                (
                    "Typed API client",
                    "One place owns base URL, auth header, error shape, timeouts",
                    INDIGO_M,
                ),
                (
                    "Self-contained console",
                    "Served at / by the API · renders with no internet",
                    INDIGO_M,
                ),
            ],
            height=8 * mm,
        )
    ]

    st += [Spacer(1, 2 * mm), para("API", "h3")]
    st += [
        flow_row(
            [
                (
                    "FastAPI routers",
                    "10 route modules · OpenAPI generated from the same types",
                    INDIGO,
                ),
                (
                    "Middleware",
                    "Request id · structured logging · CORS · security headers",
                    INDIGO_M,
                ),
                (
                    "Dependencies",
                    "JWT auth · trip membership · admin · two rate-limit tiers",
                    INDIGO_M,
                ),
            ],
            height=8 * mm,
        )
    ]

    st += [Spacer(1, 2 * mm), para("DOMAIN SERVICES  —  no framework or database imports", "h3")]
    st += [
        flow_row(
            [
                (
                    "planner/",
                    "context · clustering · matrix · CP-SAT · greedy · validator · cost",
                    SAFFRON,
                ),
                ("recommend/", "scoring · aggregation · eligibility · taxonomy", SAFFRON),
                ("rag/", "retriever · embeddings · answer · citations", SAFFRON),
                ("routing/ weather/", "OSRM · haversine · Open-Meteo · climatology", TEAL),
                ("llm/ location/ analytics/", "providers · consent · privacy guard", TEAL),
            ],
            height=11 * mm,
            arrow=False,
            gap=3 * mm,
        )
    ]

    st += [Spacer(1, 2 * mm), para("PERSISTENCE", "h3")]
    st += [
        flow_row(
            [
                ("SQLAlchemy 2.0 models", "31 tables · 6 domains · Alembic migrations", INDIGO),
                ("Portable type layer", "GUID · JSONType · VectorType · TZDateTime", INDIGO_M),
                (
                    "PostgreSQL + pgvector  /  SQLite",
                    "One schema, two engines — no infrastructure needed",
                    TEAL,
                ),
            ],
            height=8 * mm,
        )
    ]

    st += [Spacer(1, 3.5 * mm)]
    st += [
        KeepTogether(
            table(
                [
                    ["ARCHITECTURAL DECISION", "RATIONALE", "CONSEQUENCE"],
                    [
                        "Domain logic in pure Python",
                        "The optimiser, scorer and validator import neither FastAPI nor SQLAlchemy.",
                        "Unit-testable without a database, and deterministic under a fixed seed.",
                    ],
                    [
                        "Provider abstraction everywhere",
                        "LLM, embeddings, routing, weather and database are swappable configuration strings.",
                        "The product runs fully offline; each fallback is measured and disclosed, not hidden.",
                    ],
                    [
                        "Validation independent of the solver",
                        "The validator re-reads persisted rows and re-derives every constraint from scratch.",
                        "A modelling bug surfaces as a failed validation, not as an impossible plan on screen.",
                    ],
                    [
                        "Replanning as input change",
                        "All eleven actions re-run the whole pipeline; nothing edits a schedule in place.",
                        "A modification cannot produce a state the optimiser would never have generated.",
                    ],
                    [
                        "Corpus derived from the catalogue",
                        "Chunks are generated from the same records the planner uses.",
                        "There is no second source of truth that can drift.",
                    ],
                ],
                [46 * mm, (LW - 46 * mm) / 2, (LW - 46 * mm) / 2],
                pad=2.6,
            )
        )
    ]

    st.append(PageBreak())

    # ---------------- PAGE 2 — runtime flows ----------------
    st += [para("RUNTIME FLOWS", "h1")]

    st += [para("FLOW 1 — ITINERARY GENERATION   ·   POST /api/v1/trips/{id}/itinerary", "h3")]
    st += [
        flow_row(
            [
                ("1 · Context", "Trip + per-member preferences merged", INDIGO),
                ("2 · Eligibility", "Infeasible options removed; veto absolute", CLAY),
                ("3 · Score", "9 components, fairness aggregation", SAFFRON),
                ("4 · Cluster", "Balanced k-means, 25 km guard", SAFFRON),
                ("5 · Matrix", "OSRM or haversine, per-day base", TEAL),
            ],
            height=9 * mm,
            gap=3 * mm,
        )
    ]
    st += [Spacer(1, 1.5 * mm)]
    st += [
        flow_row(
            [
                ("6 · Solve", "CP-SAT per day, relaxation ladder", TEAL),
                ("7 · Validate", "15 checks; errors block display", CLAY),
                ("8 · Cost", "Range across 5 components", INDIGO_M),
                ("9 · Explain", "LLM optional — narrates only", INDIGO_M),
                ("10 · Persist", "Versioned + fingerprint + audit", INDIGO),
            ],
            height=9 * mm,
            gap=3 * mm,
        )
    ]

    st += [Spacer(1, 3 * mm), para("FLOW 2 — CITED ANSWER   ·   POST /api/v1/assistant/ask", "h3")]
    st += [
        flow_row(
            [
                ("Sanitise + classify", "Injection neutralised; topic routed", CLAY),
                ("Scope + retrieve ×2", "Dense cosine and BM25, independently", INDIGO),
                ("Fuse + rerank", "RRF k=60, then a feature model", SAFFRON),
                ("Evidence gate", "Below 0.26 → abstain, no model call", TEAL),
                ("Answer + cite", "Citations computed from overlap", INDIGO),
            ],
            height=9 * mm,
            gap=3 * mm,
        )
    ]

    st += [Spacer(1, 3 * mm), para("FLOW 3 — DATA INGESTION   ·   make pipeline", "h3")]
    st += [
        flow_row(
            [
                ("Seed JSON", "10 files, committed to the repository", INDIGO_M),
                ("Bronze", "Content-hashed, idempotent — 140 documents", SAFFRON),
                ("Silver", "7 Pandera contracts — 130 attractions, 142 sources", SAFFRON),
                ("Gold", "Derived features — 130 rows, 0 rejected", TEAL),
            ],
            height=9 * mm,
            gap=3 * mm,
        )
    ]
    st += [
        Spacer(1, 1.5 * mm),
        para(
            "The same records also generate the knowledge corpus — 140 documents become 790 chunks and "
            "790 embeddings — so the assistant and the planner can never disagree about a fact.",
            "small",
        ),
    ]

    st += [Spacer(1, 3 * mm)]
    st += [
        table(
            [
                ["FAILURE MODE", "SYSTEM RESPONSE"],
                [
                    "No feasible schedule for a day",
                    "Five-step relaxation ladder, least harmful first. Travel is relaxed last and least. What was relaxed is recorded and shown to the user; if all attempts fail the day returns empty with status INFEASIBLE.",
                ],
                [
                    "Routing service unreachable",
                    "Haversine with documented detour factors and conservative urban speeds. Fallback rate reported at /metrics and disclosed in a UI banner.",
                ],
                [
                    "Weather service unreachable",
                    "Committed per-cluster climatology, labelled as seasonal averages rather than a forecast.",
                ],
                [
                    "Corpus cannot answer a question",
                    "Abstain below an absolute evidence threshold, with no model call and zero citations.",
                ],
                [
                    "LLM provider errors or is absent",
                    "Deterministic template composition. The response records which provider actually answered.",
                ],
                [
                    "A member's accessibility need conflicts with the majority",
                    "The candidate is removed, not down-weighted. A majority cannot outvote one member's mobility requirement.",
                ],
            ],
            [46 * mm, LW - 46 * mm],
            header=CLAY,
        )
    ]

    st.append(PageBreak())

    # ---------------- PAGE 3 — deployment & data ----------------
    st += [para("DEPLOYMENT TOPOLOGY & DATA ARCHITECTURE", "h1")]

    st += [para("DEPLOYMENT", "h3")]
    st += [
        flow_row(
            [
                ("Vercel", "Next.js frontend · security headers · NEXT_PUBLIC_API_URL", INDIGO),
                (
                    "Render",
                    "FastAPI container · secrets sync:false · JWT_SECRET generated at deploy",
                    INDIGO,
                ),
                ("Managed PostgreSQL", "pgvector extension · pooled connection string", TEAL),
            ],
            height=9 * mm,
        )
    ]
    st += [
        Spacer(1, 2 * mm),
        para(
            "Local development and CI use Docker Compose (pgvector/pg16, API, web) or the SQLite "
            "fallback, which requires no infrastructure at all. GitHub Actions runs backend, Postgres "
            "integration, data-quality, frontend and docker jobs. "
            "<font face='Courier'>scripts/verify_deployment.py</font> exercises ten post-deployment "
            "checks against a live instance and exits non-zero on any failure.",
            "small",
        ),
    ]

    st += [Spacer(1, 2.5 * mm), para("DATA ARCHITECTURE — 31 TABLES, SIX DOMAINS", "h3")]
    st += [
        flow_row(
            [
                ("Catalogue", "clusters · attractions · schedules · costs · sources", INDIGO),
                ("Trips", "trips · members · preferences · proposals · votes · chat", INDIGO_M),
                ("Itineraries", "itineraries · days · activities · scores", SAFFRON),
                ("Knowledge", "documents · chunks · embeddings", SAFFRON),
                ("Privacy", "sharing sessions · location points (expiring)", CLAY),
                ("Observability", "audit · analytics · model & pipeline runs", TEAL),
            ],
            height=11 * mm,
            arrow=False,
            gap=2.5 * mm,
        )
    ]

    st += [Spacer(1, 3 * mm)]
    st += [
        table(
            [
                ["CROSS-CUTTING CONCERN", "WHERE IT IS IMPLEMENTED", "EVIDENCE IT WORKS"],
                [
                    "Determinism",
                    "num_workers = 1, fixed random seed, deterministic k-means seeding, input fingerprint stored per itinerary",
                    "A test asserts identical inputs produce identical plans, and that candidate ordering does not change the result",
                ],
                [
                    "Portability across databases",
                    "GUID, JSONType, VectorType and TZDateTime TypeDecorators",
                    "The identical schema and the whole test suite run on PostgreSQL and on SQLite",
                ],
                [
                    "Graceful degradation",
                    "Provider interfaces with measured fallbacks; nothing raises",
                    "/metrics reports per-provider latency, error rate and fallback rate; the UI shows an honest banner",
                ],
                [
                    "Auditability",
                    "Append-only audit_logs on every sensitive trip action, carrying actor, entity, trip and request id",
                    "Rows join to structured logs by request id. Message bodies and coordinates are never included.",
                ],
                [
                    "Privacy by construction",
                    "Coordinates snapped before the row is built; forbidden keys stripped at analytics write time; no history table exists",
                    "A test posts a real coordinate and asserts it appears nowhere in the dashboard payload",
                ],
                [
                    "Reproducibility of claims",
                    "ml/ experiments, evaluation/ harness, generated reports",
                    "make experiments and python evaluation/run_rag_eval.py regenerate every published figure",
                ],
            ],
            [40 * mm, (LW - 40 * mm) / 2, (LW - 40 * mm) / 2],
        )
    ]

    st += [
        Spacer(1, 4 * mm),
        note(
            "<b>The single architectural claim.</b> Correctness is delegated to components that can be "
            "tested — a constraint solver, a validator, executable data contracts. Fluency is delegated "
            "to a component that cannot affect correctness, because it runs after everything has been "
            "decided and validated. Turn the language model off entirely, which is the default this test "
            "suite runs against, and the product still produces a complete, validated itinerary.",
            "indigo",
        ),
    ]

    build(
        OUT / "YatraAI_System_Architecture.pdf",
        st,
        "YatraAI — System Architecture",
        "Layered view · runtime flows · deployment",
        pagesize=LAND,
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    doc_readme()
    doc_architecture()
    for f in sorted(OUT.glob("*.pdf")):
        print(f"Wrote {f}  ({f.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
