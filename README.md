# Evidence Brief

A small, inspectable workflow for turning prommer.net's public material into sourced conversation briefs for founders, operators, and podcast producers.

**[Open the live brief](https://codebymv.github.io/prommer-evidence-brief/)** · [Source artifact](docs/index.html) · [Editor handoff](prompts/editor.md)

The checked-in brief uses live evidence captured during development and an AI-authored editorial proposal. Its source excerpts are verified mechanically; its interpretations still require human judgment.

## Run it

Python 3.11+, no dependencies, no credentials.

```bash
python brief.py --audience producer --out output
python -m http.server 8765 --directory output
```

Visit `http://localhost:8765`. `--audience founder` and `--audience operator` choose different relevance terms and discussion questions. The default CLI planner is deliberately deterministic. This project does **not** pretend that rules are an LLM or that a successful substring match proves a claim true.

Replay the delivered AI-assisted brief, without a network call:

```bash
python brief.py --audience producer --evidence-in docs/evidence.json --draft-in drafts/producer.json --out replay
```

Exercise the failure path (expected exit code **2**):

```bash
python brief.py --evidence-in docs/evidence.json --draft-in drafts/producer.json --inject-fault --out fault-demo
```

## The handoffs

1. **Collector:** a CLI trigger selects an audience. Three allowlisted HTTPS pages are fetched with 15-second timeouts, a 2 MB limit, two bounded attempts for transient errors, and an identifying User-Agent. The HTML parser removes script/style/navigation/form content. Audience keywords rank paragraphs. A short excerpt, source URL, capture time, stable evidence ID, and document SHA-256 become `evidence.json`. Source failures are explicit, not silently fabricated.
2. **Planner/editor:** the default planner maps the evidence into audience-specific cards. Alternatively, `--draft-in` accepts a separate AI- or human-authored proposal, using the exact same interface. `drafts/producer.json` was authored with Codex against the actual collected evidence. The questions are proposals, not attributed statements by Thomas.
3. **Verifier:** independent code checks audience, cardinality, duplicate/unknown evidence IDs, exact excerpt equality, source URL identity, and field bounds. It cannot approve an invented quote. HTML escaping occurs at rendering, not by trusting the draft.
4. **Renderer:** a successful verification produces a static review page plus the proposal and run trace. A failed verification writes a blocked page so a previous success is not mistaken for the current run. Partial source coverage is visible. There is no email-sending or auto-publishing tool.

The runtime baseline is a bounded scrape → transform → validate → output workflow. AI was used for implementation and the delivered editorial draft, **not** as an unconfigured background dependency. The proposal interface is the seam for a future runtime model: pass only evidence objects, demand the same JSON contract, then use the existing verifier. Replaying the saved AI draft is not a fresh model inference.

## Why this is specific to prommer.net

The site spans many subjects. A producer deciding whether to book an interview needs a concrete angle and a path back to the work, not another generic bio. This run selects the technology services page, press room, and context-engineering guide. It keeps self-published source material distinct from independent corroboration and avoids turning a press-room mention into an invented client result.

## Real development failure

The first fetch used Python's default urllib client and failed with HTTP 403. Retrying the same public URL with an explicit identifying User-Agent returned HTTP 200. The collector now sends that header on every request. Permanent errors such as 403 are surfaced; only transient HTTP errors and connection timeouts are retried. This was a client/request compatibility issue in this environment, not evidence that every 403 can or should be retried.

An early planner reused the same audience question across all three sources. The source checks passed, but the output was editorially poor: an accountability question did not fit a context-engineering excerpt. I inspected `proposal.json`, changed the baseline to source-specific questions, and authored the delivered three-card draft against each individual excerpt. This is why deterministic provenance checks are necessary but insufficient for useful output.

## Validation

```bash
python -m unittest -v
```

Tests use synthetic HTML and do not require the live site. They cover grounded success, invented excerpts, wrong URLs, duplicate and unknown evidence, audience mismatch, missing/partial sources, navigation/hidden-content filtering, HTML escaping, stable evidence IDs, and stale-report replacement after validation failure. A separate live run demonstrates the real collection path.

## Deliberate limits / next iteration

- Source matching is provenance, not truth. The subject's own website is not independent corroboration.
- The extractor uses paragraph text and does not execute JavaScript. It cannot fully infer CSS visibility or semantic context. Changes to page structure may reduce coverage.
- Draft questions can be speculative; they remain labeled editorial inference and require review.
- Saved snapshots are trusted local inputs. The document hash is recorded for change detection; full copyrighted page bodies are not distributed, so a reviewer verifies current content by following the source.
- The tiny keyword ranker is inspectable but coarse. Next: an evaluated runtime planning model, sentence/section anchors, timestamp/freshness checks, source-diff caching, and a human approval record bound to the exact artifact hash.
- Before recurring delivery: durable state, per-subscriber opt-in/preferences, an idempotent outbox, unsubscribe/suppression checks, and a reviewed email adapter. No outbound messages are sent by this prototype.

No assessment questions, personal answers, credentials, or third-party private material are included in this repository. No open-source license is asserted over the assessment work.
