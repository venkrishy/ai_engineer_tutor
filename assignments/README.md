# Assignment bundles

One folder per assignment, in the shape `tutor/catalog.py` describes. Upload a folder with
`python3 scripts/upload_assignment.py assignments/triage` or zip it and use the dashboard.

`tickets.json` in each level holds the hidden tickets and their answer key. It is not committed,
because this repository is public. Keep the real files on your machine and in S3 only.

## Pages and extra level files

Beside the files the catalog reads, each level folder holds files for its two web pages:

- `rules.md`: the rules in plain words.
- `samples.json`: public examples, `[{"input": {...}, "output": {...}}]`. They must differ from the hidden tickets; use ids like `S-1`.
- `hints.md`: one hint per failed try, separated by lines of `---`. The catalog stores it too.

Build the pages with `python3 scripts/build_pages.py assignments/triage` and commit the `.html` files.
GitHub Pages publishes them and the emails link to them (`tutor/links.py`). The level folder must be named
`NN-name` after its position and name, such as `01-classify`, or the links break. The page text comes from
these files, so edit them here, not in the dashboard.
