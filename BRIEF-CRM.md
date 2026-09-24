# Brief: CRM front end

For an Antigravity agent. Read `AGENTS.md` first — its rules apply here too.

## What this is

A local control room for the agent system: which brands are in play, what the agents are doing,
who has been contacted, and what came back. One operator, one machine, runs locally.

## Data contract

**Read:** `shared/data/dashboard.json` — regenerate with `python3 tools/build_dashboard.py`.
It already contains `stats`, `funnel`, `agents`, `brands` (102), `scripts` (12), `activity`
(the status log) and `production`. **Do not read the repo's other files.** That file is the
contract; if a field is missing, ask for it to be added rather than reaching around it.

**Write:** `shared/data/crm.json` — yours alone. Nothing else in the repo may be written.
Needs a small local backend; a static page cannot persist. Keep it minimal (a single Python
or Node process serving the UI and a few JSON endpoints). No database server, no cloud, no auth.

## Screens

**1. Pipeline** — the default view. Columns `prospect · researched · scripted · drafted ·
contacted · replied · client`. Cards show brand, fatigue score, ad count, days silent, segment.
Drag a card to change stage; that write persists. Sort by score. Filter by segment.

**2. Brand** — one brand. Its numbers, its scripts with hooks visible, its outreach draft,
contact record, and a free-text activity log the operator can append to.

**3. Agents** — the five roles, their event counts, blocked counts, last activity. Below, the
status feed from `activity`, newest first, colour-coded by state (DONE / BLOCKED / FLAG / NOTE).
This is the "watch them work" screen.

**4. Outreach** — contact records, send log, replies. **Today this is empty and must render as
empty**, with a clear prompt to add a contact. Adding one records email, role, source (where the
address was read) and date. Marking one sent records the date. Logging a reply records date and
free text.

**5. Production** — render queue state, spend to date, dry-run flag. Spend is `$0.00`; show it.

## Hard rules

- **This app never sends email and never spends money.** It records that a human did.
  No SMTP client, no email API, no payment anything.
- **Never invent a contact, a send, or a reply.** Empty renders as empty. The brand list is real
  data; the outreach pipeline is not yet, and the UI must not blur the two.
- Every number traces to `dashboard.json`. No computed marketing figures.
- Stage changes and contact records are the operator's own entries; do not derive them from
  agent activity.

## Design

Modern, dense, dark by default with a light mode. Built for someone scanning 102 rows, not a
marketing page — no hero sections, no illustrations, no gradients on everything. Readable at
a glance: the pipeline is the product. Keyboard navigation where it is cheap. Responsive enough
to work on a laptop screen; mobile is not a requirement.

Pick the stack. React or Svelte are both fine. Ship something that runs with one command and
document that command in the README.

## Done

- `npm run dev` (or equivalent) serves it; one command, documented
- All five screens work against real `dashboard.json`
- Stage changes and contact records persist across a restart
- Push a branch. Do not merge to main.
