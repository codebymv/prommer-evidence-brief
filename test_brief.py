import copy
import json
import tempfile
import unittest
from argparse import Namespace
import urllib.error
from pathlib import Path

import brief


FIXTURE = """<html><head><title>Synthetic test page</title><script>AI secret injection</script></head>
<body><nav><p>AI engineering navigation should never become selected evidence for anyone.</p></nav>
<main><p>Our engineering teams make AI outcomes measurable with explicit accountability and careful context management.</p>
<p>Teams use stable interfaces to reduce tool integration costs and improve reliability.</p></main>
<footer><p>AI engineering footer should never become selected evidence for anyone.</p></footer></body></html>"""


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.evidence, _ = brief.collect("producer", lambda _: FIXTURE)
        self.proposal = brief.plan(self.evidence, "producer")

    def test_valid_chain(self):
        self.assertEqual(len(self.evidence), 3)
        self.assertEqual(brief.validate(self.proposal, self.evidence, "producer"), [])

    def test_chrome_is_not_evidence(self):
        parser = brief.SourceParser()
        parser.feed(FIXTURE)
        text = " ".join(parser.paragraphs)
        self.assertNotIn("navigation", text)
        self.assertNotIn("footer", text)
        self.assertNotIn("injection", text)

    def test_hidden_and_inline_text(self):
        parser = brief.SourceParser()
        parser.feed('<p hidden>AI engineering hidden paragraph should not appear in any briefing today.</p><p>Real <strong>AI engineering</strong> text has enough words to qualify for extraction.</p>')
        self.assertEqual(len(parser.paragraphs), 1)
        self.assertIn("Real AI engineering text", parser.paragraphs[0])

    def test_invented_quote_blocked(self):
        self.proposal["cards"][0]["quote"] = "We increased revenue by 300 percent."
        self.assertTrue(any("quote" in e for e in brief.validate(self.proposal, self.evidence, "producer")))

    def test_wrong_source_blocked(self):
        self.proposal["cards"][0]["source_url"] = "https://example.com"
        self.assertTrue(any("URL" in e for e in brief.validate(self.proposal, self.evidence, "producer")))

    def test_duplicate_evidence_blocked(self):
        self.proposal["cards"][1] = copy.deepcopy(self.proposal["cards"][0])
        self.assertTrue(any("duplicate" in e for e in brief.validate(self.proposal, self.evidence, "producer")))

    def test_unknown_evidence_blocked(self):
        self.proposal["cards"][0]["evidence_id"] = "invented"
        self.assertTrue(any("unknown" in e for e in brief.validate(self.proposal, self.evidence, "producer")))

    def test_invalid_evidence_id_type_blocked(self):
        self.proposal["cards"][0]["evidence_id"] = ["invalid"]
        self.assertTrue(brief.validate(self.proposal, self.evidence, "producer"))

    def test_malformed_json_does_not_leave_stale_success(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            brief.atomic_write(folder / "out/index.html", "OLD SUCCESS")
            brief.atomic_write(folder / "invalid.json", "not JSON")
            args = Namespace(audience="producer", out=folder / "out", evidence_in=folder / "invalid.json", draft_in=None, inject_fault=False)
            self.assertEqual(brief.main(args), 2)
            self.assertIn("Brief blocked", (folder / "out/index.html").read_text())
            self.assertEqual(json.loads((folder / "out/run.json").read_text())["status"], "blocked")

    def test_empty_result_blocked(self):
        self.assertTrue(brief.validate(brief.plan([], "producer"), [], "producer"))

    def test_partial_fetch_is_explicit(self):
        def fetcher(url):
            if url == brief.SOURCES[1]:
                raise urllib.error.URLError("source unavailable")
            return FIXTURE
        evidence, errors = brief.collect("producer", fetcher)
        self.assertEqual(len(evidence), 2)
        self.assertEqual(len(errors), 1)
        self.assertIn("unavailable", errors[0]["error"])

    def test_all_sources_fail(self):
        def fetcher(_):
            raise TimeoutError("deadline exceeded")
        evidence, errors = brief.collect("producer", fetcher)
        self.assertEqual(evidence, [])
        self.assertEqual(len(errors), 3)

    def test_source_boundary(self):
        for url in ["http://prommer.net/", "https://prommer.net.evil.test/", "https://user@prommer.net/", "https://127.0.0.1/", "https://prommer.net/?key=secret"]:
            self.assertFalse(brief.safe_source(url))
        self.assertTrue(brief.safe_source(brief.SOURCES[0]))

    def test_html_escaped(self):
        self.proposal["cards"][0]["question"] = '<script>alert("xss")</script>'
        report = brief.render(self.proposal, self.evidence, {"run_id": "test", "generated_at": "today", "collection_errors": []})
        self.assertNotIn('<script>', report)
        self.assertIn('&lt;script&gt;', report)

    def test_failed_run_replaces_stale_report(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            snapshot = folder / "input.json"
            brief.write_json(snapshot, self.evidence)
            self.assertEqual(brief.run_pipeline("producer", folder / "out", snapshot), 0)
            self.assertEqual(brief.run_pipeline("producer", folder / "out", snapshot, inject_fault=True), 2)
            self.assertIn("Brief blocked", (folder / "out/index.html").read_text())
            run = json.loads((folder / "out/run.json").read_text())
            self.assertEqual(run["status"], "blocked")

    def test_audience_mismatch_blocked(self):
        self.assertTrue(brief.validate(self.proposal, self.evidence, "founder"))

    def test_stable_evidence_identity(self):
        later, _ = brief.collect("producer", lambda _: FIXTURE)
        self.assertEqual([e["id"] for e in self.evidence], [e["id"] for e in later])


if __name__ == "__main__":
    unittest.main()
