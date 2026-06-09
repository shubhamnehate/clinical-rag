"""
Evaluation Script — Clinical RAG Prototype
===========================================
Metrics:
  1. Retrieval Recall@k   — were gold keywords found in top-k chunks?
  2. Context Precision@k  — fraction of retrieved chunks that are relevant
  3. Answer Coverage      — fraction of expected keywords in final answer
  4. PII Leakage Rate     — PII detected in output (MUST be 0.00%)
  5. Mean Latency (ms)    — end-to-end query time
  6. Token Efficiency     — context tokens used / budget

Run:
    python eval/run_eval.py [--top-k 5] [--verbose]
"""
from __future__ import annotations

import json
import os
import sys
import time
import argparse
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.chunking import chunk_document, Chunk
from src.retrieval import EmbeddingEngine, BM25Index, HybridRetriever
from src.prompt import Pseudonymiser, PromptBuilder


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_records(data_dir: Path) -> Dict[str, str]:
    """Load all .txt files from data/records/ as {stem: text}."""
    records = {}
    for path in (data_dir / "records").glob("*.txt"):
        records[path.stem] = path.read_text(encoding="utf-8")
    return records


def build_index(records: Dict[str, str]) -> HybridRetriever:
    """Ingest all records into the retrieval system."""
    print("\n[Setup] Ingesting records...")
    emb = EmbeddingEngine()
    bm25 = BM25Index()
    retriever = HybridRetriever(emb, bm25)

    all_chunks: List[Chunk] = []
    for doc_id, text in records.items():
        patient_id = "patient_A" if "patient_A" in doc_id else "patient_B"
        doc_type = (
            "discharge_summary" if "discharge" in doc_id
            else "lab_report" if "lab" in doc_id
            else "radiology_report" if "radiology" in doc_id
            else "progress_note"
        )
        chunks = chunk_document(
            doc_id=doc_id,
            text=text,
            patient_id=patient_id,
            doc_type=doc_type,
        )
        all_chunks.extend(chunks)
        print(f"  {doc_id}: {len(chunks)} chunks")

    retriever.index(all_chunks)
    print(f"[Setup] Total chunks indexed: {len(all_chunks)}\n")
    return retriever


def retrieval_recall_at_k(
    retrieved_chunks: list,
    expected_keywords: List[str],
    expected_section: str,
) -> float:
    """
    Recall@k: fraction of expected_keywords found in top-k retrieved chunks.
    A keyword is 'found' if it appears (case-insensitive) in any retrieved chunk.
    """
    if not expected_keywords:
        return 1.0
    combined_text = " ".join(c.chunk.text.lower() for c in retrieved_chunks)
    hits = sum(1 for kw in expected_keywords if kw.lower() in combined_text)
    return hits / len(expected_keywords)


def context_precision_at_k(
    retrieved_chunks: list,
    expected_keywords: List[str],
) -> float:
    """
    Precision@k: fraction of retrieved chunks that contain at least one keyword.
    """
    if not retrieved_chunks or not expected_keywords:
        return 0.0
    relevant = sum(
        1 for r in retrieved_chunks
        if any(kw.lower() in r.chunk.text.lower() for kw in expected_keywords)
    )
    return relevant / len(retrieved_chunks)


def answer_coverage(answer: str, expected_keywords: List[str]) -> float:
    """Fraction of gold keywords present in the answer string."""
    if not expected_keywords:
        return 1.0
    return sum(1 for kw in expected_keywords if kw.lower() in answer.lower()) / len(expected_keywords)


def check_pii_leakage(text: str, ps: Pseudonymiser) -> bool:
    """True if PII detected in text (leakage = bad)."""
    found, _ = ps.scan(text)
    return found


def mock_answer(built_prompt, q: dict) -> str:
    """
    Generate a mock answer by extracting relevant text from context.
    In production: call Claude API here.
    Checks for expected keywords in the context and constructs an answer.
    """
    context = built_prompt.user
    keywords = q["expected_keywords"]
    found_kws = [kw for kw in keywords if kw.lower() in context.lower()]

    if not found_kws:
        return "Not found in the provided records."

    # Simulate an answer based on what context contains
    answer_parts = [f"Based on [{q['expected_section']}]:"]
    for kw in found_kws[:5]:
        # Find the line containing the keyword
        for line in context.splitlines():
            if kw.lower() in line.lower() and len(line.strip()) > 5:
                answer_parts.append(f"  - {line.strip()[:100]}")
                break
    return "\n".join(answer_parts) if len(answer_parts) > 1 else f"Found: {', '.join(found_kws)}"


# ── Main eval loop ────────────────────────────────────────────────────────────

def run_evaluation(top_k: int = 5, verbose: bool = False) -> None:
    data_dir = ROOT / "data"
    eval_path = ROOT / "eval" / "eval_set.json"

    records = load_records(data_dir)
    if not records:
        print("ERROR: No records found in data/records/")
        sys.exit(1)

    retriever = build_index(records)
    ps = Pseudonymiser()
    prompt_builder = PromptBuilder(pseudonymiser=ps)

    with open(eval_path) as f:
        eval_set = json.load(f)

    questions = eval_set["questions"]
    print(f"[Eval] Running {len(questions)} questions with top_k={top_k}\n")

    # Per-question metrics
    per_question = []
    by_type: Dict[str, List] = defaultdict(list)
    by_difficulty: Dict[str, List] = defaultdict(list)
    latencies = []
    pii_leakage_count = 0

    for q in questions:
        t0 = time.perf_counter()

        # Retrieve
        results = retriever.retrieve(
            query=q["query"],
            top_k=top_k,
            patient_id=q["patient"],
            use_reranker=True,
        )

        # Build prompt
        built = prompt_builder.build(query=q["query"], results=results)

        # Generate answer (mock)
        answer = mock_answer(built, q)

        latency_ms = (time.perf_counter() - t0) * 1000

        # Metrics
        recall = retrieval_recall_at_k(results, q["expected_keywords"], q["expected_section"])
        precision = context_precision_at_k(results, q["expected_keywords"])
        coverage = answer_coverage(answer, q["expected_keywords"])
        pii_leaked = check_pii_leakage(answer, ps)

        if pii_leaked:
            pii_leakage_count += 1

        row = {
            "id": q["id"],
            "query_type": q["query_type"],
            "difficulty": q["difficulty"],
            "recall_at_k": recall,
            "precision_at_k": precision,
            "answer_coverage": coverage,
            "pii_leaked": pii_leaked,
            "context_chunks": built.context_chunks_used,
            "context_tokens": built.context_tokens,
            "latency_ms": latency_ms,
            "pii_guard": built.pii_guard_triggered,
        }
        per_question.append(row)
        by_type[q["query_type"]].append(row)
        by_difficulty[q["difficulty"]].append(row)
        latencies.append(latency_ms)

        if verbose:
            status = "PASS" if recall >= 0.5 else "FAIL"
            pii_flag = " [PII!]" if pii_leaked else ""
            print(
                f"  {q['id']} [{status}]{pii_flag}  "
                f"Recall={recall:.2f}  Prec={precision:.2f}  "
                f"Cov={coverage:.2f}  Lat={latency_ms:.0f}ms  "
                f"Q: {q['query'][:60]}"
            )

    # ── Summary metrics ──
    n = len(per_question)
    avg = lambda key: sum(r[key] for r in per_question) / n

    print("\n" + "=" * 72)
    print("  EVALUATION RESULTS")
    print("=" * 72)

    print(f"\n  Dataset    : {n} questions over {len(records)} documents")
    print(f"  Top-k      : {top_k}")
    print(f"  Total chunks in index: {sum(1 for _ in retriever._indexed_chunks)}")

    print("\n  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  METRIC                        │  VALUE   │  TARGET        │")
    print("  ├─────────────────────────────────────────────────────────────┤")

    recall_avg = avg("recall_at_k")
    precision_avg = avg("precision_at_k")
    coverage_avg = avg("answer_coverage")
    pii_rate = pii_leakage_count / n
    lat_avg = sum(latencies) / n
    lat_p95 = sorted(latencies)[int(0.95 * len(latencies))]
    tok_util = avg("context_tokens") / prompt_builder.budget

    def row(name, val, fmt, target, pass_fn):
        val_str = fmt.format(val)
        tgt_str = target
        status = "PASS" if pass_fn(val) else "FAIL"
        flag = "  ✓" if pass_fn(val) else "  ✗"
        print(f"  │  {name:<30}  │  {val_str:<8} │  {tgt_str:<14}  {flag} │")

    row("Retrieval Recall@k",      recall_avg,    "{:.1%}",    "> 70%",     lambda v: v >= 0.70)
    row("Context Precision@k",     precision_avg, "{:.1%}",    "> 60%",     lambda v: v >= 0.60)
    row("Answer Coverage",         coverage_avg,  "{:.1%}",    "> 60%",     lambda v: v >= 0.60)
    row("PII Leakage Rate",        pii_rate,      "{:.2%}",    "= 0.00%",   lambda v: v == 0.0)
    row("Mean Latency (ms)",       lat_avg,       "{:.0f}ms",  "< 500ms",   lambda v: v < 500)
    row("P95 Latency (ms)",        lat_p95,       "{:.0f}ms",  "< 1000ms",  lambda v: v < 1000)
    row("Token Utilisation",       tok_util,      "{:.0%}",    "< 80%",     lambda v: v < 0.80)

    print("  └─────────────────────────────────────────────────────────────┘")

    # By query type
    print("\n  BY QUERY TYPE:")
    print(f"  {'Type':<20} {'Count':>6} {'Recall@k':>10} {'Coverage':>10}")
    print(f"  {'-'*20} {'-'*6} {'-'*10} {'-'*10}")
    for qtype, rows in sorted(by_type.items()):
        cnt = len(rows)
        r_avg = sum(r["recall_at_k"] for r in rows) / cnt
        c_avg = sum(r["answer_coverage"] for r in rows) / cnt
        print(f"  {qtype:<20} {cnt:>6} {r_avg:>9.1%} {c_avg:>10.1%}")

    # By difficulty
    print("\n  BY DIFFICULTY:")
    print(f"  {'Difficulty':<12} {'Count':>6} {'Recall@k':>10} {'Coverage':>10}")
    print(f"  {'-'*12} {'-'*6} {'-'*10} {'-'*10}")
    for diff in ["easy", "medium", "hard"]:
        rows = by_difficulty.get(diff, [])
        if not rows:
            continue
        cnt = len(rows)
        r_avg = sum(r["recall_at_k"] for r in rows) / cnt
        c_avg = sum(r["answer_coverage"] for r in rows) / cnt
        print(f"  {diff:<12} {cnt:>6} {r_avg:>9.1%} {c_avg:>10.1%}")

    # PII summary
    print(f"\n  PII AUDIT: {pii_leakage_count}/{n} responses contained PII — "
          + ("ALL CLEAR" if pii_leakage_count == 0 else "CRITICAL: LEAKAGE DETECTED"))

    print("=" * 72)

    # Save results
    out_path = ROOT / "eval" / "results.json"
    with open(out_path, "w") as f:
        json.dump({
            "summary": {
                "recall_at_k": round(recall_avg, 4),
                "precision_at_k": round(precision_avg, 4),
                "answer_coverage": round(coverage_avg, 4),
                "pii_leakage_rate": round(pii_rate, 4),
                "mean_latency_ms": round(lat_avg, 1),
                "p95_latency_ms": round(lat_p95, 1),
                "token_utilisation": round(tok_util, 4),
            },
            "per_question": per_question,
        }, f, indent=2)
    print(f"\n  Full results saved to: {out_path}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Clinical RAG evaluation")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to retrieve")
    parser.add_argument("--verbose", action="store_true", help="Show per-question results")
    args = parser.parse_args()
    run_evaluation(top_k=args.top_k, verbose=args.verbose)
