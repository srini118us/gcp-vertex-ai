# RAG R0, Foundation: corpus and tagged question set

The foundation every later RAG pattern plugs into. One corpus, one question set,
built backwards from the differences so that each pattern has a case it should win
and a control case it should not. If a fancy pattern does not beat Naive on its own
hard case, that is a real finding about when not to add the complexity.

## Corpus

A synthetic knowledge base for a fictional appliance maker, Meridian. Eight short
documents under `corpus/`. The company and facts are invented so the exact failure
modes can be planted.

| Document | Role | Planted stress |
|---|---|---|
| product_catalog.md | Product specs in tables | Multimodal, values live in table cells not prose |
| warranty_policy.md | Warranty terms by division | Naive facts, and a distractor against returns |
| returns_refunds.md | Return window and restocking fee | Naive, and the warranty versus returns confusion |
| pricing_promotions.md | Prices and the current promo | Naive, and deal versus promotion wording |
| installation_dishwasher.md | Install and troubleshooting | Vocabulary mismatch, does not power on versus will not start |
| support_faq.md | Generic support answers | Distractor chunks near the real answers |
| company_overview.md | Divisions, leaders, suppliers | Graph, entity relationships for multi hop |
| safety_recall.md | AC300 recall and remedy | Multi hop and agentic reconciliation |

Facts are kept consistent across documents on purpose, so multi hop questions have
a single correct chain. Two gaps are planted deliberately: acoustic noise ratings
and financing are never stated, so questions about them must be refused, not
answered.

## Question set

`questions.jsonl`, one JSON object per line. Schema:

- id, question
- pattern, the pattern the question targets: naive, multimodal, fusion, hyde,
  corrective, graph, agentic
- difficulty, easy, medium, or hard
- answerable, true or false. False means the correct response is a refusal
- gold_answer, the reference answer or the refusal
- gold_sources, the documents that contain the answer, empty when unanswerable
- stress, one line on why the question separates that pattern from Naive

Distribution, 22 questions: naive 5, multimodal 3, fusion 2, hyde 1, corrective 4
(three unanswerable, one distractor), graph 4, agentic 3.

## How the later labs use this

- R1 Naive baseline runs every question through a single retrieve then generate
  pass and records the control numbers.
- R2 Agentic lets an ADK agent plan retrieval, expected to win the agentic rows
  (q18 to q20) and help the graph rows.
- R3 Corrective adds a relevance grader, expected to win the unanswerable rows
  (q11 to q13) by refusing instead of inventing.
- R4 Fusion and HyDE target the vocabulary mismatch rows (q08 to q10).
- R5 Multimodal renders product_catalog.md as an image so the table rows (q05 to
  q07) require true multimodal retrieval.
- R6 Graph builds a small graph over company_overview.md for the multi hop rows
  (q14 to q17).
- R7 scorecard scores every pattern on the same questions.

## Metrics the scorecard will use

- Retrieval recall, did the gold_sources appear in the retrieved set.
- Groundedness, is the answer supported by retrieved text.
- Refusal correctness, did unanswerable questions get refused.
- Citation fidelity, do cited sources match gold_sources.
- Latency and cost per query.

## Honest note

On this small clean corpus, Naive will answer most easy and medium questions well.
The point is not to make Naive look bad. It is to find the specific rows where a
pattern earns its added latency and cost, and to report the rows where it does not.
