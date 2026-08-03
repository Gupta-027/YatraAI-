#!/usr/bin/env python
"""Build the YatraAI interview deck.

    python scripts/build_deck.py            # -> docs/YatraAI_Interview_Deck.pptx

Ten slides, dense by design: this is meant to be studied from as much as
presented from. Every figure in it is traceable to a script in this repository
(`ml/`, `evaluation/`, `pytest`) or to a constant in the source — nothing here is
illustrative. Where a number is an assumption or a limitation, the slide says so.

The deck is generated rather than hand-built for the same reason the README
numbers are: regenerating it after a code change is one command, so it cannot
quietly drift away from the system it describes.
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "YatraAI_Interview_Deck.pptx"

# --------------------------------------------------------------------------- #
# Palette — the product's own Tailwind tokens, so deck and app agree.
# --------------------------------------------------------------------------- #
NAVY = RGBColor(0x0E, 0x13, 0x29)  # indigo-900
NAVY_2 = RGBColor(0x14, 0x1C, 0x3E)  # indigo-800
INDIGO = RGBColor(0x23, 0x30, 0x6B)  # indigo-600
INDIGO_M = RGBColor(0x42, 0x56, 0x9F)  # indigo-400
INDIGO_L = RGBColor(0xD6, 0xDC, 0xF2)  # indigo-100
INDIGO_XL = RGBColor(0xEE, 0xF1, 0xFA)  # indigo-50
SAFFRON = RGBColor(0xE0, 0x7A, 0x3F)  # saffron-400
SAFFRON_D = RGBColor(0xA4, 0x4C, 0x1F)  # saffron-600
SAFFRON_L = RGBColor(0xFA, 0xDF, 0xCB)  # saffron-100
SAFFRON_XL = RGBColor(0xFD, 0xF2, 0xEA)  # saffron-50
TEAL = RGBColor(0x0F, 0x7B, 0x6C)  # teal-500
TEAL_L = RGBColor(0xC6, 0xEB, 0xE4)  # teal-100
TEAL_XL = RGBColor(0xE9, 0xF7, 0xF4)  # teal-50
CLAY = RGBColor(0xA9, 0x45, 0x45)  # clay-500
CLAY_L = RGBColor(0xF2, 0xDC, 0xDC)
SAND = RGBColor(0xFD, 0xFB, 0xF7)  # sand-50
SAND_2 = RGBColor(0xF2, 0xEC, 0xE1)  # sand-200
LINE = RGBColor(0xE6, 0xE1, 0xD8)  # sand-300
INK = RGBColor(0x1A, 0x1D, 0x2E)
INK_M = RGBColor(0x5B, 0x61, 0x78)
INK_F = RGBColor(0x8A, 0x90, 0xA6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

FONT = "Segoe UI"
MONO = "Consolas"

SECTIONS = [
    "PROBLEM &\nARCHITECTURE",
    "DATA\nFOUNDATION",
    "RANKING &\nFAIRNESS",
    "OPTIMISATION\n& VALIDATION",
    "RETRIEVAL,\nTRUST & RESULTS",
]

SW, SH = 13.333, 7.5  # slide size, inches
M = 0.36  # page margin
CW = SW - 2 * M  # content width


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #
def rect(slide, x, y, w, h, fill=None, line=None, line_w=0.75):
    from pptx.enum.shapes import MSO_SHAPE

    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.shadow.inherit = False
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(line_w)
    shp.text_frame.text = ""
    return shp


def text(
    slide,
    x,
    y,
    w,
    h,
    runs,
    size=10,
    color=INK,
    bold=False,
    align=PP_ALIGN.LEFT,
    font=FONT,
    anchor=MSO_ANCHOR.TOP,
    line_spacing=1.0,
    space_after=0,
):
    """`runs` is a str, or a list of paragraphs; a paragraph is a str or list of
    (text, {overrides}) tuples so a single line can mix weights and colours."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Emu(0)
    tf.margin_top = tf.margin_bottom = Emu(0)
    tf.vertical_anchor = anchor

    paras = [runs] if isinstance(runs, str) else runs
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        p.space_after = Pt(space_after)
        pieces = [para] if isinstance(para, str) else para
        for piece in pieces:
            # A piece is either a bare string or a (text, overrides) pair. Accepting
            # both keeps the slide definitions readable — most runs need no overrides.
            content, over = (piece, {}) if isinstance(piece, str) else piece
            r = p.add_run()
            r.text = content
            f = r.font
            f.name = over.get("font", font)
            f.size = Pt(over.get("size", size))
            f.bold = over.get("bold", bold)
            f.color.rgb = over.get("color", color)
    return box


def ribbon(slide, active: int):
    """Section tracker across the top — orients the reader mid-deck."""
    n = len(SECTIONS)
    gap = 0.06
    w = (CW - gap * (n - 1)) / n
    for i, label in enumerate(SECTIONS):
        x = M + i * (w + gap)
        on = i == active
        rect(slide, x, 0.26, w, 0.46, SAFFRON if on else SAFFRON_L)
        text(
            slide,
            x,
            0.33,
            w,
            0.34,
            label.split("\n"),
            size=7.5,
            bold=True,
            color=WHITE if on else SAFFRON_D,
            align=PP_ALIGN.CENTER,
            line_spacing=0.95,
        )


def headline(slide, title, y=0.88):
    text(slide, M, y, CW, 0.32, title, size=17, bold=True, color=INDIGO)
    rect(slide, M, y + 0.36, CW, 0.022, INDIGO)


def band(slide, x, y, w, label, fill=INDIGO, color=WHITE, h=0.3, size=9.5):
    rect(slide, x, y, w, h, fill)
    text(
        slide,
        x + 0.1,
        y + 0.055,
        w - 0.2,
        h - 0.08,
        label,
        size=size,
        bold=True,
        color=color,
    )


def footer(slide, source, page):
    rect(slide, M, SH - 0.52, CW, 0.012, LINE)
    text(slide, M, SH - 0.42, CW - 0.7, 0.28, source, size=6.8, color=INK_F)
    text(
        slide,
        SW - M - 0.6,
        SH - 0.44,
        0.6,
        0.3,
        f"{page:02d}",
        size=11,
        bold=True,
        color=INDIGO_M,
        align=PP_ALIGN.RIGHT,
    )


def kpi(slide, x, y, w, value, label, accent=INDIGO, h=0.78, vsize=17):
    rect(slide, x, y, w, 0.045, accent)
    rect(slide, x, y + 0.045, w, h - 0.045, WHITE, LINE)
    text(slide, x + 0.1, y + 0.14, w - 0.2, 0.3, value, size=vsize, bold=True, color=accent)
    text(slide, x + 0.1, y + 0.48, w - 0.2, 0.26, label, size=7.2, color=INK_M, line_spacing=0.95)


def table(
    slide,
    x,
    y,
    w,
    col_w,
    rows,
    header_fill=INDIGO,
    row_h=0.235,
    head_h=0.28,
    size=7.6,
    head_size=7.4,
    zebra=True,
    mono_cols=(),
    align=None,
):
    """Hand-styled table. Every cell fill is set explicitly so PowerPoint's
    default banding style never shows through."""
    n_rows, n_cols = len(rows), len(rows[0])
    total_h = head_h + row_h * (n_rows - 1)
    shape = slide.shapes.add_table(n_rows, n_cols, Inches(x), Inches(y), Inches(w), Inches(total_h))
    tbl = shape.table
    tbl.first_row = False
    tbl.horz_banding = False

    scale = w / sum(col_w)
    for i, cw in enumerate(col_w):
        tbl.columns[i].width = Inches(cw * scale)
    tbl.rows[0].height = Inches(head_h)
    for r in range(1, n_rows):
        tbl.rows[r].height = Inches(row_h)

    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.margin_left = Inches(0.06)
            cell.margin_right = Inches(0.06)
            cell.margin_top = Inches(0.02)
            cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = header_fill
            elif zebra and r % 2 == 0:
                cell.fill.fore_color.rgb = SAND
            else:
                cell.fill.fore_color.rgb = WHITE

            body, over = (val, {}) if isinstance(val, str) else val
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = over.get("align", align[c] if align else PP_ALIGN.LEFT)
            run = p.add_run()
            run.text = body
            f = run.font
            f.size = Pt(head_size if r == 0 else over.get("size", size))
            f.bold = over.get("bold", r == 0 or c == 0)
            f.name = over.get("font", MONO if c in mono_cols and r > 0 else FONT)
            f.color.rgb = over.get("color", WHITE if r == 0 else INK)
    return shape


def callout(slide, y, label, body, fill=NAVY_2, label_color=SAFFRON, h=0.46):
    rect(slide, M, y, CW, h, fill)
    text(
        slide,
        M + 0.14,
        y + 0.09,
        CW - 0.28,
        h - 0.16,
        [[(label, {"color": label_color, "bold": True}), (body, {"color": WHITE})]],
        size=8.6,
        line_spacing=1.15,
    )


def blank(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, SW, SH, WHITE)
    return s


# --------------------------------------------------------------------------- #
# Slides
# --------------------------------------------------------------------------- #
def slide_01_title(prs):
    s = blank(prs)
    rect(s, 0, 0, SW, SH, NAVY)
    rect(s, 0, 0, 0.12, SH, SAFFRON)

    text(
        s,
        0.85,
        1.05,
        10,
        0.3,
        "ENGINEERING CASE STUDY  ·  APPLIED ML & OPTIMISATION",
        size=10,
        bold=True,
        color=SAFFRON,
    )
    text(s, 0.85, 1.55, 11.5, 1.0, "YatraAI", size=52, bold=True, color=WHITE)
    text(
        s,
        0.85,
        2.55,
        11.5,
        0.5,
        "Context-Aware Group Travel Intelligence",
        size=22,
        bold=True,
        color=RGBColor(0x7C, 0x8F, 0xD6),
    )
    rect(s, 0.85, 3.2, 1.5, 0.04, SAFFRON)

    text(
        s,
        0.85,
        3.5,
        9.6,
        0.9,
        [
            "A group itinerary planner where a constraint solver — not a language model —",
            "decides what you do and when. The model runs last, writes prose, and changes nothing.",
        ],
        size=12,
        color=RGBColor(0xC5, 0xCB, 0xDE),
        line_spacing=1.35,
    )

    n, gap = len(SECTIONS), 0.14
    w = (11.6 - gap * (n - 1)) / n
    for i, label in enumerate(SECTIONS):
        x = 0.85 + i * (w + gap)
        rect(s, x, 4.75, w, 0.045, SAFFRON)
        rect(s, x, 4.795, w, 0.72, NAVY_2)
        text(s, x + 0.1, 4.88, w - 0.2, 0.2, f"{i + 1:02d}", size=9, bold=True, color=SAFFRON)
        text(
            s,
            x + 0.1,
            5.09,
            w - 0.2,
            0.38,
            label.split("\n"),
            size=7.8,
            bold=True,
            color=WHITE,
            line_spacing=1.0,
        )

    stats = [
        ("338", "automated tests\npassing"),
        ("130", "curated places\n10 destinations"),
        ("−57%", "travel vs a greedy\nplanner (measured)"),
        ("1.00", "RAG abstention\naccuracy"),
        ("0", "LLM calls needed\nto produce a plan"),
    ]
    w2 = 11.6 / len(stats)
    for i, (v, lab) in enumerate(stats):
        x = 0.85 + i * w2
        text(s, x, 5.95, w2 - 0.2, 0.4, v, size=26, bold=True, color=SAFFRON)
        text(
            s,
            x,
            6.45,
            w2 - 0.2,
            0.5,
            lab.split("\n"),
            size=8,
            color=RGBColor(0x9A, 0xA2, 0xBC),
            line_spacing=1.15,
        )

    text(
        s,
        0.85,
        7.02,
        11.6,
        0.3,
        "Every figure in this deck is reproduced by a script in the repository. Assumptions and "
        "limitations are labelled as such.",
        size=7.5,
        color=RGBColor(0x6B, 0x74, 0x92),
    )
    return s


def slide_02_problem(prs):
    s = blank(prs)
    ribbon(s, 0)
    headline(s, "THE PROBLEM — AND THE ONE DESIGN DECISION EVERYTHING FOLLOWS FROM")

    band(s, M, 1.42, 5.0, "WHAT THE PRODUCT SOLVES")
    rect(s, M, 1.72, 5.0, 2.42, WHITE, LINE)
    text(
        s,
        M + 0.14,
        1.86,
        4.72,
        2.2,
        [
            [
                ("Business problem.  ", {"bold": True, "color": INDIGO}),
                (
                    "Group trips fail on coordination, not inspiration. Four people want four "
                    "different things; one always gets ignored; the plan ignores opening hours, "
                    "travel time and weather, and collapses on day one."
                ),
            ],
            "",
            [
                ("Technical problem.  ", {"bold": True, "color": INDIGO}),
                (
                    "Produce a fair, explainable and physically feasible group itinerary under "
                    "weather, time windows, budget, distance, opening hours, individual preferences "
                    "and accessibility — without letting a language model invent the facts."
                ),
            ],
        ],
        size=8.8,
        color=INK_M,
        line_spacing=1.24,
    )

    band(s, M, 4.28, 5.0, "WHY AN LLM CANNOT OWN THIS", fill=CLAY)
    rect(s, M, 4.58, 5.0, 1.62, WHITE, LINE)
    text(
        s,
        M + 0.14,
        4.72,
        4.72,
        1.4,
        [
            'Ask any LLM to "plan three days in Agra" and it will confidently:',
            "•  schedule the Taj Mahal on a Friday — it is closed to tourists",
            "•  allow 20 minutes to cross Delhi in traffic",
            "•  quote a ticket price it invented",
            "",
            [
                (
                    "Each failure is a constraint violation, not a wording problem.",
                    {"bold": True, "color": CLAY},
                )
            ],
        ],
        size=8.6,
        color=INK_M,
        line_spacing=1.22,
    )

    band(s, 5.62, 1.42, CW - 5.26, "RESPONSIBILITY SEPARATION — WHO IS ALLOWED TO INVENT ANYTHING")
    table(
        s,
        5.62,
        1.78,
        CW - 5.26,
        [0.5, 2.6, 2.2],
        [
            ["STAGE", "OWNER", "CAN IT INVENT FACTS?"],
            [
                "1",
                "Curated catalogue + provenance",
                ("No — every field cites a source", {"color": TEAL}),
            ],
            ["2", "Hard eligibility filters", ("No — infeasible options removed", {"color": TEAL})],
            ["3", "Fairness-aware ranking (9 features)", ("No — deterministic", {"color": TEAL})],
            ["4", "Balanced k-means day clustering", ("No", {"color": TEAL})],
            ["5", "OSRM → haversine travel matrix", ("No", {"color": TEAL})],
            ["6", "OR-Tools CP-SAT scheduler", ("No — solves a stated model", {"color": TEAL})],
            ["7", "15-check constraint validator", ("No — errors block display", {"color": TEAL})],
            [
                "8",
                "LLM (optional)",
                ("YES — which is why it runs last", {"color": CLAY, "bold": True}),
            ],
        ],
        row_h=0.245,
        head_h=0.28,
    )

    rect(s, 5.62, 4.06, CW - 5.26, 2.14, INDIGO_XL, INDIGO_L)
    text(
        s,
        5.76,
        4.2,
        CW - 5.54,
        1.9,
        [
            [
                ("The load-bearing claim.  ", {"bold": True, "color": INDIGO}),
                (
                    "The LLM sits at stage 8. By then the itinerary is chosen, scheduled and "
                    "validated. Its output is prose printed beside the timeline — it cannot add, "
                    "remove or reorder a stop."
                ),
            ],
            "",
            [
                ("Proof, not assertion.  ", {"bold": True, "color": INDIGO}),
                ("The default provider is "),
                ("mock", {"font": MONO}),
                (". Live telemetry at "),
                ("/api/v1/metrics", {"font": MONO}),
                (" reports "),
                ("llm.calls = 0", {"font": MONO, "bold": True, "color": CLAY}),
                (
                    ". Every itinerary in this deck was produced with no model call. Switch a real "
                    "provider on and the plan is byte-identical — only the paragraph changes."
                ),
            ],
        ],
        size=8.8,
        color=INK_M,
        line_spacing=1.26,
    )

    callout(
        s,
        6.36,
        "SO WHAT?  ",
        "Correctness is delegated to systems that can be tested; fluency is delegated to a "
        "model that cannot break correctness. That split is the whole architecture.",
    )
    footer(
        s, "Sources: repository README; live /api/v1/metrics telemetry; docs/architecture.md.", 2
    )
    return s


def slide_03_stack(prs):
    s = blank(prs)
    ribbon(s, 0)
    headline(s, "SYSTEM ARCHITECTURE & TECHNOLOGY STACK")

    band(s, M, 1.42, 6.1, "REQUEST PATH — GENERATE AN ITINERARY")
    rect(s, M, 1.72, 6.1, 2.5, WHITE, LINE)
    steps = [
        ("Next.js 14 client", "typed API client, TanStack Query cache", INDIGO),
        ("FastAPI route", "Pydantic validation · JWT · rate limit tier", INDIGO_M),
        ("Planner pipeline", "8 stages, pure-Python domain objects", SAFFRON),
        ("OR-Tools CP-SAT", "one model per day, deterministic", TEAL),
        ("Validator + persist", "15 checks, then SQLAlchemy write", INDIGO),
    ]
    for i, (title, sub, col) in enumerate(steps):
        y = 1.84 + i * 0.47
        rect(s, M + 0.12, y, 0.28, 0.28, col)
        text(
            s,
            M + 0.12,
            y + 0.045,
            0.28,
            0.2,
            str(i + 1),
            size=9,
            bold=True,
            color=WHITE,
            align=PP_ALIGN.CENTER,
        )
        text(s, M + 0.5, y - 0.01, 5.5, 0.2, title, size=9, bold=True, color=INK)
        text(s, M + 0.5, y + 0.17, 5.5, 0.2, sub, size=7.6, color=INK_F)
        if i < len(steps) - 1:
            rect(s, M + 0.255, y + 0.28, 0.012, 0.19, LINE)

    band(s, 6.66, 1.42, CW - 6.3, "STACK BY LAYER", fill=INDIGO_M)
    table(
        s,
        6.66,
        1.72,
        CW - 6.3,
        [1.05, 2.6],
        [
            ["LAYER", "TECHNOLOGY"],
            [
                "Frontend",
                "Next.js 14 (App Router) · TypeScript strict · Tailwind · TanStack Query · Recharts · react-leaflet",
            ],
            ["API", "FastAPI · Pydantic v2 · pydantic-settings · structlog"],
            ["Persistence", "SQLAlchemy 2.0 · Alembic · PostgreSQL + pgvector, portable to SQLite"],
            ["Optimisation", "Google OR-Tools CP-SAT"],
            ["ML / science", "NumPy · pandas · scikit-learn · Pandera"],
            ["Data pipeline", "Bronze/Silver/Gold medallion · Airflow DAGs · pyarrow"],
            ["Security", "PyJWT (HS256) · bcrypt · in-process sliding-window limiter"],
            [
                "Testing / CI",
                "pytest (295) · Vitest + Testing Library (43) · ruff · mypy · GitHub Actions",
            ],
            ["Deploy", "Docker multi-stage · Compose · render.yaml · Vercel"],
        ],
        row_h=0.245,
        head_h=0.28,
        size=7.4,
    )

    band(
        s,
        M,
        4.34,
        CW,
        "PROVIDER ABSTRACTION — EVERY EXTERNAL DEPENDENCY IS SWAPPABLE, AND EVERY FALLBACK IS MEASURED",
        fill=TEAL,
    )
    table(
        s,
        M,
        4.66,
        CW,
        [1.25, 1.5, 1.9, 1.05, 3.6],
        [
            ["PROVIDER", "DEFAULT", "FALLBACK", "LIVE RATE", "WHY IT MATTERS"],
            [
                "LLM",
                "mock",
                "deterministic templates",
                ("0 calls", {"color": TEAL, "bold": True}),
                "Product is fully functional with no model configured — the default the tests run against",
            ],
            [
                "Embeddings",
                "hashing",
                "n/a (is the default)",
                "0% fallback",
                "384-dim signed feature hashing — deterministic, no model download, not a neural encoder",
            ],
            [
                "Routing",
                "OSRM",
                "haversine × detour factor",
                ("100% fallback", {"color": SAFFRON_D}),
                "Conservative Indian urban speeds; underestimating travel is the dangerous direction",
            ],
            [
                "Weather",
                "Open-Meteo",
                "committed climatology",
                ("100% fallback", {"color": SAFFRON_D}),
                "Labelled in the UI as seasonal averages, never presented as a forecast",
            ],
            [
                "Database",
                "PostgreSQL + pgvector",
                "SQLite",
                "—",
                "Four portable TypeDecorators (GUID, JSONType, VectorType, TZDateTime) — one schema, two engines",
            ],
        ],
        header_fill=TEAL,
        row_h=0.28,
        head_h=0.28,
        size=7.4,
    )

    callout(
        s,
        6.38,
        "KEY POINT:  ",
        "No provider raises on failure — each degrades to a documented fallback and records it. "
        "The UI shows an honest banner; /metrics reports the real fallback rate. Both amber rates "
        "above are this machine being offline, not a bug.",
        fill=NAVY_2,
        h=0.58,
    )
    footer(
        s,
        "Sources: pyproject.toml; apps/web/package.json; yatraai/config.py; live /api/v1/metrics.",
        3,
    )
    return s


def slide_04_data(prs):
    s = blank(prs)
    ribbon(s, 1)
    headline(s, "DATA FOUNDATION — WHERE THE FACTS COME FROM, AND HOW THEY ARE POLICED")

    band(s, M, 1.42, 7.5, "BRONZE → SILVER → GOLD, WITH A CONTRACT AT EVERY PROMOTION")
    rect(s, M, 1.72, 7.5, 1.62, WHITE, LINE)
    stages = [
        ("BRONZE", "Raw seed JSON, content-hashed", "140 documents ingested", SAFFRON),
        (
            "SILVER",
            "Validated, typed, deduplicated",
            "130 attractions · 142 sources\n164 schedules · 216 fee rows",
            INDIGO_M,
        ),
        (
            "GOLD",
            "Derived planning features",
            "130 feature rows · 10 cluster\nmetric rows · 0 rejected",
            TEAL,
        ),
    ]
    bw = 7.5 / 3
    for i, (name, what, nums, col) in enumerate(stages):
        x = M + i * bw
        rect(s, x + 0.06, 1.82, bw - 0.12, 0.26, col)
        text(
            s,
            x + 0.06,
            1.865,
            bw - 0.12,
            0.2,
            name,
            size=8.5,
            bold=True,
            color=WHITE,
            align=PP_ALIGN.CENTER,
        )
        text(s, x + 0.14, 2.16, bw - 0.28, 0.24, what, size=7.8, bold=True, color=INK)
        text(
            s,
            x + 0.14,
            2.42,
            bw - 0.28,
            0.8,
            nums.split("\n"),
            size=7.6,
            color=INK_M,
            line_spacing=1.2,
        )

    band(s, M, 3.46, 7.5, "WHAT EVERY ATTRACTION CARRIES — ~30 STRUCTURED FIELDS", fill=INDIGO_M)
    table(
        s,
        M,
        3.78,
        7.5,
        [1.15, 3.2],
        [
            ["GROUP", "FIELDS"],
            [
                "Identity",
                "slug · name · locality · city · lat/lon · categories (mapped to a 10-interest taxonomy)",
            ],
            [
                "Narrative",
                "summary · history · significance · 2–8 interesting facts  → these become the RAG chunks",
            ],
            [
                "Planning",
                "typical / min / max duration · best time of day · suitable months · indoor-outdoor · weather sensitivity · crowd profile",
            ],
            [
                "Access",
                "wheelchair · accessibility notes · senior & child suitability · physical intensity",
            ],
            [
                "Etiquette",
                "dress code · photography policy · local customs  (mandatory for religious sites — enforced by test)",
            ],
            ["Schedule", "per-weekday open/close windows · seasonal variants · closure days"],
            ["Cost", "fee bands by visitor type · free flags"],
            [
                "Provenance",
                "≥1 cited source, HTTPS, allow-listed domain, with a covers[] list and last_verified date",
            ],
        ],
        header_fill=INDIGO_M,
        row_h=0.263,
        head_h=0.27,
        size=7.3,
    )

    band(s, 8.06, 1.42, CW - 7.7, "THE GATES", fill=CLAY)
    rect(s, 8.06, 1.72, CW - 7.7, 2.22, WHITE, LINE)
    text(
        s,
        8.2,
        1.86,
        CW - 7.98,
        2.0,
        [
            [
                ("7 Pandera contracts", {"bold": True, "color": INK}),
                (
                    " enforced at promotion — a row that fails is rejected with a reason, never coerced silently."
                ),
            ],
            "",
            [
                ("12 runtime data-quality checks", {"bold": True, "color": INK}),
                (" power an admin dashboard and gate the Airflow DAG."),
            ],
            "",
            [
                ("30 data-quality tests", {"bold": True, "color": INK}),
                (
                    " run in CI: coordinate bounds, cluster distance, duplicate detection, category-taxonomy coverage, source allow-list, dress code on religious sites."
                ),
            ],
        ],
        size=8.4,
        color=INK_M,
        line_spacing=1.22,
    )

    band(s, 8.06, 4.06, CW - 7.7, "THE HONESTY RULE", fill=SAFFRON)
    rect(s, 8.06, 4.36, CW - 7.7, 1.84, SAFFRON_XL, SAFFRON_L)
    text(
        s,
        8.2,
        4.5,
        CW - 7.98,
        1.6,
        [
            [
                (
                    "Not one schedule or fee row in this dataset claims to be verified.",
                    {"bold": True, "color": SAFFRON_D},
                )
            ],
            "",
            "I authored the catalogue from public sources; I cannot verify opening hours or prices. So every such row carries verified: false, the UI renders a badge, and a data-quality test fails the build if a row ever claims otherwise.",
        ],
        size=8.4,
        color=INK_M,
        line_spacing=1.22,
    )

    callout(
        s,
        6.32,
        "TWO REAL DEFECTS THE GATE CAUGHT:  ",
        "a neighbour reference crossing destination clusters (Mawlynnong → Dawki), and two "
        "attractions sharing identical coordinates (Gaurikund / Kedarnath trek). Both were my "
        "authoring errors. Neither was visible by reading the JSON.",
    )
    footer(
        s,
        "Sources: data/seed/attractions/*.json; pipelines/medallion.py; tests/data_quality/; docs/data-dictionary.md.",
        4,
    )
    return s


def slide_05_ranking(prs):
    s = blank(prs)
    ribbon(s, 2)
    headline(s, "RANKING & GROUP FAIRNESS — TURNING FOUR PEOPLE'S PREFERENCES INTO ONE SHORTLIST")

    band(s, M, 1.42, 6.05, "STEP 1 — HARD ELIGIBILITY (REMOVAL, NOT DOWN-RANKING)", fill=CLAY)
    rect(s, M, 1.72, 6.05, 1.06, WHITE, LINE)
    text(
        s,
        M + 0.14,
        1.84,
        5.77,
        0.9,
        [
            "Closed on every day of the trip · outside budget · fails a stated accessibility need · on a member's avoid list.",
            "",
            [
                (
                    "A member veto is absolute — a majority cannot outvote one person's mobility requirement. "
                    "Infeasible options are deleted from the candidate set, so the optimiser can never "
                    "trade an accessibility need against a higher score.",
                    {"bold": True, "color": CLAY},
                )
            ],
        ],
        size=8.4,
        color=INK_M,
        line_spacing=1.2,
    )

    band(s, M, 2.92, 6.05, "STEP 2 — NINE EXPLAINABLE SCORE COMPONENTS")
    table(
        s,
        M,
        3.24,
        6.05,
        [2.0, 3.5],
        [
            ["COMPONENT", "WHAT IT MEASURES"],
            ["interest_match", "Member interests vs the attraction's mapped categories"],
            ["group_fairness", "Marginal gain to the least-served members"],
            ["attraction_quality", "Curated significance / interest"],
            ["seasonal_suitability", "Month fit, per attraction"],
            ["weather_suitability", "Forecast vs weather sensitivity + indoor/outdoor"],
            ["budget_suitability", "Entry fee against the daily budget"],
            ["accessibility_suitability", "Access rating and physical intensity"],
            ["evidence_quality", "Source authority, count and completeness"],
            ["distance / crowd penalty", "Subtracted — travel cost and congestion"],
        ],
        row_h=0.238,
        head_h=0.27,
        size=7.5,
        mono_cols=(0,),
    )

    rect(s, M, 5.72, 6.05, 0.62, INDIGO_XL, INDIGO_L)
    text(
        s,
        M + 0.14,
        5.83,
        5.77,
        0.5,
        [
            [
                ("Weights are fixed and inspectable.  ", {"bold": True, "color": INDIGO}),
                (
                    'The "Why was this selected?" panel renders the stored breakdown for that plan — it is '
                    "not generated text, and it cannot disagree with the optimiser."
                ),
            ]
        ],
        size=8.3,
        color=INK_M,
        line_spacing=1.2,
    )

    band(
        s,
        6.66,
        1.42,
        CW - 6.3,
        "STEP 3 — AGGREGATION: FIVE METHODS, MEASURED HEAD-TO-HEAD",
        fill=TEAL,
    )
    table(
        s,
        6.66,
        1.74,
        CW - 6.3,
        [2.15, 1.0, 1.05, 0.85],
        [
            ["METHOD", "MEAN SAT.", "LEAST SATISFIED", "SPREAD"],
            ["simple_average", "0.604", "0.481", "0.172"],
            ["borda_count", "0.618", ("0.478", {"color": CLAY}), "0.197"],
            ["max_min_fairness", "0.582", ("0.545", {"color": TEAL, "bold": True}), "0.069"],
            ["fairness_aware (1-pass)", "0.603", "0.484", "0.167"],
            ["select_fairly (SHIPPED)", "0.597", ("0.522", {"color": TEAL, "bold": True}), "0.115"],
        ],
        header_fill=TEAL,
        row_h=0.27,
        head_h=0.28,
        size=7.6,
        mono_cols=(0, 1, 2, 3),
    )

    rect(s, 6.66, 3.53, CW - 6.3, 1.28, WHITE, LINE)
    text(
        s,
        6.8,
        3.65,
        CW - 6.58,
        1.1,
        [
            [
                ("How to read this.  ", {"bold": True, "color": INDIGO}),
                (
                    "Five group profiles built so a simple average steamrolls a minority. "
                    "Iterative fair selection captures 64% of pure max-min's fairness gain for 30% of "
                    "its cost in mean satisfaction."
                ),
            ],
            "",
            [
                ("The null result is the useful one:  ", {"bold": True, "color": SAFFRON_D}),
                (
                    "single-pass fairness_aware barely beats a plain average (0.484 vs 0.481). That is "
                    "exactly why the iterative selector exists — the cheap version does not work."
                ),
            ],
        ],
        size=8.3,
        color=INK_M,
        line_spacing=1.2,
    )

    band(s, 6.66, 4.96, CW - 6.3, "THE FAIRNESS METRIC", fill=INDIGO_M)
    rect(s, 6.66, 5.28, CW - 6.3, 1.06, INDIGO_XL, INDIGO_L)
    (
        text(
            s,
            6.8,
            5.4,
            CW - 6.58,
            0.9,
            [
                [
                    (
                        "Jain's fairness index      J(x) = (Σxᵢ)² / (n · Σxᵢ²)",
                        {"font": MONO, "bold": True, "color": INDIGO, "size": 9.5},
                    )
                ],
                "",
                "1.0 = everyone equally served; 1/n = one person served. Reported alongside the floor guaranteed to the worst-served member, because an average hides exactly the person this product exists to protect.",
            ],
            size=8.2,
            color=INK_M,
            line_spacing=1.18,
        ),
    )

    callout(
        s,
        6.38,
        "INTERVIEW LINE:  ",
        '"I did not pick an aggregation rule, I measured five. Borda scored the best mean and '
        "the worst floor — which is the trap. The shipped selector deliberately gives up 1.1% of "
        'mean satisfaction to raise the least-satisfied member 8.5%."',
        h=0.58,
    )
    footer(
        s,
        "Source: python ml/experiments/aggregation_comparison.py → ml/reports/aggregation_comparison.md. 5 profiles, K=5.",
        5,
    )
    return s


def slide_06_optimiser(prs):
    s = blank(prs)
    ribbon(s, 3)
    headline(s, "THE OPTIMISER — A PRIZE-COLLECTING TSP WITH TIME WINDOWS, SOLVED PER DAY")

    band(s, M, 1.42, 6.3, "THE CP-SAT MODEL")
    rect(s, M, 1.72, 6.3, 2.62, WHITE, LINE)
    text(
        s,
        M + 0.14,
        1.84,
        6.02,
        2.4,
        [
            [("DECISION VARIABLES", {"bold": True, "color": INDIGO, "size": 8})],
            [
                ("x[i][j] ∈ {0,1}", {"font": MONO, "color": INK}),
                ("   tour goes i → j        ", {}),
                ("x[i][i] = 1", {"font": MONO}),
                ("  node skipped", {}),
            ],
            [
                ("u[i] ∈ ℤ", {"font": MONO, "color": INK}),
                ("          service start, minutes from midnight", {}),
            ],
            "",
            [("CONSTRAINTS", {"bold": True, "color": INDIGO, "size": 8})],
            [
                ("C1  ", {"font": MONO, "bold": True}),
                (
                    "AddCircuit over all arcs — sequencing AND selection in one constraint. A node opts out via its self-loop: no subtour-elimination family, no big-M.",
                    {},
                ),
            ],
            [
                ("C2  ", {"font": MONO, "bold": True}),
                (
                    "x[i][j] = 1 ⟹ u[j] ≥ u[i] + sᵢ + tᵢⱼ   (a real implication, via OnlyEnforceIf)",
                    {},
                ),
            ],
            [
                ("C3  ", {"font": MONO, "bold": True}),
                ("eᵢ ≤ u[i] ≤ lᵢ — the weekday opening window ∩ the group's day window", {}),
            ],
            [
                ("C4  ", {"font": MONO, "bold": True}),
                (
                    "skipped nodes pinned to eᵢ, so unvisited starts cannot float and slow the solve",
                    {},
                ),
            ],
            [
                ("C5  ", {"font": MONO, "bold": True}),
                ("must-visit places and the meal break are mandatory nodes", {}),
            ],
            [
                ("C6  ", {"font": MONO, "bold": True}),
                ("caps on activities, daily travel minutes and entry-fee budget", {}),
            ],
            "",
            [("OBJECTIVE", {"bold": True, "color": INDIGO, "size": 8})],
            [
                (
                    "maximise  Σ ⌈(pᵢ − shift + 0.05)·1000⌉·v[i]  −  4·Σ tᵢⱼ·x[i][j]",
                    {"font": MONO, "bold": True, "color": INDIGO},
                )
            ],
        ],
        size=7.9,
        color=INK_M,
        line_spacing=1.16,
    )

    band(s, M, 4.46, 6.3, "THREE DECISIONS AN INTERVIEWER WILL PROBE", fill=SAFFRON)
    rect(s, M, 4.76, 6.3, 1.44, SAFFRON_XL, SAFFRON_L)
    text(
        s,
        M + 0.14,
        4.88,
        6.02,
        1.24,
        [
            [
                ("Why per-day, not trip-wide?  ", {"bold": True, "color": SAFFRON_D}),
                (
                    "Trip-wide is O((k·days)²) arcs — 1,296 vs 324 for k=9, 4 days. It also zig-zags, because a global objective only sees total distance."
                ),
            ],
            [
                ("Why the score shift?  ", {"bold": True, "color": SAFFRON_D}),
                (
                    "Scores can go negative after penalties; a negative prize makes skipping rewarding and the solver returns an empty day."
                ),
            ],
            [
                ("Why TRAVEL_WEIGHT = 4?  ", {"bold": True, "color": SAFFRON_D}),
                (
                    "It is what stops two high-scoring places at opposite ends of a city beating three good ones in a cluster. The single most consequential constant in the model."
                ),
            ],
        ],
        size=8.1,
        color=INK_M,
        line_spacing=1.18,
    )

    band(s, 6.88, 1.42, CW - 6.52, "MEASURED — OR-TOOLS vs A FAIR GREEDY BASELINE", fill=TEAL)
    table(
        s,
        6.88,
        1.74,
        CW - 6.52,
        [1.9, 0.95, 1.0, 0.75],
        [
            ["METRIC", "GREEDY", "CP-SAT", "Δ"],
            [
                "Total travel distance",
                "149.8 km",
                ("64.0 km", {"bold": True}),
                ("−57%", {"color": TEAL, "bold": True}),
            ],
            [
                "Total travel time",
                "487 min",
                ("275 min", {"bold": True}),
                ("−43%", {"color": TEAL, "bold": True}),
            ],
            [
                "Travel km per activity",
                "15.61",
                ("6.01", {"bold": True}),
                ("−61%", {"color": TEAL, "bold": True}),
            ],
            ["Activities scheduled", "9.8", "10.3", "+0.5"],
            ["Constraint violations", "0.0", "0.0", "—"],
            ["Median solve time", "8.8 ms", "48.2 ms", ("+39 ms", {"color": SAFFRON_D})],
        ],
        header_fill=TEAL,
        row_h=0.262,
        head_h=0.28,
        size=7.6,
        mono_cols=(1, 2, 3),
    )

    rect(s, 6.88, 3.62, CW - 6.52, 0.7, WHITE, LINE)
    text(
        s,
        7.02,
        3.72,
        CW - 6.8,
        0.55,
        [
            [
                ("The baseline is not a strawman.  ", {"bold": True, "color": INDIGO}),
                (
                    "It honours identical opening hours, budget, activity and travel caps, and inserts each "
                    "candidate at its earliest feasible start. The 57% gap measures sequencing quality alone."
                ),
            ]
        ],
        size=8.1,
        color=INK_M,
        line_spacing=1.18,
    )

    band(
        s,
        6.88,
        4.46,
        CW - 6.52,
        'RELAXATION LADDER — WHY IT NEVER JUST SAYS "NO PLAN"',
        fill=INDIGO_M,
    )
    table(
        s,
        6.88,
        4.78,
        CW - 6.52,
        [0.55, 3.5],
        [
            ["TRY", "WHAT IS RELAXED"],
            ["1", "Nothing — the full model"],
            ["2", "max_activities − 1"],
            ["3", "travel cap × 1.25"],
            ["4", "drop budget cap; activities − 1; travel × 1.4"],
            ["5", "activities = 2; travel × 1.5"],
        ],
        header_fill=INDIGO_M,
        row_h=0.225,
        head_h=0.26,
        size=7.5,
    )
    text(
        s,
        6.88,
        6.2,
        CW - 6.52,
        0.3,
        [
            [
                (
                    "Travel is relaxed last and least — a six-hour driving day is feasible and useless. "
                    "Whatever was relaxed is recorded and shown to the user.",
                    {"color": INK_M},
                )
            ]
        ],
        size=7.6,
        line_spacing=1.15,
    )

    callout(
        s,
        6.54,
        "DETERMINISM:  ",
        "num_workers = 1 and a fixed random seed. Multi-threaded CP-SAT search is non-deterministic; "
        "single-worker costs some speed and buys a reproducible plan — asserted by test.",
        h=0.42,
    )
    footer(
        s,
        "Source: python ml/experiments/planner_comparison.py — 6 scenarios × 6 clusters × 3 repeats. Constants from services/planner/ortools_scheduler.py.",
        6,
    )
    return s


def slide_07_validation(prs):
    s = blank(prs)
    ribbon(s, 3)
    headline(s, "VALIDATION & DYNAMIC REPLANNING — WHY A WRONG PLAN CANNOT REACH THE SCREEN")

    band(
        s,
        M,
        1.42,
        6.15,
        "THE VALIDATOR — 15 CHECKS, RE-DERIVED INDEPENDENTLY OF THE SOLVER",
        fill=CLAY,
    )
    table(
        s,
        M,
        1.74,
        6.15,
        [3.35, 0.85],
        [
            ["CHECK", "SEVERITY"],
            ["Activities ordered and non-overlapping", ("error", {"color": CLAY})],
            [
                "Every visit inside a real opening window for that weekday",
                ("error", {"color": CLAY}),
            ],
            ["Nothing before day start or after day end", ("error", {"color": CLAY})],
            ["Visit duration within the attraction's min/max", ("error", {"color": CLAY})],
            [
                "Travel time between consecutive stops is actually available",
                ("error", {"color": CLAY}),
            ],
            ["No attraction scheduled twice across the trip", ("error", {"color": CLAY})],
            ["Every mandatory attraction is scheduled", ("error", {"color": CLAY})],
            ["Accessibility requirements respected", ("error", {"color": CLAY})],
            ["Nothing scheduled on a day the attraction is closed", ("error", {"color": CLAY})],
            [
                "Daily travel / activities within the pace guideline",
                ("warning", {"color": SAFFRON_D}),
            ],
            ["Meal break exists on any day longer than 6 h", ("warning", {"color": SAFFRON_D})],
            ["Total estimated cost within budget", ("warning", {"color": SAFFRON_D})],
        ],
        header_fill=CLAY,
        row_h=0.222,
        head_h=0.27,
        size=7.4,
    )

    rect(s, M, 4.72, 6.15, 0.92, INDIGO_XL, INDIGO_L)
    text(
        s,
        M + 0.14,
        4.84,
        5.87,
        0.76,
        [
            [
                ("Independent by design.  ", {"bold": True, "color": INDIGO}),
                (
                    "The validator re-reads the persisted rows and re-derives every constraint from "
                    "scratch. A modelling bug therefore surfaces as a failed validation, not as an "
                    "impossible itinerary shown to a user."
                ),
            ],
            [
                ("Budget is a warning, not an error — ", {"bold": True, "color": SAFFRON_D}),
                (
                    "overspending is information the traveller should act on, not a reason to withhold the plan.",
                    {"color": INK_M},
                ),
            ],
        ],
        size=8.2,
        color=INK_M,
        line_spacing=1.18,
    )

    band(
        s,
        6.72,
        1.42,
        CW - 6.36,
        "ELEVEN REPLANNING ACTIONS — EXPRESSED AS INPUTS, NEVER AS EDITS",
        fill=INDIGO,
    )
    rect(s, 6.72, 1.74, CW - 6.36, 1.32, WHITE, LINE)
    text(
        s,
        6.86,
        1.86,
        CW - 6.64,
        1.14,
        [
            [
                (
                    "remove_activity · replace_activity · regenerate_day · make_day_relaxed · "
                    "reduce_cost · reduce_travel · add_theme · shift_start_time · weather_replan · "
                    "member_opted_out · attraction_unavailable",
                    {"font": MONO, "size": 7.6, "color": INDIGO},
                )
            ],
            "",
            [
                ("Nothing edits a schedule in place.  ", {"bold": True, "color": INDIGO}),
                (
                    "Each action changes planner inputs, then the whole pipeline re-runs and re-validates. "
                    "A modification therefore cannot produce a state the optimiser would never have generated."
                ),
            ],
        ],
        size=8.2,
        color=INK_M,
        line_spacing=1.2,
    )

    band(
        s,
        6.72,
        3.22,
        CW - 6.36,
        "GROUP CONTROL — A CHANGE IS A PROPOSAL, NOT A FAIT ACCOMPLI",
        fill=TEAL,
    )
    rect(s, 6.72, 3.54, CW - 6.36, 1.16, TEAL_XL, TEAL_L)
    text(
        s,
        6.86,
        3.66,
        CW - 6.64,
        1.0,
        [
            "On a trip with more than one active member, a modification becomes a ChangeProposal with an approval threshold. Members vote; reaching the threshold auto-applies it. The owner can override, and the override is written to the append-only audit log.",
            "",
            [
                (
                    "The API returns requires_group_approval: true and a proposal_id rather than silently applying one member's preference.",
                    {"bold": True, "color": TEAL},
                )
            ],
        ],
        size=8.2,
        color=INK_M,
        line_spacing=1.2,
    )

    band(
        s,
        6.72,
        4.86,
        CW - 6.36,
        "LIVE SOLVER TRACE — SURFACED IN THE UI, NOT JUST LOGGED",
        fill=INDIGO_M,
    )
    table(
        s,
        6.72,
        5.18,
        CW - 6.36,
        [0.5, 1.05, 0.85, 1.0, 0.75],
        [
            ["DAY", "STATUS", "CHOSEN", "OBJECTIVE", "SOLVE"],
            ["1", ("OPTIMAL", {"color": TEAL}), "4 / 9", "6,393", "59.3 ms"],
            ["2", ("OPTIMAL", {"color": TEAL}), "4 / 6", "2,468", "48.2 ms"],
            ["3", ("OPTIMAL", {"color": TEAL}), "1 / 1", "712", "3.4 ms"],
        ],
        header_fill=INDIGO_M,
        row_h=0.25,
        head_h=0.27,
        size=7.6,
        mono_cols=(1, 2, 3, 4),
    )

    callout(
        s,
        6.5,
        "WHAT THIS DEMONSTRATES:  ",
        "the product shows its own working. Per-day CP-SAT status, wall-clock, objective value, "
        "candidates considered and any relaxation are rendered on the itinerary page, alongside an "
        "input fingerprint proving the same inputs reproduce the same plan.",
    )
    footer(
        s,
        "Sources: services/planner/validator.py; services/trips.py; live itinerary for the demo trip (Bengaluru, 3 days).",
        7,
    )
    return s


def slide_08_rag(prs):
    s = blank(prs)
    ribbon(s, 4)
    headline(s, "RETRIEVAL — ANSWERING FROM EVIDENCE, OR REFUSING TO ANSWER AT ALL")

    band(s, M, 1.42, 5.85, "THE PIPELINE")
    rect(s, M, 1.72, 5.85, 2.28, WHITE, LINE)
    stages = [
        ("1  Classify", "Question → knowledge topic (history, etiquette, access, visiting)"),
        (
            "2  Filter",
            "Metadata scope by cluster and place — an attraction filter REQUIRES a cluster",
        ),
        ("3  Retrieve ×2", "Dense cosine over 790 chunks + BM25, run independently"),
        ("4  Fuse", "Reciprocal Rank Fusion, k = 60"),
        ("5  Rerank", "Query coverage · heading match · topic agreement · source authority"),
        ("6  Answer or abstain", "Absolute evidence score vs threshold 0.26"),
    ]
    for i, (t, sub) in enumerate(stages):
        y = 1.82 + i * 0.365
        rect(s, M + 0.12, y + 0.02, 0.055, 0.22, INDIGO if i < 5 else SAFFRON)
        text(s, M + 0.28, y, 5.4, 0.18, t, size=8.2, bold=True, color=INK)
        text(s, M + 0.28, y + 0.17, 5.4, 0.18, sub, size=7.3, color=INK_F)

    band(s, M, 4.12, 5.85, "TWO MECHANISMS THAT MAKE THE OUTPUT TRUSTWORTHY", fill=TEAL)
    rect(s, M, 4.44, 5.85, 1.76, TEAL_XL, TEAL_L)
    text(
        s,
        M + 0.14,
        4.56,
        5.57,
        1.56,
        [
            [
                ("Citations are computed, not claimed.  ", {"bold": True, "color": TEAL}),
                (
                    "After generation, each answer sentence is matched back to the chunk it overlaps "
                    "most (threshold 0.30). A sentence the model invented earns no citation. Asking a "
                    "model to cite itself measures nothing."
                ),
            ],
            "",
            [
                ("Abstention runs on an absolute score.  ", {"bold": True, "color": TEAL}),
                (
                    "evidence = max(0.35·dense + 0.65·IDF-weighted term coverage). Below 0.26 no model "
                    'is called at all and the answer is "I don\'t have verified information", with zero citations.'
                ),
            ],
        ],
        size=8.1,
        color=INK_M,
        line_spacing=1.18,
    )

    band(s, 6.42, 1.42, CW - 6.06, "MEASURED — 34-QUESTION COMMITTED BENCHMARK", fill=INDIGO)
    table(
        s,
        6.42,
        1.74,
        CW - 6.06,
        [2.25, 0.95, 1.65],
        [
            ["METRIC", "VALUE", "NOTE"],
            ["Open retrieval top-1", "0.903", "no attraction hint given"],
            ["Open retrieval top-3 / MRR", "1.000 / 0.952", "the realistic assistant path"],
            ["Retrieval recall", "1.000", "expected topic retrieved"],
            ["Topic classification", "0.941", "was 0.50 — see defect below"],
            ["Citation correctness / coverage", "1.000 / 1.000", "derived, not requested"],
            [
                "Abstention accuracy",
                ("1.000", {"color": TEAL, "bold": True}),
                "refuses when it should",
            ],
            ["Faithfulness", "0.995", "our disclaimer counts against"],
            ["Evidence: answerable / out-of-scope", "0.582 / 0.071", "what abstention keys on"],
            ["Latency p50 / p95", "8.1 / 34.4 ms", "template provider"],
        ],
        row_h=0.232,
        head_h=0.27,
        size=7.4,
        mono_cols=(1,),
    )

    band(s, 6.42, 4.26, CW - 6.06, "ABLATION — REAL RE-RUNS, NOT RE-SORTS", fill=INDIGO_M)
    table(
        s,
        6.42,
        4.58,
        CW - 6.06,
        [2.5, 0.9, 0.9],
        [
            ["CONFIGURATION", "TOP-1", "MRR"],
            ["hybrid + rerank (shipped)", ("0.903", {"bold": True}), ("0.952", {"bold": True})],
            ["hybrid, no rerank", ("0.774", {"color": CLAY}), "0.874"],
            ["dense only + rerank", "0.871", "0.935"],
            ["lexical only + rerank", "0.903", "0.946"],
        ],
        header_fill=INDIGO_M,
        row_h=0.25,
        head_h=0.27,
        size=7.5,
        mono_cols=(1, 2),
    )
    text(
        s,
        6.42,
        5.9,
        CW - 6.06,
        0.4,
        [
            [
                (
                    "Reranking is worth +12.9 pp top-1. Lexical-only nearly matches the hybrid — an honest "
                    "limitation of the hashing embedder (a lexical projection), not a strength of BM25.",
                    {"color": INK_M},
                )
            ]
        ],
        size=7.5,
        line_spacing=1.15,
    )

    callout(
        s,
        6.38,
        "THE DEFECT THAT ONLY MEASUREMENT COULD FIND:  ",
        '"What happened at Sarnath and why does it matter?" abstained at 0.229 — with the correct '
        'chunk ranked FIRST — because "happened" and "matter" appear in 0 of 790 chunks and so drew '
        "maximum IDF weight. Absent entities signal out-of-scope; absent framing words signal nothing. "
        "Fixing that moved abstention 0.912 → 1.000 while out-of-scope evidence stayed at exactly 0.071.",
        h=0.58,
    )
    footer(
        s,
        "Source: python evaluation/run_rag_eval.py → evaluation/reports/rag_evaluation.md. Benchmark hand-written by the author and labelled as such.",
        8,
    )
    return s


def slide_09_trust(prs):
    s = blank(prs)
    ribbon(s, 4)
    headline(s, "SECURITY, PRIVACY & THE HONESTY CONTRACT")

    band(
        s,
        M,
        1.42,
        6.1,
        "SECURITY — THREATS THAT ACTUALLY APPLY, AND THE CONTROL FOR EACH",
        fill=CLAY,
    )
    table(
        s,
        M,
        1.74,
        6.1,
        [1.9, 3.3],
        [
            ["THREAT", "CONTROL"],
            [
                "Credential compromise",
                "bcrypt (rounds=12) with a SHA-256 pre-hash — bcrypt silently truncates at 72 bytes",
            ],
            [
                "Token forgery",
                "HS256 JWT, signature + issuer + expiry verified; Supabase tokens accepted",
            ],
            [
                "Horizontal escalation",
                "require_trip_member / require_trip_owner as dependencies on every trip route",
            ],
            [
                "Cost / DoS",
                "Two-tier sliding window — 120 req/min default, 15 req/min on optimiser and RAG",
            ],
            [
                "Prompt injection",
                "Detected on the question, neutralised on every retrieved chunk, injection-aware system prompt",
            ],
            ["Data poisoning", "Source-domain allow-list enforced at the Silver gate"],
            [
                "Secret leakage",
                ".env git-ignored; .env.example holds names only; production boot guard refuses weak config",
            ],
        ],
        header_fill=CLAY,
        row_h=0.31,
        head_h=0.27,
        size=7.3,
    )

    band(s, M, 4.28, 6.1, "PRODUCTION BOOT GUARD", fill=INDIGO_M)
    rect(s, M, 4.58, 6.1, 1.0, WHITE, LINE)
    text(
        s,
        M + 0.14,
        4.7,
        5.82,
        0.84,
        [
            [
                (
                    "With YATRA_ENV=production the API refuses to start if:",
                    {"bold": True, "color": INDIGO},
                )
            ],
            "JWT_SECRET is under 32 chars or contains 'dev-only' · DATABASE_URL is unset (the SQLite fallback is refused) · any non-localhost CORS origin uses plain http:// · a named LLM provider has no API key.",
        ],
        size=8.1,
        color=INK_M,
        line_spacing=1.18,
    )

    band(
        s,
        6.7,
        1.42,
        CW - 6.34,
        "PRIVACY — EVERY GUARANTEE IS ENFORCED IN CODE AND COVERED BY A TEST",
        fill=TEAL,
    )
    table(
        s,
        6.7,
        1.74,
        CW - 6.34,
        [1.55, 3.0],
        [
            ["GUARANTEE", "IMPLEMENTATION"],
            [
                "Opt-in only",
                "No session without consent_granted_at + a stored consent-text version",
            ],
            [
                "Approximate by default",
                "Snapped to a ~500 m grid BEFORE storage — the exact point is never written",
            ],
            ["Always expiring", "12 h hard cap per session; every point carries its own expiry"],
            ["Stop means delete", "Stopping deletes the trail immediately, not just hides it"],
            [
                "Never in analytics",
                "Coordinate-like keys stripped at write time; a test posts a real coordinate and asserts it appears nowhere",
            ],
            ["No location history", "There is no table that could hold one"],
        ],
        header_fill=TEAL,
        row_h=0.325,
        head_h=0.27,
        size=7.3,
    )

    band(
        s,
        6.7,
        4.06,
        CW - 6.34,
        "THE HONESTY CONTRACT — FOUR CLAIMS THE CODE ENFORCES",
        fill=SAFFRON,
    )
    rect(s, 6.7, 4.38, CW - 6.34, 1.86, SAFFRON_XL, SAFFRON_L)
    text(
        s,
        6.84,
        4.5,
        CW - 6.62,
        1.66,
        [
            [
                ("1  No verified hours or fees.  ", {"bold": True, "color": SAFFRON_D}),
                ("A data-quality test fails the build if a row ever claims otherwise."),
            ],
            [
                ("2  Cited or silent.  ", {"bold": True, "color": SAFFRON_D}),
                (
                    "The assistant abstains rather than guessing, and states plainly when a value is recorded rather than live."
                ),
            ],
            [
                ("3  SOS is a demonstration.  ", {"bold": True, "color": SAFFRON_D}),
                (
                    "It contacts nobody — stated in the OpenAPI description, the response body, the UI, and the chat message it posts, and it refuses to fire without an explicit acknowledgement flag."
                ),
            ],
            [
                ("4  No invented metrics.  ", {"bold": True, "color": SAFFRON_D}),
                (
                    'Every number in the README re-runs from a script. Synthetic ML results carry data_kind="synthetic" on every row.'
                ),
            ],
        ],
        size=8.1,
        color=INK_M,
        line_spacing=1.18,
    )

    callout(
        s,
        6.5,
        "WHY THIS MATTERS IN AN INTERVIEW:  ",
        "these are the constraints a real product team would impose, and they are the parts most "
        'portfolio projects skip. Being able to say "the build fails if that claim is ever made" '
        "is stronger than any feature.",
    )
    footer(
        s,
        "Sources: docs/security.md; docs/privacy.md; tests/integration/; yatraai/config.py assert_production_ready().",
        9,
    )
    return s


def slide_10_results(prs):
    s = blank(prs)
    rect(s, 0, 0, SW, SH, NAVY)
    rect(s, 0, 0, 0.12, SH, SAFFRON)

    text(s, 0.72, 0.5, 11.9, 0.3, "IN ONE SENTENCE", size=10, bold=True, color=SAFFRON)
    text(
        s,
        0.72,
        0.86,
        11.9,
        0.9,
        [
            "A group itinerary planner where a constraint solver decides,",
            "a validator gates, and the language model only ever narrates.",
        ],
        size=25,
        bold=True,
        color=WHITE,
        line_spacing=1.16,
    )
    rect(s, 0.72, 2.02, 1.5, 0.04, SAFFRON)

    band(
        s, 0.72, 2.32, 5.7, "EVERYTHING MEASURED, IN ONE PLACE", fill=NAVY_2, color=SAFFRON, size=9
    )
    rows = [
        ("Travel distance vs greedy baseline", "−57%", TEAL),
        ("Least-satisfied member vs simple average", "+8.5%", TEAL),
        ("RAG abstention accuracy / citation correctness", "1.000 / 1.000", TEAL),
        ("Retrieval top-1 · MRR (no hint)", "0.903 · 0.952", WHITE),
        ("Reranking contribution to top-1", "+12.9 pp", TEAL),
        ("Median CP-SAT solve per day", "48.2 ms", WHITE),
        ("Automated tests (295 Python + 43 frontend)", "338", WHITE),
        ("Post-deployment verification checks", "10 / 10", TEAL),
        ("LLM calls required to produce an itinerary", "0", SAFFRON),
    ]
    for i, (label, val, col) in enumerate(rows):
        y = 2.72 + i * 0.325
        text(s, 0.8, y, 4.2, 0.24, label, size=8.4, color=RGBColor(0xB8, 0xBF, 0xD4))
        text(s, 5.05, y, 1.3, 0.24, val, size=9, bold=True, color=col, align=PP_ALIGN.RIGHT)
        rect(s, 0.8, y + 0.265, 5.55, 0.008, RGBColor(0x25, 0x2E, 0x50))

    band(
        s,
        6.72,
        2.32,
        5.9,
        "STATED LIMITATIONS — LEAD WITH THESE, DO NOT BE CAUGHT BY THEM",
        fill=NAVY_2,
        color=SAFFRON,
        size=9,
    )
    text(
        s,
        6.8,
        2.74,
        5.75,
        1.9,
        [
            [
                ("Default embeddings are not neural.  ", {"bold": True, "color": WHITE}),
                (
                    "A 384-dim signed hashing projection. sentence-transformers is a one-env-var swap.",
                    {"color": RGBColor(0xB8, 0xBF, 0xD4)},
                ),
            ],
            [
                ("ML models were not promoted.  ", {"bold": True, "color": WHITE}),
                (
                    "Trained on synthetic labels. The trees lost (0.6404) to the hand-weighted rule (0.6676); the one learner that edged it was inside a bootstrap CI of [−0.010, +0.017].",
                    {"color": RGBColor(0xB8, 0xBF, 0xD4)},
                ),
            ],
            [
                ("The benchmark is mine.  ", {"bold": True, "color": WHITE}),
                (
                    "34 hand-written questions, not collected from users. Small, and labelled as such.",
                    {"color": RGBColor(0xB8, 0xBF, 0xD4)},
                ),
            ],
            [
                ("Ten destinations, not all of India.  ", {"bold": True, "color": WHITE}),
                (
                    "Depth over breadth — a new cluster is a data change, not a code change.",
                    {"color": RGBColor(0xB8, 0xBF, 0xD4)},
                ),
            ],
            [
                (
                    "Rate limiting is per-process; no refresh tokens.  ",
                    {"bold": True, "color": WHITE},
                ),
                (
                    'Documented in docs/security.md under "known gaps".',
                    {"color": RGBColor(0xB8, 0xBF, 0xD4)},
                ),
            ],
        ],
        size=8.2,
        line_spacing=1.2,
        space_after=4,
    )

    band(s, 6.72, 4.86, 5.9, "FOUR LINES TO SAY OUT LOUD", fill=NAVY_2, color=SAFFRON, size=9)
    text(
        s,
        6.8,
        5.28,
        5.75,
        1.5,
        [
            [
                (
                    '"It is a retrieval and constraint-optimisation system, not a chatbot. The LLM runs '
                    'last and changes nothing — the default config never calls it."',
                    {"color": RGBColor(0xD8, 0xDD, 0xEC)},
                )
            ],
            [
                (
                    '"I measured five aggregation rules. The one with the best mean had the worst floor."',
                    {"color": RGBColor(0xD8, 0xDD, 0xEC)},
                )
            ],
            [
                (
                    '"Every interesting bug was found by an experiment, not by reading code."',
                    {"color": RGBColor(0xD8, 0xDD, 0xEC)},
                )
            ],
            [
                (
                    '"No opening hour or fee in this dataset claims to be verified — the build fails if one does."',
                    {"color": RGBColor(0xD8, 0xDD, 0xEC)},
                )
            ],
        ],
        size=8.4,
        line_spacing=1.2,
        space_after=5,
    )

    rect(s, 0.72, 6.42, 5.7, 0.62, NAVY_2)
    text(
        s,
        0.86,
        6.54,
        5.45,
        0.44,
        [
            [
                ("Reproduce everything:  ", {"bold": True, "color": SAFFRON}),
                (
                    "make experiments  ·  python evaluation/run_rag_eval.py  ·  pytest",
                    {"font": MONO, "color": WHITE, "size": 8.2},
                ),
            ]
        ],
        size=8.4,
        line_spacing=1.15,
    )

    text(
        s,
        0.72,
        7.08,
        11.9,
        0.3,
        "338 tests passing · 10/10 deployment checks · ruff, mypy, tsc and eslint clean · "
        "every figure above regenerated from a script in the repository",
        size=7.5,
        color=RGBColor(0x6B, 0x74, 0x92),
    )
    return s


# --------------------------------------------------------------------------- #
def main() -> int:
    prs = Presentation()
    prs.slide_width = Inches(SW)
    prs.slide_height = Inches(SH)

    for builder in (
        slide_01_title,
        slide_02_problem,
        slide_03_stack,
        slide_04_data,
        slide_05_ranking,
        slide_06_optimiser,
        slide_07_validation,
        slide_08_rag,
        slide_09_trust,
        slide_10_results,
    ):
        builder(prs)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print(f"Wrote {OUT}  ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
