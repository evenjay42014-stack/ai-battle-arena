# Mini Task Board — project brief

Tiny web app: local Flask + vanilla JS kanban with three columns (Todo / Doing / Done).

## Goals
- Add/edit/delete cards; persist to SQLite
- No auth in v0; single-user desktop use
- Keep deps minimal (Flask, sqlite3)

## Non-goals
- Multiplayer, OAuth, mobile apps

## Open questions
- Should drag-and-drop be required for v0?
- Export to JSON?

## Risks
- XSS if card titles are unsanitized
- Schema migrations later
