# Project Context

This is my AI agent workspace. I use it for research, content creation, editing, web scraping, data base creation, and productivity work flows.

# About Me

I create content on multiple different social media channels. They focus on daily vlogs, food, pokemon trading cards(Pack pulling and buying packs), and I also am looking into creating applications for webscraping video games. Each channel is unique, but I like a more honest, not overly edited style.

# Rules

-Always ask clarifying question before starting a complex task
-Show your plan and stops before executing
-keep reports and summaries concise - bullet points over paragraphs
-Save all outfiles to the output folder
-cite sources when doing research

# Project structure

-workflows/ - Workflow instruction files (plain english recipes the agent follows)
-output/ - Finished deliverables(reports, drafts, analysis)
-resources/ - Reference docs and templates
-resources/agent-information-docs.md - Master guide for agent teams/subagents; read before spawning agents and add lessons learned after team runs
-portable/ - Export/import scripts for moving everything to another laptop. Backup = Documents\Claude-Workspace-Backup.zip (auto-updated at end of every session; see portable/RESTORE.md)

# This repository (maple-classic-db)

Restored from Claude-Workspace-Backup.zip (2026-10-12) so cloud sessions get the same groundwork as the laptop.

- STATUS.md - project status, live site, waiting-on-you list. Read it first and update it at the end of every phase.
- docs/ - data, API and design contracts
- resources/agent-information-docs.md - agent team guide (copied from the workspace)
- .claude/agents/ - teammate roles: data-engineer, backend-dev, frontend-dev. Their paths are Windows laptop paths; in a cloud session use `python` from the repo root instead of `.venv\Scripts\python`.
- .claude/skills/ - find-skills, frontend-design, tdd, handoff, last30days
- Data source rules (no Henesys.gg; MeowDB only with permission; MesoWatch link only) are in STATUS.md and still apply.

## last30days skill
- Researches what people said about a topic in the last 30 days (Reddit, Hacker News, YouTube, X, GitHub, web and more).
- Run `/last30days <topic>`. Health check: `python3 .claude/skills/last30days/scripts/last30days.py doctor`.
- Cloud sessions: the environment's network policy must allow reddit.com, hn.algolia.com and similar hosts, or only GitHub and web search work.
- Demo media in the upstream `assets/` folder was left out to keep the repo small. Source: https://github.com/mvanhorn/last30days-skill (MIT).