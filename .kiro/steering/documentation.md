# Documentation Organization

- All documentation lives in `docs/`. The only markdown allowed in the repo root is `README.md`.
- Keep `README.md` lean: overview, key features, a diagram, a short quick start, and the doc index. Link to `docs/` for anything longer.
- One canonical source per topic (see the table in `project.md`). Never duplicate content across files — cross-reference with relative links and edit only the canonical file.
- When you change code, update the matching doc in the same change:
  - config/env vars → `docs/GETTING_STARTED.md` and `.env.example`
  - API endpoints → `docs/API_SERVER.md`
  - setup/commands → `docs/GETTING_STARTED.md` and the README quick start
  - new tool/skill examples → `docs/HOW_TO.md`
- `docs/INDEX.md` is the source of truth for the active doc set. When adding or renaming a doc, update `INDEX.md` (and the README index for a major feature). Never reference archived or non-existent files.

## Environment Variables

- All runtime config documented in `.env.example` (every variable). Never commit `.env`.
- Use pydantic-settings for validation. Update `.env.example` and `docs/GETTING_STARTED.md#configuration` whenever you add a variable.
