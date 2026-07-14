# Sill Creation Specification

*note* this is a sample Project.md file to illustrate the file structure. This content gets copied verbatim into the P-Prompt when its created. You should define a Projct.md in your repo in a similar structure to provide project specific context to the LLM.

## Idea
Hindsight is a developer skill (`/hindsight`) that analyzes a project directory and all associated documentation. It performs a comprehensive architectural and technical review based on explicit user goals, outputting actionable insights to `inHindsight.md`.

## Ambition
The final iteration of Hindsight will function as an integrated 'Architectural Review Board'. It will not only identify flaws but will also generate weighted decision matrices (Impact/Effort) and provide full-fidelity, optimized LLM prompts ready for execution, accelerating the leap from code to production-ready architecture.

## Goal
Implementing a command-line skill that accepts: 
1) A project root path; 
2) The list of files to scan (max 300); and 
3) A mandatory user goal/use case string. 

The tool must read the code and documentation, identify at least one improvement area for each type (Code Quality, Documentation Gap, Architectural Pattern), write these findings into a structured `inHindsight.md` file, and group results by Impact/Effort ranking.

