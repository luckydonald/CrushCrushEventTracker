# Log Direct Codex Shell Executions

## Summary

Extend the prompt logger to capture direct user shell commands from the Codex transcript and add them to `ai[/°base]/query.md`. Only user-executed commands are included; agent tool calls remain excluded.

Because Codex provides no dedicated hook for these commands, capture occurs at the next ordinary prompt. The transcript is available to hooks but is explicitly documented as an unstable interface, so parsing will be narrow and fail-soft. [Codex hooks documentation](https://learn.chatgpt.com/docs/hooks)

## Implementation Changes

- In `save-prompt/hook.py`, scan `transcript_path` up to the current prompt and collect `<user_shell_command>` records since the preceding real user prompt. Ignore injected user-context fragments and agent-issued shell tools.
- Parse the command, exit code, duration, and `Output:` payload. Preserve output without truncation or redaction in sequential `output/commands/NNN.log` files.
- Add a question-style `<details>` block to `query.md` for each command, showing a console-style command summary, full command when multiline, exit code, duration, and a character/size link to its `.log` file.
- Write all commands caught in one pass as a single commit containing both `query.md` and the generated logs. Use `ai: command NNN result` or `ai: commands NNN-NNN results`, retaining existing `[base]` and `.by-issue` prefixes.
- Capture commands before prompt filtering so they are not lost when the following prompt is skipped or normalized. Afterwards, continue the existing prompt-logging path unchanged.
- Update the repository hook documentation to mention caught-up direct Codex command executions. No settings or generated hook configuration changes are required.

## Artifact Contract

- Logs live beside the routed query log under `output/commands/001.log`, `002.log`, and so on.
- Each `.log` contains exactly the transcript’s `Output:` content; an empty command result creates an empty log.
- Missing, unreadable, malformed, or changed transcript records produce no partial command artifacts and do not interfere with normal prompt logging.

## Test Plan

- Cover successful and nonzero commands, multiple commands between prompts, multiline commands, multiline and empty output, and exact output preservation.
- Verify command blocks precede the following prompt, older commands are not repeated, injected context does not reset command collection, and agent shell tool calls are excluded.
- Verify skipped/normalized prompts still flush pending commands.
- Verify base, consuming-repository, and `.by-issue` routing, sequential numbering, commit subjects, and atomic inclusion of `query.md` plus log files.
- Verify absent or malformed transcripts fail softly and Claude/Copilot behavior remains unchanged.
- Run the focused AI-hook routing tests, then the complete `scripts/°base` unittest suite.

## Assumptions

- “Raw output” means the complete combined `Output:` field supplied by Codex, with no secret filtering or size limit.
- Capture is deferred until the next ordinary prompt, including a prompt after resuming the session. A final shell command followed by no future prompt cannot be captured by the documented hook lifecycle.
