# Interview readiness

## Three-minute demo script

**0:00 — Frame the problem (20 s)**

> "Group trips fail on coordination, not inspiration. Four people want four different things,
> someone always gets ignored, and the plan ignores opening hours and travel time. If you ask an
> LLM to plan Agra it will happily send you to the Taj Mahal on a Friday — it's closed — and
> invent a ticket price. So the design question was: how do you keep a language model away from
> anything that has to be *correct*?"

**0:20 — Show the answer (30 s)** — landing page, the five-stage strip

> "Structured data owns the facts. Deterministic ranking selects. OR-Tools schedules. A validator
> gates it. Only then does the model narrate. Turn the model off entirely and the product still
> works — that's the default this test suite runs against."

**0:50 — Generate a real itinerary (45 s)** — demo account → trip → *Regenerate*

> "Three members with deliberately conflicting preferences. That's a validated plan: 66 constraint
> checks passed. Every stop has a time, a travel leg, a cost band and a reason."

Expand **Why was this selected?**

> "That's not generated text. Those are the nine score components the optimiser actually used —
> interest match, fairness, weather, accessibility. The UI just renders the stored numbers."

**1:35 — Fairness (30 s)** — the summary panel

> "Jain's fairness index, and the floor guaranteed to the *least*-satisfied member. I measured
> five aggregation methods on adversarial group profiles. A simple average scores the worst-served
> person at 0.481. Iterative fair selection gets 0.522 for a 1.1% cost in average satisfaction.
> Pure max-min scores higher but flattens the trip. That trade-off is measured, not asserted."

**2:05 — Honesty (30 s)** — open a place drawer

> "History, significance, etiquette, sources — and this badge. No opening-hour or fee row in this
> dataset claims to be verified, because I authored it. A data-quality test fails the build if one
> ever does."

Ask the assistant something out of scope.

> "It abstains. Citations are computed from lexical overlap between each sentence and the
> retrieved chunk, so the model can't cite a source it didn't use."

**2:35 — Land it (25 s)**

> "57% less travel than a greedy baseline, measured across six scenarios. 330 tests. Every number
> in the README comes from a script in the repo. And every interesting bug in this project was
> found by the experiments, not by me reading the code — including one where the assistant
> refused to quote a ticket price it was holding in memory."

---

## Resume bullets

Pick 3–4; each maps to something demonstrable.

- Built a group travel planning platform where an **OR-Tools CP-SAT** scheduler (prize-collecting
  TSP with time windows) reduced itinerary travel distance **57%** versus a greedy baseline across
  six measured scenarios, at a median 48 ms solve.
- Designed a **fairness-aware group recommender** using Jain's fairness index and iterative
  submodular-style selection, raising the least-satisfied member's satisfaction **8.5%** over a
  simple average for a **1.1%** cost in mean satisfaction — measured on five adversarial group profiles.
- Implemented **hybrid RAG** (dense + BM25 fused with reciprocal rank fusion, feature-based
  reranking) over a cited knowledge base, achieving **0.90 top-1 / 0.95 MRR** retrieval and
  **1.00 abstention accuracy** on a 34-question benchmark, with citations derived from
  sentence–chunk overlap so they cannot be fabricated.
- Engineered a **Bronze/Silver/Gold pipeline** with seven executable Pandera contracts and twelve
  runtime data-quality checks gating both CI and the Airflow DAG; contract failures surfaced two
  real defects before they reached the planner.
- Architected every external dependency (LLM, embeddings, routing, weather, database) behind a
  **provider abstraction with a measured fallback**, so the product delivers validated itineraries
  fully offline; the entire 295-test Python suite runs with no network and no Docker.
- Shipped **consent-based location sharing** with coordinates snapped to ~500 m *before storage*,
  automatic expiry, immediate deletion on stop, and a write-time guard preventing coordinates from
  ever entering analytics — each guarantee covered by a test.

---

## Questions you will be asked

### "Why OR-Tools instead of a heuristic?"

The problem is genuinely a prize-collecting TSP with time windows: you choose *which* attractions
as well as their order, under opening hours. `AddCircuit` expresses sequencing and selection in
one constraint — a node opts out via its self-loop — with no subtour-elimination family and no
big-M. I still built the greedy baseline because you cannot claim an optimiser is worth 39 ms
without measuring it. It came out 57% better on travel, and building it also exposed a meal-break
bug in shared code.

### "Why not fine-tune a model to rank attractions?"

There is no labelled data. Nobody has told me which itineraries groups enjoyed. Any model I
trained would be fitted to labels I invented, and its accuracy would measure how well it
reproduced my own heuristic. `ml/` has the full training pipeline against clearly-labelled
synthetic data, recorded as `data_kind="synthetic"` on every run, ready for the day feedback
exists. The rule-based ranker stays in production precisely because of that.

### "How do you stop the LLM hallucinating?"

Structurally, not by prompting. It never runs before stage 8, and by then the itinerary is already
validated. Its output is prose *beside* the timeline, not the timeline. For the assistant, the
answer is constrained to retrieved context, and **citations are computed after generation** from
lexical overlap between each sentence and each chunk — so a sentence the model invented earns no
citation. Below an absolute evidence threshold it abstains without calling a model at all.

### "How does abstention actually work?"

My first attempt thresholded on the fused RRF score and could not separate answerable from
unanswerable questions at all — RRF encodes *ordering*, so its top score is roughly constant
regardless of whether the corpus can answer. I replaced it with an absolute score blending dense
similarity with **IDF-weighted query-term coverage**. The IDF weighting is the part that works:
plain coverage scored "best restaurant in Reykjavik" respectably against a Bengaluru corpus
because "best" appears everywhere. Weighted by rarity, the absent terms dominate.

Then it over-corrected, and that is the more interesting half. Giving *every* absent term maximum
weight assumes absence always means "out of scope". It doesn't. "What **happened** at Sarnath and
why does it **matter**?" scored 0.229 and abstained — with the correct chunk ranked first — purely
because "happened" and "matter" have document frequency zero across all 790 chunks. A factual
catalogue entry never uses words like those, however well it answers the question. So the score
now drops temporal deixis and question-framing words before measuring, while every out-of-scope
entity term keeps full weight.

The measurement that tells me I fixed the right thing: abstention accuracy went 0.912 → 1.000 and
mean answerable evidence 0.521 → 0.582, while mean **out-of-scope** evidence stayed at exactly
0.071. If the gate had simply loosened, that last number would have moved.

### "What went wrong?"

Five things, all found by measurement:

1. **Topic classification at 50%.** My regexes used `\b(histor)\b` — the trailing word boundary
   means it can *never* match "history". Fixed with `\w*` stems: 0.50 → 0.94.
2. **A 401 km Delhi–Agra itinerary.** Size-balancing in the day clusterer was dragging Delhi sites
   into the Agra day. Added a rule that refuses any balancing move stranding a point more than
   25 km from where it belongs. Same scenario now plans at 54 km.
3. **Every Delhi–Agra day infeasible.** A single trip-wide base sat 115 km from everything, so no
   day could satisfy the travel cap. Now each day has its own base with an explicit "you'll need to
   move accommodation" note.
4. **The assistant abstained on a fee it was holding.** "What's the ticket price in rupees today
   at 4pm exactly?" scored 0.183 against a 0.26 gate. Two independent causes: the time words drew
   maximum IDF weight for being absent, and separately the catalogue writes `Entry: … Rs.50-Rs.250`
   and never the word "price". Fixed with non-evidential term handling plus a small hand-checked
   alias map — guarded by a test that a question sharing "current/price/today" but asking about
   *stock* prices must still abstain.
5. **A benchmark question demanding live data got no disclaimer at all.** The "verify before
   visiting" note was keyed on which chunk came back rather than on what was asked. Answering
   "what's the price right now" from a static catalogue without saying so is the most misleading
   thing this system could do, so it is now keyed on the question.

None of these were visible from reading the code. (4) and (5) came from a single failing cell in
the evaluation report — `Time-sensitive answers carried an unverified warning: 0/1` — which is
the argument for building the harness before believing the system works.

### "How would you scale this to 500 destinations?"

The data model already supports it — adding destinations is a pipeline task, not a code change.
What would break first:

- **Retrieval.** In-Python cosine over 790 chunks is fine; at 40,000 it needs pgvector's HNSW
  index. The `VectorType` already maps to `pgvector.Vector` on Postgres, so it is an index and a
  query change, not a rewrite.
- **Routing.** The matrix is `O(k²)` per day but k is capped at 9 by design, so this is unaffected.
  The leg cache matters more as trip volume grows.
- **Scoring.** Currently scores every candidate in a cluster. Beyond a few hundred per cluster I
  would pre-filter on the Gold feature table before scoring.

The genuinely hard part is not scale — it is that data quality does not survive scraping. Every
attraction here was hand-checked against a cited source. At 500 destinations you need either
editorial staff or a source-of-truth partnership.

### "Why SQLite and Postgres?"

Four `TypeDecorator`s make one schema serve both. Concretely: `pytest` needs no Docker, CI is
fast, and a reviewer can run the whole product offline. Production still gets `JSONB`, native
`uuid` and pgvector. The cost is that the vector search path has two implementations — worth it
for a test suite that runs in 40 seconds.

### "Show me something you're not happy with."

Lexical retrieval alone nearly matches the hybrid on my benchmark — 0.903 vs 0.903 top-1. That is
not a win for BM25; it means my default hashing embedder is essentially a lexical projection, so
the "dense" arm is correlated rather than complementary. A real sentence encoder should widen the
gap on paraphrased questions. I have not run that experiment, so the README says so instead of
claiming it.

Also: my faithfulness metric is lexical-overlap based. It reliably catches fabrication but cannot
catch a fluent paraphrase that subtly changes meaning. An NLI judge would be strictly better.

### "What would you build next?"

1. **Close the feedback loop.** Actual-spend capture exists; the accuracy metric appears once
   there is data. That is also the first genuine training signal for a learned ranker.
2. **NLI-based faithfulness** to replace the lexical proxy.
3. **Multi-city trips as a first-class concept** rather than the per-day-base workaround.
4. **Realtime collaboration** via Supabase Realtime — polling is adequate for eight people and
   nothing more, and I would not add the infrastructure before the product needed it.

---

## Concepts, if pressed

**Jain's fairness index** `J(x) = (Σxᵢ)²/(n·Σxᵢ²)`, bounded (0,1]. 1.0 = perfect equality,
1/n = one member served. Standard in resource allocation, and it has the property I wanted:
scale-invariant, so it measures *distribution* rather than magnitude.

**Reciprocal rank fusion** `score(d) = Σᵣ 1/(k + rankᵣ(d))`, k = 60. Chosen because dense cosine
and BM25 scores live on incomparable scales; RRF uses only ranks, so it needs no calibration.
Its weakness is that it discards score magnitude — which is exactly why it is useless as an
abstention signal, and why abstention uses a separate absolute measure.

**Prize-collecting TSP with time windows.** TSP where nodes are optional and each carries a prize;
the objective trades collected prize against travel cost, subject to time windows. NP-hard; CP-SAT
solves our instances (≤ 11 nodes) to optimality in tens of milliseconds.

**Medallion architecture.** Bronze = raw, verbatim, content-hashed. Silver = cleaned, validated,
deduplicated. Gold = features and aggregates. The value is that each promotion is a gate: a bad
seed edit fails at Silver with a named contract violation, rather than silently producing a wrong
itinerary three layers downstream.
