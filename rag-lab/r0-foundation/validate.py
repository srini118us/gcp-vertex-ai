"""Sanity check R0: questions parse, sources exist, print the distribution."""
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "corpus")


def main():
    corpus_files = set(os.listdir(CORPUS))
    rows = []
    with open(os.path.join(HERE, "questions.jsonl"), encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            rows.append(row)
            for src in row.get("gold_sources", []):
                assert src in corpus_files, f"q{i}: missing source {src}"
            if row["answerable"]:
                assert row["gold_sources"], f"{row['id']}: answerable but no sources"
            else:
                assert not row["gold_sources"], f"{row['id']}: unanswerable but has sources"

    by_pattern = Counter(r["pattern"] for r in rows)
    by_diff = Counter(r["difficulty"] for r in rows)
    unanswerable = sum(1 for r in rows if not r["answerable"])
    print(f"questions: {len(rows)}")
    print(f"corpus docs: {len(corpus_files)}")
    print(f"by pattern: {dict(by_pattern)}")
    print(f"by difficulty: {dict(by_diff)}")
    print(f"unanswerable (refusal) rows: {unanswerable}")
    print("OK: every answerable question has an existing gold source")


if __name__ == "__main__":
    main()
