# CLAUDE.md

This repository is a toolkit for AI agents. **Follow [AGENTS.md](AGENTS.md)**: it is the
procedure for every uncreep task.

@AGENTS.md

Claude Code specifics:
- Phase 4: ask with the `AskUserQuestion` tool (`multiSelect: true`, max 4 options per question,
  so group findings or ask in rounds) when it's available; otherwise use a numbered list.
- Phase 6 in Claude Code on the web: if a file-sending tool is available, send the APK to the user
  directly. Otherwise use the GitHub route in docs/delivery.md, and only to a private repository.
  Check visibility with the GitHub tools first.
- The `uncreep` skill (`.claude/skills/uncreep/`) and the REA skill and MCP server (`.mcp.json`) are
  available in this project.
