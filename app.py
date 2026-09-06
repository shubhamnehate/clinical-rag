"""
app.py - Hosted Streamlit demo for the Clinical RAG system.

Runs the real pipeline (src/pipeline.py) end to end, in memory:
  ingestion -> query intelligence -> hybrid retrieval -> generation
  -> confidence scoring -> 3-layer PII protection.

Generation goes through the Yolo-Auto LLM API (OpenAI-compatible) when
YOLO_API_URL + YOLO_API_KEY are configured (env vars or Streamlit
secrets); otherwise the demo runs in mock mode and everything except the
final LLM answer still works.

Run locally:
    streamlit run app.py
"""

import hmac
import json
import logging
import os
import pathlib
import sys
import threading
import time
import urllib.request

import streamlit as st

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT / "clinical-rag"))  # the pipeline package

from src.generation.llm import LLMResponse  # noqa: E402
from src.pipeline import ClinicalRAGPipeline  # noqa: E402

log = logging.getLogger("clinical_rag_demo")

st.set_page_config(page_title="Clinical RAG", page_icon="🏥", layout="wide")

MAX_QUERY_LEN = 400
MIN_QUERY_INTERVAL_S = 4  # per-session throttle; the LLM key is shared with the live site
RL_PER_MIN = 6  # app-wide ceiling on real LLM calls
RL_PER_HOUR = 40

SAMPLE_QUERIES = {
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


def _secret(name: str) -> str:
    val = os.environ.get(name, "")
    if val:
        return val
    try:
        return st.secrets[name]
    except Exception:
        return ""


# Redirects would re-send the Authorization header to the redirect target;
# refuse them (urllib, unlike requests, does not strip auth across hosts).
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


@st.cache_resource
def _rate_state():
    """One shared limiter across all sessions in this process."""
    return {"lock": threading.Lock(), "hits": []}


def _rate_ok() -> bool:
    """App-wide sliding-window limit on real LLM calls (not per session)."""
    state = _rate_state()
    now = time.time()
    with state["lock"]:
        hits = [t for t in state["hits"] if now - t < 3600]
        if len(hits) >= RL_PER_HOUR or sum(now - t < 60 for t in hits) >= RL_PER_MIN:
            state["hits"] = hits
            return False
        hits.append(now)
        state["hits"] = hits
        return True


def _access_granted() -> bool:
    """Optional shared-secret gate; open when DEMO_ACCESS_CODE is unset."""
    code = _secret("DEMO_ACCESS_CODE")
    if not code:
        return True
    if st.session_state.get("access_ok"):
        return True
    with st.form("access_gate"):
        entered = st.text_input("Access code", type="password")
        if st.form_submit_button("Enter") and hmac.compare_digest(entered, code):
            st.session_state["access_ok"] = True
            st.rerun()
    return False


class YoloLLMClient:
    """OpenAI-compatible chat client for the Yolo-Auto API.

    Drop-in for the pipeline's LLMClient: the pipeline only ever calls
    ``generate(system_prompt, user_message)`` on it and expects an
    ``LLMResponse`` back.
    """

    def __init__(self, url: str, key: str, model: str, max_tokens: int = 1000):
        if not url.startswith("https://"):
            raise ValueError("YOLO_API_URL must be an https:// URL")
        self.url = url.rstrip("/")
        self.key = key
        self.model = model
        self.max_tokens = max_tokens

    def generate(self, system_prompt: str, user_message: str) -> LLMResponse:
        start = time.time()
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "max_tokens": self.max_tokens,
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.key}",
            },
        )
        try:
            with _OPENER.open(req, timeout=30) as resp:
                data = json.loads(resp.read())
            answer = (data["choices"][0]["message"]["content"] or "").strip()
            if not answer:
                raise ValueError("empty completion")
            usage = data.get("usage", {})
            return LLMResponse(
                answer=answer,
                model=self.model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception:
            log.exception("Yolo-Auto request failed")
            return LLMResponse(
                answer="_The generation service is unavailable right now. "
                "Retrieval, the PII guard and confidence scoring above still ran._",
                model=self.model,
                input_tokens=0,
                output_tokens=0,
                latency_ms=(time.time() - start) * 1000,
            )


@st.cache_resource(show_spinner="Building index from the sample corpus...")
def build_pipeline(live: bool, model: str):
    pipe = ClinicalRAGPipeline(
        mock_llm=True,  # never touch the built-in Anthropic path
        reranker_enabled=False,  # keep the free-tier image torch-free
        cache_enabled=True,
    )
    if live:
        pipe.llm = YoloLLMClient(
            url=_secret("YOLO_API_URL"),
            key=_secret("YOLO_API_KEY"),
            model=model,
        )
    for path in sorted((ROOT / "demo_data" / "records").glob("*.txt")):
        stem = path.stem
        patient_id = "patient_A" if "patient_A" in stem else "patient_B" if "patient_B" in stem else None
        pipe.ingest_text(stem, path.read_text(encoding="utf-8"), patient_id=patient_id)
    return pipe


live = bool(_secret("YOLO_API_URL") and _secret("YOLO_API_KEY"))
yolo_model = _secret("YOLO_MODEL") or "qwen3.8-27b"
pipe = build_pipeline(live, yolo_model)

st.title("Clinical RAG")
st.caption(
    "Retrieval, re-ranking, pseudonymisation-aware prompting, prompt-injection "
    "guardrails and confidence scoring over synthetic, de-identified clinical records."
)
if not live:
    st.warning(
        "**Mock mode** - no `YOLO_API_URL` / `YOLO_API_KEY` configured, so the final "
        "answer is a stitched-together context stub. Retrieval, the 3-layer PII "
        "guard, confidence scoring and the feedback loop all run for real.",
        icon="⚠️",
    )

if not _access_granted():
    st.stop()

st.session_state.setdefault("query", SAMPLE_QUERIES["patient_A"][0])

with st.sidebar:
    st.header("Query scope")
    scope = st.radio("Patient", ["patient_A", "patient_B", "Both patients"], index=0)
    patient_id = None if scope == "Both patients" else scope
    st.divider()
    st.subheader("Sample questions")
    for pid, qs in SAMPLE_QUERIES.items():
        if patient_id in (None, pid):
            st.markdown(f"*{pid}*")
            for q in qs:
                if st.button(q, key=f"s_{pid}_{q}", use_container_width=True):
                    st.session_state["query"] = q

with st.form("query_form"):
    st.text_input("Clinical question", key="query", max_chars=MAX_QUERY_LEN)
    submitted = st.form_submit_button("Run query", type="primary")

if submitted:
    query = st.session_state["query"].strip()
    now = time.time()
    if not query:
        st.stop()
    if len(query) > MAX_QUERY_LEN:  # server-side check; the widget cap can be bypassed
        st.error(f"Question is too long (max {MAX_QUERY_LEN} characters).")
        st.stop()
    if now - st.session_state.get("last_query_ts", 0.0) < MIN_QUERY_INTERVAL_S:
        st.warning("One moment between queries, please.")
        st.stop()
    if live and not _rate_ok():
        st.warning(
            "The demo has hit its shared usage limit for now. Try again shortly, "
            "or run it locally with your own key."
        )
        st.stop()
    st.session_state["last_query_ts"] = now

    with st.spinner("Running the pipeline..."):
        resp = pipe.query(query, patient_id=patient_id)

    st.markdown("### Answer")
    st.write(resp.answer)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Confidence", f"{resp.confidence:.2f}", resp.confidence_level)
    c2.metric("Route", resp.route)
    c3.metric("Chunks retrieved", resp.retrieval_count)
    c4.metric("Latency", f"{resp.latency_ms:.0f} ms")

    flags = []
    if resp.cache_hit:
        flags.append("semantic cache hit")
    if resp.retry_count:
        flags.append(f"{resp.retry_count} feedback-loop retr{'y' if resp.retry_count == 1 else 'ies'}")
    if resp.pii_guard_triggered:
        flags.append("Layer 2 PII guard triggered")
    if resp.pii_output_detected:
        flags.append("Layer 3 PII detected in output")
    if flags:
        st.info(" · ".join(flags))
    for w in resp.warnings:
        st.caption(f"⚠️ {w}")

    with st.expander("System metrics"):
        st.json(pipe.get_metrics())
