# Hindsight — Project Specification

> **Note**
>
> This is a sample `Project.md`: it shows a structure (Idea, Ambition, Goal)
> for stating a project's intent in one place. It is also Hindsight's own
> intent document. Hindsight reads documentation before code to learn what a
> project's authors intended, so a file like this at your repository root
> gives every review a clear baseline to judge the code against.
>
> To use it, copy it to your repository root and replace the content below
> with your own project's, deleting this note.

## Idea
Hindsight is a developer skill (`/hindsight`) that analyzes a project directory and all associated documentation. It performs a comprehensive architectural and technical review based on explicit user goals, outputting actionable insights to `inHindsight.md`.

## Ambition
The final iteration of Hindsight will function as an integrated 'Architectural Review Board'. It will not only identify flaws but will also generate weighted decision matrices (Impact/Effort) and provide full-fidelity, optimized LLM prompts ready for execution, accelerating the leap from code to production-ready architecture. Its reviews must be consistent, reliable, and highly accurate: every claim checkable against the code, and the same project ranked the same way from run to run.

## Goal
Implement an Agent Skill that accepts:
1) A project root path;
2) The list of files to scan (a guideline of 300, which the user may knowingly exceed); and
3) A mandatory user goal/use case string.

The skill must read the documentation first and then the code, and address each area (Architectural Patterns, Code Quality, Documentation Gaps) with at least one finding, or with an explicit "no findings" entry stating why the area is clean. It writes the findings, with verifiable evidence and a ready-to-paste fix prompt each, to a structured `inHindsight.md` (plus `inHindsight.json`), grouped by Impact/Effort ranking.
