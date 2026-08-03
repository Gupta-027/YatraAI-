# RAG architecture

## The corpus is derived, not authored twice

The knowledge base is generated from the **same rows the planner reasons about**
(`seed/knowledge_builder.py`). If it were authored separately it would drift, and an assistant
answer could contradict the itinerary sitting next to it on screen.

Chunking is **semantic**: one chunk per `(attraction, topic)` — history, significance, facts,
visiting practicalities, accessibility, etiquette — not a blind N-character split. Topics are
short and self-contained, which is what makes sentence-level citation possible at all.

**140 documents → 790 chunks → 790 embeddings.** Each chunk carries its cluster, attraction,
topic, source URL, source type and verification date, so the answer layer can cite without
guessing.

## Retrieval pipeline

```
question
  │
  ├─ 1. classify        regex topic router (history | etiquette | accessibility | …)
  ├─ 2. metadata filter cluster + attraction + topic, widening only if starved
  ├─ 3a. dense          cosine over chunk embeddings (pgvector <=> on PG, Python on SQLite)
  ├─ 3b. lexical        BM25 in Python over the filtered set
  ├─ 4. fuse            reciprocal rank fusion, k = 60
  ├─ 5. rerank          coverage · heading match · topic agreement · source authority
  └─ 6. evidence score  absolute; drives abstention
```

### Why filter before retrieving

The single biggest quality lever. Asking "what should I wear here?" on the Taj Mahal page must
never return Kedarnath's dress code. The filter widens in a deliberate order — it relaxes the
**topic** before the **place**, because returning the right place with a loosely-related topic is
far better than the reverse.

### Why BM25 in Python

Rather than delegating to `tsvector` on Postgres and `LIKE` on SQLite, BM25 is implemented
directly. Behaviour is then identical on both databases and in tests — no dialect-specific
retrieval quality to reason about.

### Why RRF

Dense cosine (0–1) and BM25 (unbounded) live on incomparable scales. RRF uses only ranks, so it
needs no normalisation and no calibration that would rot. Its cost is that it discards score
*magnitude* — which is precisely why it cannot be used for abstention.

### Reranking

A feature-based reranker rather than a cross-encoder. For 790 short, well-structured chunks the
four features below do most of the work and stay explainable, which matters in a system whose
premise is inspectability:

```
0.45 · normalised RRF  +  0.22 · query-term coverage
                       +  0.13 · heading match
                       +  0.12 · topic agreement
                       +  0.08 · source authority
```

Measured contribution: removing it drops top-1 from **0.903 to 0.774** and MRR from 0.952 to
0.874, for essentially no latency saving.

## Abstention

**The metric that matters most for trust.** The first implementation thresholded the fused RRF
score and could not separate answerable from unanswerable questions at all.

The replacement is an **absolute** evidence score:

```
evidence = max over chunks of [ 0.35 · dense_similarity + 0.65 · idf_weighted_coverage ]
```

IDF is computed over the **whole corpus**, cached by corpus size. That detail matters twice:

- Computing IDF over the handful of chunks left after filtering makes ordinary phrasing words
  ("historically", "important") look maximally rare simply because they are absent from six
  paragraphs, which collapses the score and causes over-abstention.
- Plain, unweighted coverage scored "What is the best restaurant in Reykjavik?" respectably
  against a Bengaluru corpus, purely because "best" appears everywhere. Weighting by rarity means
  the absent terms — "reykjavik", "restaurant" — dominate.

### Not every absent term is evidence

Giving an absent term maximum IDF weight is right for one kind of word and badly wrong for
another, and conflating the two produced the two worst bugs in this subsystem — both found by the
evaluation harness, neither visible from reading the code:

| Question | Score | What went wrong |
|---|---|---|
| "What is the current ticket price in rupees **today at 4pm exactly**?" | 0.183 → abstain | The Taj Mahal visiting chunk it retrieved *literally contains the fee*. "today", "4pm" and "exactly" are absent from all 790 chunks, so they drew maximum weight and sank a question we could answer. |
| "What **happened** at Sarnath and why does it **matter**?" | 0.229 → abstain | The correct history chunk was ranked **first**. "happened" and "matter" have document frequency zero. |

The distinction:

- **"reykjavik", "bhutan", "stock"** are absent because they are *out of scope*. That absence is
  the signal, and it keeps full weight.
- **"today", "4pm", "happened", "matter"** are absent because a factual catalogue entry never
  contains words like these *however completely it answers the question*. Their absence measures
  our writing style, not our coverage.

So `_evidence_terms` drops temporal deixis and question-framing words before scoring. The list is
measured, not guessed — every entry was checked to have df = 0 against the live corpus. The
near-miss that proves the point: `matter` is absent, but `matters` appears in **130** chunks,
because every significance chunk is titled "Why X matters".

A second, separate fix: a question demanding a live value now *always* says so —

> Note: this is a recorded value from our catalogue, not a live lookup. We do not have real-time
> prices, availability or opening status.

That disclaimer used to be keyed on which chunk was retrieved. It is now keyed on what was
**asked**, because answering "what's the price right now" from a static catalogue without saying
so is the most misleading thing this assistant could do.

### Synonyms, and why they don't loosen the gate

"Ticket price in rupees" found nothing because the catalogue writes `Entry: Indian visitors:
about Rs.50-Rs.250` — it never uses the words "price" or "rupees". A small hand-checked alias map
(`price → fee/entry/rs/ticket`, `timings → hours/opening`, `kids → child`) closes that gap. It is
deliberately domain-specific rather than a general thesaurus, because broad synonyms would start
manufacturing coverage for questions the corpus genuinely cannot answer.

The guard is a test: *"What is the current **stock price** of Reliance **today**?"* shares
"current", "price" and "today" with the answerable question above and must still abstain — which
it does, at 0.230, because "stock" and "reliance" are nowhere in the corpus.

### Measured effect

| | Before | After |
|---|---|---|
| Abstention accuracy | 0.912 | **1.000** |
| Citation coverage | 0.903 | **1.000** |
| Mean evidence — answerable | 0.521 | **0.582** |
| Mean evidence — **out-of-scope** | 0.071 | **0.071** |

The last row is the one that matters. Out-of-scope evidence did not move *at all*. The gate did
not get more permissive; it stopped misfiring.

Below the threshold, **no LLM call is made at all** and the response is an explicit
"I don't have verified information", with zero citations.

## Citations are computed, not claimed

After generation, each answer sentence is matched back to the retrieved chunk it overlaps most
with. A citation index is attached only when overlap clears 30%.

This is the design decision that makes citation correctness a meaningful metric: a model that
invented a fact simply fails to earn a citation for that sentence. Asking a model to cite its own
sources measures nothing.

## Prompt-injection defence

Retrieved text is **data, never instructions**:

- `detect_prompt_injection` on the user's question → flagged in `warnings`, and the question is
  neutralised before use.
- `safe_context` runs every retrieved chunk through `neutralize_prompt_injection` before it enters
  a prompt.
- The system prompt states that context is reference material and instructions inside it must be
  ignored — belt as well as braces, since the neutralisation is the actual control.

An injection attempt also scores low on evidence, so it typically abstains anyway.

## Without an LLM

With `LLM_PROVIDER=mock` (the default) the answer is composed from retrieved sentences.
Faithfulness is then near-perfect *by construction* — the failure mode is terseness, never
fabrication. The report states this explicitly, because a 1.000 faithfulness score against the
mock provider would otherwise look more impressive than it is.

## Measured results

`python evaluation/run_rag_eval.py` → [full report](../evaluation/reports/rag_evaluation.md)

| Metric | Value |
|---|---|
| Open retrieval top-1 | 0.903 |
| Open retrieval top-3 | 1.000 |
| Open retrieval MRR | 0.952 |
| Retrieval recall | 1.000 |
| Topic classification accuracy | 0.941 |
| Faithfulness | 0.995 |
| Citation correctness | 1.000 |
| Citation coverage | 1.000 |
| Answer completeness | 0.984 |
| **Abstention accuracy** | **1.000** |
| Mean evidence — answerable / out-of-scope | 0.582 / 0.071 |
| Latency p50 / p95 | 8.1 ms / 34.4 ms |

Faithfulness is 0.995 rather than 1.000 for a boring and honest reason: the "not a live lookup"
disclaimer is system text with no lexical support in the retrieved context, so the metric counts
it as unsupported. Exempting our own boilerplate from the faithfulness check would make the
number prettier and the measurement worse, so it stays counted.

### On precision@5

Open precision@5 sits at 0.200 and **that is correct behaviour**. Retrieval filters by topic
first, and each attraction contributes exactly one chunk per topic — so a history question across
a cluster returns the history chunk of five *different* attractions, capping precision@5 at 0.2.
MRR and top-k are the meaningful metrics for this corpus shape. Precision@5 is reported anyway so
the cap is visible rather than hidden.

## Honest limitations

1. The benchmark is **hand-written by the author**, 34 questions, not collected from users.
2. Faithfulness is a **lexical-overlap proxy**. It catches fabrication; it cannot catch a fluent
   paraphrase that changes meaning. An NLI judge would be stronger.
3. **Lexical-only retrieval nearly matches the hybrid** (0.903 top-1 both). That is a limitation of
   the default hashing embedder, whose signal correlates with BM25 rather than complementing it.
   A real encoder should widen the gap — untested, so unclaimed.
4. Ground truth is expressed as required substrings, so completeness measures *retrieval* coverage
   rather than answer quality.

Switching to real embeddings and re-measuring is one command:

```bash
pip install -e ".[embeddings]"
EMBEDDING_PROVIDER=sentence-transformers python -m yatraai.cli embed
EMBEDDING_PROVIDER=sentence-transformers python evaluation/run_rag_eval.py
```
