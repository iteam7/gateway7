@AGENTS.md

# Claude Code specifics

- Agents live in `.claude/agents/`: `Orchestrator` (dispatcher, start it with `claude --agent Orchestrator`) `Formater` (checks and git), and `TechLead` (architecture, developer task planning, code review).
- Run the PRE, POST, and Git steps from `AGENTS.md` through the `Formater` agent, before and after every task, including tasks delegated to other agents.
- If `Formater` returns `BLOCKED`, do not proceed; if it returns `CHANGES REQUIRED`, fix and run POST again.
