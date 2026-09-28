"""Evidence Brief: bounded collect -> plan -> verify -> render workflow.

Python 3.11+, standard library only. No model credentials or external writes.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

SOURCES = [
    "https://prommer.net/en/tech/",
    "https://prommer.net/en/tech/press/",
    "https://prommer.net/en/tech/guides/context-engineering/",
]
AUDIENCES = {
    "founder": {
        "label": "Founder evaluating an AI engagement",
        "terms": ["strategy", "implementation", "capabilities", "value", "leadership", "scale"],
        "question": "Which business outcome would you fund first, and what evidence would stop the investment?",
        "action": "Bring one workflow, its current cost, and a measurable success threshold to a scoping conversation.",
    },
    "operator": {
        "label": "Operator building reliable agents",
        "terms": ["context", "quality", "engineering", "production", "workflow", "systems"],
        "question": "Where should the workflow refuse to proceed, and who owns the recovery when it does?",
        "action": "Map one workflow's inputs, tool permissions, acceptance checks, and rollback path before automating it.",
    },
    "producer": {
        "label": "Podcast or press producer",
        "terms": ["accountability", "outcomes", "engineering", "credit", "enterprise", "ai"],
        "question": "When AI gets the credit, what happens to the people accountable for the result?",
        "action": "Use the linked source to check the premise, then ask for one concrete example and one counterexample.",
    },
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def normalize(value):
    return " ".join(value.split())


def safe_source(url):
    p = urllib.parse.urlsplit(url)
    return p.scheme == "https" and p.netloc == "prommer.net" and not p.query and not p.fragment


class SourceParser(HTMLParser):
    """Retain paragraph boundaries; remove executable and repeated chrome text."""
    EXCLUDED = {"script", "style", "noscript", "nav", "footer", "header", "form", "svg"}
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.capture = None
        self.parts = []
        self.paragraphs = []
        self.title_parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        attrs = dict(attrs)
        excluded = tag in self.EXCLUDED or "hidden" in attrs or attrs.get("aria-hidden") == "true"
        self.stack.append((tag, excluded))
        if tag == "p" and not any(x[1] for x in self.stack):
            self.capture = len(self.stack)
            self.parts = []

    def handle_data(self, data):
        if any(x[1] for x in self.stack):
            return
        if self.stack and self.stack[-1][0] == "title":
            self.title_parts.append(data)
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag):
        indexes = [i for i, item in enumerate(self.stack) if item[0] == tag]
        if not indexes:
            return
        i = indexes[-1]
        if self.capture and i < self.capture:
            text = normalize(" ".join(self.parts))
            if len(text.split()) >= 8:
                self.paragraphs.append(text)
            self.capture = None
            self.parts = []
        self.stack = self.stack[:i]


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_source(newurl):
            raise ValueError("Redirect outside approved source boundary")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, attempts=2):
    if not safe_source(url):
        raise ValueError("Only HTTPS prommer.net sources are allowed")
    opener = urllib.request.build_opener(SafeRedirect())
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; EvidenceBrief/1.0)", "Accept": "text/html"})
            with opener.open(req, timeout=15) as response:
                if response.headers.get_content_type() != "text/html":
                    raise ValueError("Source is not HTML")
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError("Source exceeds 2 MB budget")
                return raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == attempts - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts - 1:
                raise
        time.sleep(0.5 * (attempt + 1))
    raise RuntimeError("Fetch exhausted")


def score(text, audience):
    words = set(re.findall(r"[a-z]+", text.lower()))
    return sum(term in words for term in AUDIENCES[audience]["terms"])


def collect(audience, fetcher=fetch):
    evidence, errors = [], []
    for url in SOURCES:
        started = time.monotonic()
        try:
            raw = fetcher(url)
            parser = SourceParser()
            parser.feed(raw)
            candidates = [p for p in parser.paragraphs if score(p, audience) > 0]
            if not candidates:
                raise ValueError("No relevant paragraph found; extraction needs review")
            paragraph = max(candidates, key=lambda p: (score(p, audience), -len(p)))
            # Excerpts stay short; do not republish entire articles.
            quote = " ".join(paragraph.split()[:18])
            item = {"id": digest(url + "\n" + quote)[:12], "url": url,
                    "quote": quote, "retrieved_at": now(), "source_sha256": digest(raw),
                    "score": score(paragraph, audience), "elapsed_ms": round((time.monotonic() - started) * 1000)}
            evidence.append(item)
        except (ValueError, urllib.error.URLError, TimeoutError) as exc:
            errors.append({"url": url, "error": str(exc), "stage": "collect"})
    return evidence, errors


def plan(evidence, audience):
    """Transparent rule-based planner. Optional AI drafts use the same contract."""
    profile = AUDIENCES[audience]
    questions = {
        "founder": ["Which engagement could prove business value before committing to a larger transformation?", "What would make the claimed AI outcomes credible enough to fund?", "Which missing context causes the most expensive mistakes in your current workflow?"],
        "operator": ["How would tool interoperability change the workflow you build first?", "Who owns an AI workflow's outcome when several teams and tools contribute?", "What belongs in durable context, and what should be retrieved only when needed?"],
        "producer": ["When selecting engineering tools, what does interoperability buy that a longer feature list cannot?", "What does closing the AI accountability gap look like in an actual engineering team?", "What changes when context becomes an engineering responsibility rather than a longer prompt?"],
    }
    return {"audience": audience, "mode": "deterministic", "cards": [
        {"evidence_id": item["id"], "source_url": item["url"], "quote": item["quote"],
         "question": questions[audience][SOURCES.index(item["url"])], "next_step": profile["action"]}
        for item in sorted(evidence, key=lambda e: (-e["score"], e["url"]))
    ]}


def validate(proposal, evidence, audience):
    """Structural grounding, not a claim of semantic truth or independent verification."""
    errors = []
    if not isinstance(proposal, dict):
        return ["Proposal must be an object"]
    if proposal.get("audience") != audience:
        errors.append("Audience mismatch")
    cards = proposal.get("cards")
    if not isinstance(cards, list) or not 1 <= len(cards) <= 3:
        return errors + ["Expected 1-3 cards"]
    allowed = {item["id"]: item for item in evidence}
    seen = set()
    for i, card in enumerate(cards):
        if not isinstance(card, dict):
            errors.append(f"card {i}: expected object")
            continue
        evidence_id = card.get("evidence_id")
        item = allowed.get(evidence_id) if isinstance(evidence_id, str) else None
        if not item:
            errors.append(f"card {i}: unknown evidence ID")
            continue
        if item["id"] in seen:
            errors.append(f"card {i}: duplicate evidence")
        seen.add(item["id"])
        if card.get("quote") != item["quote"]:
            errors.append(f"card {i}: quote does not match captured evidence")
        if card.get("source_url") != item["url"] or not safe_source(card.get("source_url", "")):
            errors.append(f"card {i}: source URL mismatch")
        for field in ["question", "next_step"]:
            value = card.get(field)
            if not isinstance(value, str) or not 10 <= len(value) <= 500:
                errors.append(f"card {i}: invalid {field}")
    return errors


def write_json(path, value):
    atomic_write(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(value, encoding="utf-8")
    temp.replace(path)


def render(proposal, evidence, run):
    e = html.escape
    lookup = {item["id"]: item for item in evidence}
    cards = []
    for n, card in enumerate(proposal["cards"], 1):
        item = lookup[card["evidence_id"]]
        cards.append(f'''<article><div class="eyebrow">BRIEF {n:02} / SOURCE-BACKED EXCERPT</div>
        <blockquote>“{e(card['quote'])}…”</blockquote>
        <a class="source" href="{e(card['source_url'], quote=True)}" target="_blank" rel="noopener noreferrer">Read source ↗</a>
        <div class="idea"><span>PROPOSED DISCUSSION QUESTION · EDITORIAL INFERENCE</span><h2>{e(card['question'])}</h2><p>{e(card['next_step'])}</p></div>
        <details><summary>Inspect evidence</summary><p>Captured {e(item['retrieved_at'])}</p><code>ID {e(item['id'])}<br>SHA-256 {e(item['source_sha256'])}</code><p>Hash identifies the fetched document. Grounding confirms the excerpt matches it; this is not independent fact-checking.</p></details></article>''')
    template = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    return (template.replace("{{audience}}", e(AUDIENCES[proposal['audience']]['label']))
            .replace("{{cards}}", "".join(cards)).replace("{{run_id}}", e(run['run_id']))
            .replace("{{generated_at}}", e(run['generated_at'])).replace("{{count}}", str(len(cards)))
            .replace("{{mode}}", e(str(proposal.get('mode', 'external draft'))))
            .replace("{{degraded}}", "Partial source coverage — review collection errors." if run['collection_errors'] else "All three sources collected."))


def run_pipeline(audience, out, evidence_in=None, draft_in=None, inject_fault=False):
    started = time.monotonic()
    out = Path(out)
    # Invalidate stale success before parsing any external draft or doing network I/O.
    atomic_write(out / "index.html", "<!doctype html><html lang='en'><meta charset='utf-8'><title>Brief pending</title><h1>Brief pending</h1><p>This run has not completed validation.</p></html>")
    write_json(out / "run.json", {"status": "running", "generated_at": now()})
    if evidence_in:
        evidence = json.loads(Path(evidence_in).read_text(encoding="utf-8"))
        collection_errors = []
    else:
        evidence, collection_errors = collect(audience)
    proposal = json.loads(Path(draft_in).read_text(encoding="utf-8")) if draft_in else plan(evidence, audience)
    if inject_fault and proposal.get("cards"):
        proposal["cards"][0]["quote"] = "Invented claim: revenue increased 300 percent."
    errors = validate(proposal, evidence, audience)
    run = {"run_id": digest(json.dumps([audience, evidence, proposal], sort_keys=True))[:16],
           "generated_at": now(), "audience": audience, "source_mode": "snapshot" if evidence_in else "live",
           "stages": ["collect", "plan", "verify", "render" if not errors else "blocked"],
           "collection_errors": collection_errors, "validation_errors": errors,
           "status": "blocked" if errors else "needs_human_review",
           "elapsed_ms": round((time.monotonic() - started) * 1000)}
    write_json(out / "evidence.json", evidence)
    write_json(out / "proposal.json", proposal)
    write_json(out / "run.json", run)
    # Always overwrite the landing page: a failed run must not expose a stale success.
    if errors:
        atomic_write(out / "index.html", "<!doctype html><html lang='en'><meta charset='utf-8'><title>Blocked brief</title><h1>Brief blocked</h1><p>No current report is approved for review.</p><pre>" + html.escape("\n".join(errors)) + "</pre></html>")
    else:
        atomic_write(out / "index.html", render(proposal, evidence, run))
    print(json.dumps(run, indent=2))
    return 2 if errors else 0


def main(args):
    try:
        return run_pipeline(args.audience, args.out, args.evidence_in, args.draft_in, args.inject_fault)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        out = Path(args.out)
        write_json(out / "run.json", {"status": "blocked", "generated_at": now(), "input_error": str(exc)})
        atomic_write(out / "index.html", "<!doctype html><html lang='en'><meta charset='utf-8'><title>Blocked brief</title><h1>Brief blocked</h1><p>Input or output could not be processed. Inspect run.json.</p></html>")
        print(f"Blocked: {exc}")
        return 2


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--audience", choices=AUDIENCES, default="producer")
    cli.add_argument("--out", default="docs")
    cli.add_argument("--evidence-in", help="Replay a saved evidence snapshot without network")
    cli.add_argument("--draft-in", help="Validate an externally authored JSON proposal")
    cli.add_argument("--inject-fault", action="store_true", help="Deliberately mutate a quote to exercise the gate")
    args = cli.parse_args()
    raise SystemExit(main(args))
