[Hindsight](index.md) › Helper scripts

# Using the helper scripts directly

The agent runs these for you during a review, but they also work on their own (`S=hindsight/scripts`, or wherever you installed the skill):

```bash
bash "$S/list_files.sh" --root path/to/project > files.txt          # the files a review would scan
python3 "$S/import_graph.py" --root path/to/project --files-from files.txt > graph.json
python3 "$S/render_output.py" --check --root path/to/project --goal "..." findings.json   # validate only
python3 "$S/render_output.py" --root path/to/project --goal "..." findings.json           # write inHindsight.md/.json
```

`render_output.py --check` exits 0 when a findings document is clean, 2 when it has warnings (unverifiable evidence, an unaddressed area, a re-run that doesn't account for the previous review), and 1 when it can't be rendered. A real render moves any previous review into `hindsight-history/` first. Script internals are documented in `hindsight/references/scripts.md`.

Next: [Developing the skill](development.md)
