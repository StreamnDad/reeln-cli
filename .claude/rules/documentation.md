---
globs: ["docs/**", "README.md", "CHANGELOG.md"]
---

# Documentation Rules

**README and docs must be updated with each user-facing phase. No feature ships without documentation.**

## What goes where

| Content | Location |
|---|---|
| Project overview, install, quick start | `README.md` |
| Detailed guides, tutorials | `docs/guide/*.md` |
| CLI command reference | `docs/cli/*.md` |
| Install instructions | `docs/install.md` |
| Getting started tutorial | `docs/quickstart.md` |
| Changelog | `CHANGELOG.md` (included in docs via `docs/changelog.md`) |

## Conventions

- All docs in Markdown (MyST parser for Sphinx)
- Use `:::{note}` / `:::{warning}` for admonitions
- Cross-reference with `{doc}` role: `{doc}`/guide/configuration``
- Code blocks with language specifier: ````bash`, ````python`, ````json`
- Every new CLI command gets a docs page entry in the appropriate `docs/cli/*.md` file
- Every new config option gets documented in `docs/guide/configuration.md`
- Every new sport gets added to `docs/guide/sports.md`
- Run `make docs` to build locally, `make docs-serve` to preview at `http://localhost:8000`
