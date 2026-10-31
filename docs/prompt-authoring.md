# Readable prompts

Shared runtime instructions live in `okabebot/prompts/*.md`: conversation, routing,
continuation, memory, tool replies, worker modes, judge and evaluated treatment
candidate. Character personas and welcome styles live in
`okabebot/characters/<id>/*.md` and load through the character interface. Python
owns request construction and typed schemas.
Historical frozen evaluation inputs remain in `evals/`; they are not silently rewritten.

`from .prompts import prompt` loads a named bundled template and compacts static
whitespace before substituting strict `$slot` values. Missing slots fail. Literal
JSON braces need no escaping. Use `$$` for a literal dollar sign in static text.
Dynamic source/user data is inserted afterward, so its whitespace and `$` text
remain literal; it is never interpreted as another template. The loader accepts
bundled names only and caches static files for the process lifetime. Restart a
worker after changing a file. Wheels include the Markdown files.

Keep paragraphs and line wrapping readable. This loader is for prose instructions,
not whitespace-sensitive code or few-shot payloads. Runtime owner treatments remain
private and editable in the dashboard; they are not copied into the bundled files.
This extraction changes whitespace, not intended policy. It does not by itself
establish an improvement in model quality; rerun the labelled evals for policy edits.
