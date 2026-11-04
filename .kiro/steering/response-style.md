# Response Style

Keep responses concise and proportional to the task. This is the default for all work in this project.

- Lead with the answer or the change. Skip preamble, restating the request, and filler acknowledgments.
- For code changes, a one or two sentence summary is enough. Do not narrate every step or re-explain code that is self-evident from the diff.
- Prefer prose for explanations and short bullet lists for sequences. Avoid headers and multi-section write-ups for simple tasks.
- Do not paste large code blocks back into chat when the edit is already applied to a file. Reference the file instead.
- Show, don't tell: no hyperbole, no superlatives, no exaggerated punctuation.
- Only go long when the user explicitly asks for detail, a design discussion, or a review.

## Documentation Updates

When applying improvements or adding features, update the matching documentation in the same change — never defer it.

- Follow the rules in `documentation.md` for where content lives.
- Config/env vars → `docs/GETTING_STARTED.md` and `.env.example`.
- API endpoints → `docs/API_SERVER.md`.
- Setup/commands → `docs/GETTING_STARTED.md` and the README quick start.
- New tool/skill examples → `docs/HOW_TO.md`.
- When adding or renaming a doc, update `docs/INDEX.md`.
