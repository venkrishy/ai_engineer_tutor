## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues and are managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Branches

Each ticket gets its own branch. Name it `feature/ticket-<number>-<shortname>`, for example `feature/ticket-2-letter-reply`. Base the branch on the previous ticket's branch so the work stacks. Implement one ticket in its own fresh context, then stop.
