"""
Clinical RAG Prototype -- End-to-End Demo
==========================================
Run this script to see the full pipeline in action:
  1. Load synthetic clinical records
  2. Chunk + index into hybrid retriever
  3. Build pseudonymised prompt with minimum context
  4. Show retrieval results and constructed prompt
  5. Print eval summary from results.json

Usage:
    python demo.py [--patient patient_A|patient_B] [--verbose]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.chunking import chunk_document
from src.retrieval import EmbeddingEngine, BM25Index, HybridRetriever
from src.prompt import Pseudonymiser, PromptBuilder

DEMO_QUERIES = {
    "patient_A": [
        "What medications was the patient discharged with?",
        "What was the troponin trend during admission?",
        "What are the follow-up instructions after discharge?",
    ],
    "patient_B": [
        "What was the patient's ejection fraction?",
        "What caused the patient's hospital admission?",
        "What was the BNP trend during the stay?",
    ],
}


def load_records(patient_id: str) -> dict[str, str]:
    records = {}
    for path in (ROOT / "data" / "records").glob("*.txt"):
        if patient_id in path.stem or patient_id.replace("_", "") in path.stem:
            records[path.stem] = path.read_text(encoding="utf-8")
    return records


def build_index(records: dict[str, str]) -> HybridRetriever:
    emb = EmbeddingEngine()
    bm25 = BM25Index()
    retriever = HybridRetriever(emb, bm25)
    all_chunks = []
    for doc_id, text in records.items():
        patient_id = "patient_A" if "patient_A" in doc_id else "patient_B"
        doc_type = (
            "discharge_summary" if "discharge" in doc_id
            else "lab_report" if "lab" in doc_id
            else "radiology_report" if "radiology" in doc_id
            else "progress_note"
        )
        chunks = chunk_document(doc_id=doc_id, text=text,
                                patient_id=patient_id, doc_type=doc_type)
        all_chunks.extend(chunks)
    retriever.index(all_chunks)
    return retriever, all_chunks


def run_demo(patient_id: str = "patient_A", verbose: bool = False) -> None:
    print("=" * 65)
    print("  Clinical RAG Prototype -- Demo")
    print("=" * 65)

    # ── Load & index ──────────────────────────────────────────────
    print(f"\n[1] Loading records for {patient_id}...")
    records = load_records(patient_id)
    if not records:
        print(f"  ERROR: No records found for {patient_id}")
        sys.exit(1)
    for doc_id in records:
        print(f"  Loaded: {doc_id}.txt")

    print("\n[2] Chunking and indexing...")
    retriever, all_chunks = build_index(records)
    print(f"  Total chunks indexed: {len(all_chunks)}")
    if verbose:
        for c in all_chunks[:3]:
            print(f"    chunk_id={c.chunk_id}  section={c.section}  tokens={c.token_count}")

    # ── Pseudonymiser + prompt builder ────────────────────────────
    ps = Pseudonymiser()
    builder = PromptBuilder(pseudonymiser=ps)

    # ── Demo queries ──────────────────────────────────────────────
    queries = DEMO_QUERIES.get(patient_id, DEMO_QUERIES["patient_A"])
    print(f"\n[3] Running {len(queries)} demo queries (top-k=5)...\n")

    for i, query in enumerate(queries, 1):
        print(f"  Query {i}: {query}")

        results = retriever.retrieve(query=query, top_k=5,
                                     patient_id=patient_id, use_reranker=True)
        built = builder.build(query=query, results=results)

        print(f"  Retrieved: {len(results)} chunks")
        print(f"  Context tokens: {built.context_tokens} / {built.budget_tokens} budget")
        print(f"  PII guard triggered: {built.pii_guard_triggered}"
              + (f" -- types: {built.pii_types_found}" if built.pii_guard_triggered else ""))

        if verbose and results:
            print("  Top chunk:")
            top = results[0]
            print(f"    section={top.chunk.section}  rrf={top.rrf_score:.4f}"
                  + (f"  rerank={top.rerank_score:.3f}" if top.rerank_score else ""))
            print(f"    text: {top.chunk.text[:120].strip()}...")

        print()

    # ── Eval summary ──────────────────────────────────────────────
    results_path = ROOT / "eval" / "results.json"
    if results_path.exists():
        with open(results_path) as f:
            data = json.load(f)
        s = data["summary"]
        print("[4] Latest eval results (eval/results.json):")
        print(f"  Recall@5       : {s['recall_at_k']:.1%}")
        print(f"  Precision@5    : {s['precision_at_k']:.1%}")
        print(f"  Answer Coverage: {s['answer_coverage']:.1%}")
        print(f"  PII Leakage    : {s['pii_leakage_rate']:.2%}  (target = 0%)")
        print(f"  Mean Latency   : {s['mean_latency_ms']:.1f} ms")
        print(f"  Token Util     : {s['token_utilisation']:.1%}")

    print("\n" + "=" * 65)
    print("  Demo complete. See eval/run_eval.py for full evaluation.")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clinical RAG demo")
    parser.add_argument("--patient", choices=["patient_A", "patient_B"],
                        default="patient_A")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    run_demo(patient_id=args.patient, verbose=args.verbose)
