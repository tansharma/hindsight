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


def run(script, *args, stdin=None, env=None, cwd=None):
    interpreter = ["bash"] if script.endswith(".sh") else [sys.executable]
    return subprocess.run(
        interpreter + [str(SCRIPTS / script), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        cwd=cwd,
    )


def review(area="Code Quality", issue="x", rationale="y",
           impact="High Impact / Low Effort", prompt="z", style="**{label}**"):
    rows = [("Area", area), ("Issue", issue), ("Rationale", rationale),
            ("Impact/Effort", impact), ("Suggested LLM Action Prompt", prompt)]
    return "\n".join(f"{style.format(label=label)} {value}" for label, value in rows) + "\n"


def parse(text):
    result = run("parse_findings.py", stdin=text)
    return result, (json.loads(result.stdout) if result.returncode == 0 else None)


def render(findings):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "inHindsight.md"
        result = run("render_output.py", "--root", tmp, "--goal", "g", "--out", str(out),
                     stdin=json.dumps(findings))
        return result, (out.read_text() if out.exists() else "")


def finding(**overrides):
    base = {"Area": "Code Quality", "Issue": "x", "Rationale": "y",
            "Impact/Effort": "High Impact / Low Effort", "LLM_Prompt": "z"}
    return {**base, **overrides}


class ParseFindingsTest(unittest.TestCase):
    def test_mock_review_parses_three_findings(self):
        result = run("parse_findings.py", str(SCRIPTS / "mock_review.txt"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)), 3)

    def test_colon_inside_bold_labels(self):
        result, findings = parse(review(style="- **{label}:**"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(findings[0]["Area"], "Code Quality")
        self.assertEqual(findings[0]["LLM_Prompt"], "z")

    def test_colon_after_bold_labels(self):
        _, findings = parse(review(style="**{label}**:"))
        self.assertEqual(findings[0]["Issue"], "x")

    def test_list_marker_does_not_leak_into_previous_value(self):
        _, findings = parse(review(style="- **{label}:**"))
        self.assertEqual(findings[0]["Issue"], "x")
        self.assertEqual(findings[0]["Rationale"], "y")

    def test_value_on_next_line(self):
        _, findings = parse(review(style="**{label}**\n"))
        self.assertEqual(findings[0]["Rationale"], "y")

    def test_numbered_findings(self):
        text = "1. " + review(issue="first") + "\n2. " + review(issue="second")
        _, findings = parse(text)
        self.assertEqual([f["Issue"] for f in findings], ["first", "second"])

    def test_label_mentioned_inside_prompt_is_not_a_new_finding(self):
        prompt = "Update the template so each finding has an **Area** label first."
        result, findings = parse(review(prompt=prompt))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["LLM_Prompt"], prompt)
        self.assertNotIn("dropped", result.stderr)

    def test_labels_inside_fenced_code_are_ignored(self):
        prompt = "Use this format:\n```markdown\n**Area** Code Quality\n**Issue** demo\n```\nDone."
        _, findings = parse(review(prompt=prompt))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["LLM_Prompt"], prompt)

    def test_incomplete_findings_are_reported(self):
        text = review() + "\n**Area** Code Quality\n**Issue** orphan\n"
        result, findings = parse(text)
        self.assertEqual(len(findings), 1)
        self.assertIn("dropped 1 incomplete", result.stderr)

    def test_no_findings_exits_1(self):
        result, _ = parse("nothing here")
        self.assertEqual(result.returncode, 1)


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
        self.assertIn("#### 1. x", md)

    def test_prompt_with_code_fence_stays_inside_its_block(self):
        prompt = "Replace with:\n```python\nprint(1)\n```\nThen run tests."
        _, md = render([finding(LLM_Prompt=prompt)])
        self.assertIn("````text\n" + prompt + "\n````", md)

    def test_plain_prompt_uses_three_backticks(self):
        _, md = render([finding()])
        self.assertIn("```text\nz\n```", md)

    def test_every_finding_rendered_once(self):
        findings = [finding(Issue=f"issue {i}", Area=a)
                    for i, a in enumerate(["Architectural Pattern", "Code Quality", "Documentation Gap"])]
        _, md = render(findings)
        for f in findings:
            self.assertEqual(md.count(f"- **Issue:** {f['Issue']}"), 1)


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
            if path.suffix in (".sh", ".py"):
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
