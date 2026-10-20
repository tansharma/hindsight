"""Regression tests for the deterministic helper scripts in hindsight/scripts/.

Run from the repo root (stdlib only, no install needed):
    python3 -m unittest discover -s tests -v

Each script is driven as a subprocess through its interpreter, the same way
SKILL.md tells the agent to invoke it.
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "hindsight" / "scripts"


def run(script, *args, stdin=None, env=None, cwd=None, isolated=False):
    interpreter = ["bash"] if script.endswith(".sh") else [sys.executable] + (["-I"] if isolated else [])
    return subprocess.run(
        interpreter + [str(SCRIPTS / script), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        cwd=cwd,
    )


def review(area="Code Quality", issue="x", rationale="y",
           impact="High Impact / Low Effort", prompt="z", done="d", style="**{label}**"):
    rows = [("Area", area), ("Issue", issue), ("Rationale", rationale),
            ("Impact/Effort", impact), ("Suggested LLM Action Prompt", prompt)]
    if done is not None:
        rows.append(("Done When", done))
    return "\n".join(f"{style.format(label=label)} {value}" for label, value in rows) + "\n"


def parse(text):
    """Parse text; returns (result, findings list or None)."""
    result = run("parse_findings.py", stdin=text)
    return result, (json.loads(result.stdout)["findings"] if result.returncode == 0 else None)


def render(findings, *extra_args):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "inHindsight.md"
        result = run("render_output.py", "--root", tmp, "--goal", "g", "--out", str(out),
                     *extra_args, stdin=json.dumps(findings))
        return result, (out.read_text() if out.exists() else "")


def finding(**overrides):
    """A finding in the legacy (pre-JSON-contract) key format."""
    base = {"Area": "Code Quality", "Issue": "x", "Rationale": "y",
            "Impact/Effort": "High Impact / Low Effort", "LLM_Prompt": "z", "Done_When": "d"}
    return {**base, **overrides}


def json_finding(**overrides):
    base = {"area": "Code Quality", "title": "t", "issue": "x", "rationale": "y",
            "impact": "High", "effort": "Low", "prompt": "z", "done_when": "d"}
    return {**base, **overrides}


def matrix(n):
    return [{"solution": f"S{i}", "impact": 3, "effort": 2, "argument": "a"} for i in range(n)]


class ParseFindingsTest(unittest.TestCase):
    def test_mock_review_parses_three_findings(self):
        result = run("parse_findings.py", str(SCRIPTS / "mock_review.txt"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["findings"]), 3)

    def test_colon_inside_bold_labels(self):
        result, findings = parse(review(style="- **{label}:**"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(findings[0]["area"], "Code Quality")
        self.assertEqual(findings[0]["prompt"], "z")

    def test_colon_after_bold_labels(self):
        _, findings = parse(review(style="**{label}**:"))
        self.assertEqual(findings[0]["issue"], "x")

    def test_list_marker_does_not_leak_into_previous_value(self):
        _, findings = parse(review(style="- **{label}:**"))
        self.assertEqual(findings[0]["issue"], "x")
        self.assertEqual(findings[0]["rationale"], "y")

    def test_value_on_next_line(self):
        _, findings = parse(review(style="**{label}**\n"))
        self.assertEqual(findings[0]["rationale"], "y")

    def test_numbered_findings(self):
        text = "1. " + review(issue="first") + "\n2. " + review(issue="second")
        _, findings = parse(text)
        self.assertEqual([f["issue"] for f in findings], ["first", "second"])

    def test_label_mentioned_inside_prompt_is_not_a_new_finding(self):
        prompt = "Update the template so each finding has an **Area** label first."
        result, findings = parse(review(prompt=prompt))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["prompt"], prompt)
        self.assertNotIn("dropped", result.stderr)

    def test_labels_inside_fenced_code_are_ignored(self):
        prompt = "Use this format:\n```markdown\n**Area** Code Quality\n**Issue** demo\n```\nDone."
        _, findings = parse(review(prompt=prompt))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["prompt"], prompt)

    def test_incomplete_findings_are_reported(self):
        text = review() + "\n**Area** Code Quality\n**Issue** orphan\n"
        result, findings = parse(text)
        self.assertEqual(len(findings), 1)
        self.assertIn("dropped 1 incomplete", result.stderr)

    def test_no_findings_exits_1(self):
        result, _ = parse("nothing here")
        self.assertEqual(result.returncode, 1)

    def test_prose_without_done_when_is_rejected(self):
        result, _ = parse(review(done=None))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Done_When", result.stderr)

    def test_done_when_value_parsed(self):
        _, findings = parse(review(done="tests pass"))
        self.assertEqual(findings[0]["done_when"], "tests pass")

    def test_json_document_input(self):
        doc = {"summary": "s", "findings": [json_finding()]}
        result, findings = parse(json.dumps(doc))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(findings[0]["title"], "t")
        self.assertEqual(json.loads(result.stdout)["summary"], "s")

    def test_fenced_json_array_input(self):
        result, findings = parse("```json\n" + json.dumps([json_finding()]) + "\n```\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(findings), 1)

    def test_json_finding_missing_done_when_dropped(self):
        result, findings = parse(json.dumps([json_finding(), json_finding(done_when="")]))
        self.assertEqual(len(findings), 1)
        self.assertIn("dropped finding 2: missing done_when", result.stderr)

    def test_area_normalized(self):
        _, findings = parse(json.dumps([json_finding(area="Architectural Pattern")]))
        self.assertEqual(findings[0]["area"], "Architectural Patterns")

    def test_runs_in_isolated_mode(self):
        result = run("parse_findings.py", str(SCRIPTS / "mock_review.txt"), isolated=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class RenderOutputTest(unittest.TestCase):
    def test_loose_impact_effort_maps_to_canonical_bucket(self):
        for label in ["High impact / low effort (quick win)",
                      "high-impact, low-effort",
                      "Impact: High / Effort: Low"]:
            with self.subTest(label=label):
                result, md = render([finding(**{"Impact/Effort": label})])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("## ⚡ High Impact / Low Effort", md)
                self.assertNotIn(f"## {label}", md)

    def test_off_spec_label_still_rendered(self):
        _, md = render([finding(**{"Impact/Effort": "Medium"})])
        self.assertIn("## Medium", md)
        self.assertIn("#### H-001. x", md)

    def test_off_spec_json_levels_still_rendered(self):
        _, md = render([json_finding(impact="Medium")])
        self.assertIn("## Medium Impact / Low Effort", md)

    def test_prompt_with_code_fence_stays_inside_its_block(self):
        prompt = "Replace with:\n```python\nprint(1)\n```\nThen run tests."
        _, md = render([finding(LLM_Prompt=prompt)])
        self.assertIn("````text\n" + prompt + "\n\nDone when:\nd\n````", md)

    def test_plain_prompt_uses_three_backticks(self):
        _, md = render([finding()])
        self.assertIn("```text\nz\n\nDone when:\nd\n```", md)

    def test_every_finding_rendered_once(self):
        findings = [finding(Issue=f"issue {i}", Area=a)
                    for i, a in enumerate(["Architectural Pattern", "Code Quality", "Documentation Gap"])]
        _, md = render(findings)
        for f in findings:
            self.assertEqual(md.count(f"- **Issue:** {f['Issue']}"), 1)

    def test_legacy_finding_without_done_when_rejected(self):
        legacy = finding()
        del legacy["Done_When"]
        result, _ = render([legacy])
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing done_when", result.stderr)


class FullTemplateTest(unittest.TestCase):
    """render_output.py on a complete findings document."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def render_doc(self, doc, *args):
        result = run("render_output.py", "--root", str(self.root), "--goal", "g", *args,
                     stdin=json.dumps(doc))
        md = self.root / "inHindsight.md"
        return result, (md.read_text() if md.exists() else "")

    def sidecar(self):
        return json.loads((self.root / "inHindsight.json").read_text())

    def test_mock_document_renders_every_section(self):
        result = run("render_output.py", "--root", str(self.root), "--goal", "g",
                     str(SCRIPTS / "mock_review.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        md = (self.root / "inHindsight.md").read_text()
        self.assertTrue(md.startswith(f"# In Hindsight — {self.root.name}\n"))
        self.assertIn("Knowing what we know now", md)
        self.assertIn("#### H-001. Validation rules live in two places", md)
        self.assertIn("- **Evidence:** `hindsight/SKILL.md:54`", md)
        self.assertIn("- **Done when:** The 300-file cap", md)
        self.assertEqual(md.count("**Decision Matrix**"), 1)
        self.assertLess(md.index("H-001."), md.index("**Decision Matrix**"))
        self.assertLess(md.index("**Decision Matrix**"), md.index("H-002."))
        self.assertIn("## 📋 Cross-Reference Documentation Gap Report", md)
        self.assertNotIn("### LLM Action Prompt", md)

    def test_sidecar_is_normalized_document_with_ids(self):
        self.render_doc({"findings": [json_finding(), json_finding(title="u")]})
        doc = self.sidecar()
        self.assertEqual(doc["schema_version"], 1)
        self.assertEqual([f["id"] for f in doc["findings"]], ["H-001", "H-002"])
        self.assertEqual(doc["goal"], "g")

    def test_root_and_goal_can_come_from_document(self):
        doc = {"root": str(self.root), "goal": "from doc", "findings": [json_finding()]}
        result = run("render_output.py", stdin=json.dumps(doc))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.sidecar()["goal"], "from doc")

    def test_missing_root_fails(self):
        result = run("render_output.py", "--goal", "g", stdin=json.dumps([json_finding()]))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no root given", result.stderr)

    def test_more_than_one_decision_matrix_fails(self):
        doc = {"findings": [json_finding(decision_matrix=matrix(3)), json_finding(decision_matrix=matrix(3))]}
        result, _ = self.render_doc(doc)
        self.assertEqual(result.returncode, 1)
        self.assertIn("only the single most critical finding", result.stderr)
        self.assertFalse((self.root / "inHindsight.md").exists())

    def test_matrix_with_too_few_candidates_is_skipped_with_warning(self):
        result, md = self.render_doc({"findings": [json_finding(decision_matrix=matrix(2))]})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("**Decision Matrix**", md)
        self.assertIn("needs 3; skipped", result.stderr)

    def test_since_last_review_tally(self):
        doc = {"findings": [json_finding(id="H-002")], "since_last_review": [
            {"id": "H-001", "title": "a", "status": "resolved", "evidence": "fixed in x.py"},
            {"id": "H-002", "title": "b", "status": "Partially resolved"},
            {"id": "H-003", "title": "c", "status": "unresolved"},
        ]}
        _, md = self.render_doc(doc)
        self.assertIn("## Since Last Review\n\n3 previous finding(s): 1 resolved, 1 partially resolved, 1 unresolved.", md)
        self.assertIn("- **H-001 a** — Resolved: fixed in x.py", md)
        self.assertLess(md.index("## Executive Summary"), md.index("## Since Last Review"))
        self.assertLess(md.index("## Since Last Review"), md.index("## ⚡"))

    def test_gap_report_omitted_when_empty(self):
        _, md = self.render_doc({"findings": [json_finding()], "gap_report": []})
        self.assertNotIn("Gap Report", md)

    def test_rerun_archives_previous_and_never_reuses_ids(self):
        self.render_doc({"findings": [json_finding(), json_finding(), json_finding()]})
        first = (self.root / "inHindsight.md").read_text()
        # Re-run: H-002 carried forward, one new finding.
        result, _ = self.render_doc({"findings": [json_finding(id="H-002"), json_finding(title="new")]})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([f["id"] for f in self.sidecar()["findings"]], ["H-002", "H-004"])
        history = sorted((self.root / "hindsight-history").iterdir())
        self.assertEqual([p.name.split("-", 3)[-1] for p in history], ["inHindsight.json", "inHindsight.md"])
        self.assertEqual(len({p.name[:17] for p in history}), 1)
        self.assertEqual(history[1].read_text(), first)

    def test_repeated_reruns_do_not_overwrite_history(self):
        for _ in range(3):
            self.render_doc({"findings": [json_finding()]})
        self.assertEqual(len(list((self.root / "hindsight-history").iterdir())), 4)

    def test_duplicate_ids_reassigned(self):
        result, _ = self.render_doc({"findings": [json_finding(id="H-001"), json_finding(id="H-001")]})
        self.assertEqual([f["id"] for f in self.sidecar()["findings"]], ["H-001", "H-002"])
        self.assertIn("duplicate id H-001 reassigned", result.stderr)

    def test_runs_in_isolated_mode(self):
        result = run("render_output.py", "--root", str(self.root), "--goal", "g",
                     str(SCRIPTS / "mock_review.json"), isolated=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class ParseArgsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_output_is_valid_json_for_awkward_input(self):
        goal = 'C:\\path "quoted"\nsecond line\twith tab'
        result = run("parse_args.sh", "--root", self.tmp.name, "--goal", goal,
                     "--files", 'a\\b.py, c"d.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed["goal"], goal)
        self.assertEqual(parsed["files"], ["a\\b.py", 'c"d.py'])

    def test_nonexistent_root_fails(self):
        result = run("parse_args.sh", "--root", "/no/such/dir", "--goal", "g")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a directory", result.stderr)

    def test_flag_without_value_fails_with_message(self):
        result = run("parse_args.sh", "--goal", "g", "--root")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--root requires a value", result.stderr)

    def test_missing_goal_fails(self):
        result = run("parse_args.sh", "--root", self.tmp.name)
        self.assertEqual(result.returncode, 1)

    def test_more_than_300_files_fails(self):
        files = ",".join(f"f{i}.py" for i in range(301))
        result = run("parse_args.sh", "--root", self.tmp.name, "--goal", "g", "--files", files)
        self.assertEqual(result.returncode, 1)


class AggregateContextTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root = base / "proj"
        self.root.mkdir()
        (self.root / "a.py").write_text("print('a')\n")
        (self.root / "node_modules" / "pkg").mkdir(parents=True)
        (self.root / "blob.bin").write_bytes(b"head\x00tail")
        self.outside = base / "secret.txt"
        self.outside.write_text("outside\n")
        (self.root / "link.txt").symlink_to(self.outside)

    def aggregate(self, files, env=None):
        return run("aggregate_context.sh", "--root", str(self.root), "--files", files, env=env)

    def test_reads_file_inside_root(self):
        result = self.aggregate("a.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--- FILE: a.py ---\nprint('a')", result.stdout)

    def test_absolute_path_inside_root_is_read(self):
        result = self.aggregate(str(self.root / "a.py"))
        self.assertIn("print('a')", result.stdout)

    def test_paths_escaping_root_are_skipped(self):
        for f in [str(self.outside), "../secret.txt", "link.txt"]:
            with self.subTest(f=f):
                result = self.aggregate(f)
                self.assertEqual(result.returncode, 0)
                self.assertNotIn("outside", result.stdout)
                self.assertIn("outside --root", result.stderr)

    def test_binary_file_is_skipped(self):
        result = self.aggregate("blob.bin")
        self.assertNotIn("FILE: blob.bin", result.stdout)
        self.assertIn("binary file", result.stderr)

    def test_large_file_is_truncated_with_marker(self):
        (self.root / "big.txt").write_text("x" * 100)
        result = self.aggregate("big.txt", env={"HINDSIGHT_MAX_FILE_BYTES": "10"})
        self.assertIn("x" * 10 + "\n[... truncated by Hindsight: showed 10 of 100 bytes ...]",
                      result.stdout)
        self.assertNotIn("x" * 11, result.stdout)

    def test_dependency_dirs_pruned_from_tree(self):
        result = self.aggregate("a.py")
        self.assertNotIn("node_modules", result.stdout)

    def test_missing_file_warns_but_succeeds(self):
        result = self.aggregate("a.py,nope.py")
        self.assertEqual(result.returncode, 0)
        self.assertIn("file not found, skipping: nope.py", result.stderr)
        self.assertIn("Read 1 file(s), 1 missing", result.stderr)


class BuildPromptTest(unittest.TestCase):
    def test_capitalized_project_md_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "Project.md").write_text("PROJECT-CONTEXT-MARKER\n")
            result = run("build_prompt.sh", "--root", tmp, "--goal", "g", stdin="ctx")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PROJECT-CONTEXT-MARKER", result.stdout)

    def test_prompt_requests_json_with_done_when(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run("build_prompt.sh", "--root", tmp, "--goal", "g", stdin="ctx")
            self.assertIn("Respond with a single JSON object", result.stdout)
            self.assertIn('"done_when"', result.stdout)
            self.assertIn("Reconstruct what was intended", result.stdout)

    def test_inputs_inserted_literally(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "Project.md").write_text("cost is $HOME and `whoami`\n")
            result = run("build_prompt.sh", "--root", tmp, "--goal", "goal $(echo hi)",
                         stdin="ctx with $PATH")
            self.assertIn("cost is $HOME and `whoami`", result.stdout)
            self.assertIn('"goal $(echo hi)"', result.stdout)
            self.assertIn("ctx with $PATH", result.stdout)

    def test_missing_project_md_uses_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run("build_prompt.sh", "--root", tmp, "--goal", "g", stdin="ctx")
            self.assertEqual(result.returncode, 0)
            self.assertIn("no project.md found", result.stdout)


class DecisionMatrixTest(unittest.TestCase):
    def candidates(self, n):
        return [{"solution": f"Option {i} | piped", "impact": 3, "effort": 2,
                 "argument": "It's cheap; doesn't need a migration."} for i in range(n)]

    def test_three_candidates_render_table(self):
        result = run("render_decision_matrix.py", stdin=json.dumps(self.candidates(3)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Option 0 \\| piped", result.stdout)
        self.assertIn("It's cheap", result.stdout)

    def test_fewer_than_three_fails(self):
        result = run("render_decision_matrix.py", stdin=json.dumps(self.candidates(2)))
        self.assertEqual(result.returncode, 1)

    def test_heredoc_invocation_survives_apostrophes(self):
        payload = json.dumps(self.candidates(3))
        cmd = f"python3 '{SCRIPTS / 'render_decision_matrix.py'}' <<'CANDIDATES'\n{payload}\nCANDIDATES\n"
        result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class PackagingTest(unittest.TestCase):
    def test_scripts_are_executable(self):
        for path in SCRIPTS.iterdir():
            if path.suffix in (".sh", ".py") and path.read_text().startswith("#!"):
                with self.subTest(script=path.name):
                    self.assertTrue(path.stat().st_mode & stat.S_IXUSR)

    def test_pipeline_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            parsed = run("parse_findings.py", str(SCRIPTS / "mock_review.txt"), cwd=tmp)
            result = run("render_output.py", "--root", tmp, "--goal", "g",
                         stdin=parsed.stdout, cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(Path(tmp, "inHindsight.md").exists())


if __name__ == "__main__":
    unittest.main()
