# Agent Information Docs: Master Reference Guide

How to use Claude Code agents (subagents and agent teams) well in this workspace.
Last updated: 2026-10-11 · Main source: https://code.claude.com/docs/en/agent-teams

> **For Claude:** read this before spawning teammates or subagents. Add new lessons to section 11.

---

## 1. Which tool should I use?

| Situation | Use |
|---|---|
| Small, step-by-step, or same-file work | **Single session** (no agents) |
| Quick focused helper where only the result matters (research, search, verify) | **Subagent** |
| Parallel work where workers need to share findings, challenge each other, or split up a feature | **Agent team** |
| You run several sessions yourself and want them to pass notes | **Cross-session messaging** |
| You run parallel sessions by hand on separate copies of the code | **Git worktrees** |

**Subagents vs agent teams**

| | Subagents | Agent teams |
|---|---|---|
| Context | Own window; result goes back to the caller | Own window; fully independent |
| Communication | Report back to the main agent | Teammates message each other directly |
| Coordination | Main agent manages everything | Shared task list + messages; they self-coordinate |
| Best for | Focused tasks, only the result matters | Complex work needing discussion |
| Token cost | Lower | **Higher**: each teammate is a full Claude instance |

**Teams work best for:**
- Research and review
- New modules or features where each person owns a piece
- Debugging with competing theories
- Changes that cross layers (frontend / backend / tests)

**Teams are a bad fit for:**
- Sequential tasks
- Same-file edits
- Work with lots of dependencies

---

## 2. Setup on this machine

- **Enabled:** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in `C:\Users\14704\.claude\settings.json` (all projects, set 2026-10-11)
  ```json
  { "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
  ```
- **Needs an interactive session.** No teammates are spawned in `-p` (headless) mode or Agent SDK sessions.
- **Side effect:** while teams are on, any subagent that Claude *names* launches as a teammate, so teams can form without being asked for.
- **To turn it off:** set the value to `"0"`. It applies on save, with no restart needed.

---

## 3. How teams work

| Part | What it does |
|---|---|
| **Team lead** | The main session. Spawns teammates, assigns tasks, combines results |
| **Teammates** | Separate Claude Code sessions, each with its own context window |
| **Task list** | Shared work items: pending → in progress → completed |
| **Mailbox** | Messages between agents, delivered automatically (no polling) |

- **Task dependencies:** a blocked task can't be claimed until the tasks it depends on are done. They unblock automatically.
- **Claiming:** uses file locking, so two teammates can't grab the same task.
- **Assigning:** the lead assigns tasks, or teammates self-claim the next open task.
- **Idle notice:** when a teammate stops, the lead is notified automatically with its final answer.
- **What teammates load:** CLAUDE.md, MCP servers and skills. **They do NOT get the lead's chat history**, only the spawn prompt.
- **Storage:**
  - Team config: `~/.claude/teams/{team-name}/config.json`. It's created automatically, so don't edit it.
  - Tasks: `~/.claude/tasks/{team-name}/`. Kept after the session ends.
  - Mailboxes: `~/.claude/teams/{team-name}/inboxes/{agent}.json`
- **Hard rules:**
  - One team per session
  - No nested teams (teammates can't spawn teammates)
  - The lead can't be changed

---

## 4. Starting a team: how to prompt

**Checklist for every spawn prompt:**
- [ ] How many teammates, and a **name** for each (so you can refer to them later)
- [ ] Each teammate's role and **which files/folders it owns**
- [ ] All the context it needs: goal, tech stack, constraints, file paths. It has no chat history.
- [ ] What "done" looks like (deliverable + where to save it)
- [ ] Model, if you care, e.g. "Use Sonnet for each teammate"
- [ ] Whether it should plan first

**Template:**
```text
Spawn 3 teammates for <goal>:
- "data": owns <folder>. Task: <...>. Done when <...>.
- "backend": owns <folder>. Task: <...>. Done when <...>.
- "frontend": owns <folder>. Task: <...>. Done when <...>.
Context: <stack, constraints, rules from CLAUDE.md>.
Each teammate edits only its own files. Message each other about shared interfaces.
Wait for all teammates to finish before combining results.
```

**Plan first (for risky or complex work):**
- Switch the lead into **plan mode first**, then spawn teammates. They stay read-only until their plan is approved.
- ⚠️ The lead approves teammate plans **automatically** without you reviewing them. If you want to review, ask the lead to show you each plan first.
- After approval, teammates' edits still go through the normal permission prompts.

**Reusable roles (subagent definitions):**
- Put a role in `.claude/agents/<name>.md` (project) or `~/.claude/agents/` (user), then say "Spawn a teammate using the <name> agent type…"
- Fields that apply to teammates:
  - `tools`
  - `model`
  - `disallowedTools`
  - `effort`
  - the body, added as extra instructions
- `skills` is **not** applied; teammates load skills from settings.
- Don't hand-write `~/.claude/teams/…` or a project `teams.json`. Neither works as config.

**How the model is picked (first match wins):**
1. The spawn prompt
2. The agent definition's `model`
3. `CLAUDE_CODE_SUBAGENT_MODEL`
4. The lead's model

---

## 5. Controls (in-process mode, which works in VS Code)

| Key | Action |
|---|---|
| ↑ / ↓ | Select a teammate in the agent panel (below the prompt) |
| Enter | Open its transcript and message it directly |
| Esc | Clear the selection. While viewing a teammate, Esc interrupts its current turn |
| `x` | Stop the selected teammate |
| Ctrl+T | Show or hide the task list |

- **Idle rows:** hidden 30 seconds after everyone is idle. The teammate is still running; message it by name to bring the row back.
- **More than 3 idle:** extra rows collapse into "N idle agents". Press Enter to expand.
- **While viewing a teammate:**
  - Plain text and skills go to that teammate.
  - Built-in commands go to the lead.
  - `/compact`, `/clear` and `/rewind` ask you to confirm first.
  - `/model` and `/fast` are blocked.
- **Shut down:** "Ask the <name> teammate to shut down". It can accept or refuse. Cleanup is automatic when the session ends.
- **Display mode:** the `teammateMode` setting (`"in-process"` is the default, or `"auto"`, `"tmux"`, `"iterm2"`), or the `--teammate-mode` flag.
  - ⚠️ **Split panes don't work in VS Code's terminal or Windows Terminal.** Stay on in-process mode on this PC.

---

## 6. Permissions and safety

- Teammates start in the lead's permission mode, except `dontAsk`. You can change a teammate's mode after it spawns, but not at spawn time.
- **Teammate permission prompts show up in the lead session.** Approve them there.
- **Fewer interruptions:** pre-approve common safe commands before spawning, using the `/fewer-permission-prompts` skill or permissions in settings.json.
- A message from another agent **never counts as your approval**. Teammates can't approve on your behalf or get around a denial.

---

## 7. Quality gates with hooks

Set these in settings.json hooks. Exit code **2** blocks the action and sends feedback.

| Hook | When it runs | What exit 2 does |
|---|---|---|
| `TeammateIdle` | A teammate is about to go idle | Keeps it working, with your feedback |
| `TaskCreated` | A task is being created | Stops the task being created |
| `TaskCompleted` | A task is being marked done | Stops it being marked complete (e.g. tests must pass) |

---

## 8. Best practices checklist

- **Team size:** start with **3–5 teammates**. Three focused ones often beat five scattered ones.
- **Task size:** about **5–6 tasks per teammate**, each a self-contained deliverable (a function, a test file, a review).
  - Too small: the coordination costs more than it saves.
  - Too big: teammates work too long without checking in.
- **Avoid file conflicts:** each teammate owns different files. Two editors on one file means overwrites.
- **Give full context:** the spawn prompt is all a teammate knows, apart from CLAUDE.md.
- **New to teams?** Start with research or review tasks before parallel coding.
- **Monitor and steer:** check in, redirect, and combine results as they arrive. Don't leave a team unattended for long.
- **Lead doing the work itself?** Tell it: *"Wait for your teammates to complete their tasks before proceeding."*
- **Cost:** tokens grow with every active teammate.
  - Use teams for research, review and new features.
  - Use a single session for routine work.
  - Optional: `"subagentPromptCacheTtl": "1h"` keeps teammate caches longer, but 1-hour cache writes cost more.

---

## 9. Troubleshooting and limitations

| Problem | Fix |
|---|---|
| Teammates not showing up | Look in the agent panel below the prompt. The row may just be hidden while idle. The task may have been too simple to need a team |
| Claude used subagents instead | Ask again and **explicitly say "agent team"** |
| Teammates showing up when you wanted subagents | Set the env var to `"0"` |
| Too many permission prompts | Pre-approve commands before spawning |
| Teammate stopped early | Open its transcript, then give it more instructions or spawn a replacement |
| Lead declares the work finished too soon | Tell it to keep going |
| Task stuck as "in progress" | Check whether the work is actually done, then mark it complete or ask the lead to nudge that teammate |
| Teammates gone after `/resume` or `/rewind` | Expected: in-process teammates aren't restored. Tell the lead to spawn new ones |
| Slow shutdown | Normal: teammates finish their current step first |

**Other limits:**
- Teammates can't run background subagents.
- Only the lead manages the team.

---

## 10. Use case templates

**Parallel review**
```text
Spawn three teammates to review <target>:
- one focused on security
- one on performance
- one on test coverage
Have each report findings with severity; then synthesize.
```

**Competing-hypotheses debugging**
```text
<Bug description>. Spawn 5 teammates to investigate different hypotheses.
Have them message each other to try to disprove each other's theories.
Update <findings doc> with the consensus.
```

**Research (fits content creation)**
```text
Spawn 3 teammates to research <topic> from different angles: <angle A>, <angle B>,
<angle C>. Cite sources. One teammate plays devil's advocate. Save the combined
summary (bullet points) to output/<name>.md.
```

**MapleStory Classic DB: Phase 2 build (cross-layer)**
```text
Spawn 3 teammates to build Phase 2 of maple-classic-db/ (see plan file and
output/source-audit.md). Use SAMPLE data only — no scraping Henesys.gg, MeowDB,
or OSMS until permission is confirmed. Stack: Python, SQLite + SQLAlchemy,
FastAPI + Jinja2 + HTMX, Pico.css. User is a beginner — keep code simple and commented.
- "data": owns app/models.py, app/db.py, scraper/, data/. Build tables (items,
  monsters, drops, npcs, shop_items, sources, price_reports, drop_reports) and
  a seed script with ~30 sample items.
- "backend": owns app/main.py and app/services/. Routes for search, item,
  monster, NPC pages; price + drop report endpoints; median with IQR outlier filter.
- "frontend": owns app/templates/ and app/static/. Search with autocomplete,
  item/monster/NPC pages, report forms, Chart.js price history.
Agree on model/field names via messages before coding. Each owns only its files.
Wait for all to finish, then run the app and verify end-to-end.
```

**How to restart a saved team (MapleStory)**
- Teammates don't survive a restart or `/resume`, but their **roles are saved** in `.claude/agents/`:
  - `data-engineer.md`
  - `backend-dev.md`
  - `frontend-dev.md`
- Each role file holds the files that teammate owns, its tasks, who to message, and the rules.
- To bring the team back, say:
  > "Spawn the MapleStory team using the data-engineer, backend-dev, and frontend-dev agent types. Pick up from the plan and the current code."
- Teammates re-read the plan, the contracts (`maple-classic-db/docs/`) and the code, then carry on. Nothing is rebuilt.
- **Edit a role:** change its `.md` file. The new version applies the next time it's spawned.
- Agent files created mid-session might not be picked up until the next session. If an agent type isn't found, spawn a general-purpose teammate and paste the role file into its prompt.

**Installed skills (user-level, `~/.claude/skills/`, all projects)**
Teammates load these too. They don't load skills listed in an agent definition's `skills` field.

| Skill | Use it for | Notes |
|---|---|---|
| `find-skills` | Searching and installing skills (`npx skills find <query>`) | Read every skill's SKILL.md before installing; skills run with full permissions |
| `frontend-design` (anthropics) | Polishing site visuals before public launch | Writes a design plan first, then builds |
| `tdd` (mattpocock) | Test-first features and bug fixes | Asks the user to confirm "seams" (what to test) before writing tests |
| `handoff` (mattpocock) | `/handoff`: summarizes the session into a doc for a fresh session | User-invoked only; saves to `%TEMP%` |
| Built in | `/code-review`, `/security-review`, `dataviz`, `simplify` | No install needed |

- Installing needs Git: installed 2026-10-11 via `winget install Git.Git`.
- Command: `npx skills add <owner/repo@skill> -g -y`. Ignore any "PromptScript" error; that's a different tool.
- Considered for later: `fastapi/fastapi@fastapi` (official FastAPI skill) and `supabase/...postgres-best-practices` (for the Phase 5 move to Postgres).

---

## 11. Lessons learned log

Add a row after each team run. This section is how the guide gets better over time.

| Date | What we did | What went well / badly | Do next time |
|---|---|---|---|
| 2026-10-11 | Spawned MapleStory Phase 2 team (data-engineer, backend-dev, frontend-dev) | Agent types created in `.claude/agents/` during the session were "not found". Fell back to general-purpose teammates told to read their role file | Create agent files one session *before* you need them, or keep spawn prompts self-contained ("read your role file at …") |
| 2026-10-11 | Phase 2 build: 3 teammates, ~5 min each, 31 tests passing | **Went well:** contract-first (data-engineer posted `data-contract.md` first, backend posted `api-contract.md`) let all three work in parallel. Teammates settled 4 field additions directly with no lead involvement. Strict file ownership meant zero conflicts. **Watch:** backend briefly waited for a contract that had already been sent (messages crossed), and the lead had to nudge it. Teammates can't open a browser, so the lead still has to test end-to-end | Keep the contract-first opening step. Have the lead run live HTTP checks after the team finishes. Teammates' final reports repeat their earlier messages, so expect duplicates |
| 2026-10-11 | Phase 3: redesign + item browser + crafting/quest data (3 teammates, ~10–15 min each, 64 tests) | **Went well:** saved agent types loaded this time. The "design plan first, user approves, then build" gate worked; frontend-dev used the frontend-design skill and took headless screenshots. Teammates settled a data question among themselves (Pole Arm class codes). **Watch:** backend-dev wrongly said stat requirements weren't in the data, and the lead caught it. Teammate names get reused across phases, so old messages can route to the new agents. Teammates still can't click in a browser | For visual work, always gate on a design plan the user approves. The lead should check "not in the data" claims against the raw files. Ask the user to click-test HTMX interactions |

---

## 12. Sources
- Agent teams: https://code.claude.com/docs/en/agent-teams
- Subagents: https://code.claude.com/docs/en/sub-agents
- Settings: https://code.claude.com/docs/en/settings
- Hooks: https://code.claude.com/docs/en/hooks
- Costs (agent team tokens): https://code.claude.com/docs/en/costs#agent-team-token-costs
- Permissions: https://code.claude.com/docs/en/permissions
- Full docs index: https://code.claude.com/docs/llms.txt
