# AI UGC System

A multi-agent pipeline that finds DTC skincare brands worth pitching, analyses what their
category actually advertises, and produces ad creative for them.

**Business model:** creative-as-a-service. We deliver scripts and video. Clients post it —
that keeps platform risk with whoever owns the account. See `docs/DESIGN.md` §1.

## Roles

| Role | Owns | Does |
|------|------|------|
| Strategy | — | Decides scope, reviews findings, resolves blocks. Does not build. |
| Writer | Agents 0, 3 | Brand intake, scriptwriting |
| Miner | Agents 1, 2 | Ad mining, angle taxonomy |
| Producer | Agents 4, 5 | Render queue, quality gate. Only role that spends money. |
| Outreach | Agent 7 | Drafts personalised outreach. Never sends. |

Coordination protocol in `ROLES.md`. Shared artifacts in `shared/data/`. Status log in
`shared/STATUS.md`.

## The one thing to read first

`docs/DESIGN.md` §4. The original product thesis — "we'll tell brands what angles nobody in
their category is using" — was tested and **withdrawn**. 7 of 9 absence claims were falsified
when probed against the live ad index; the surviving two failed the natural-owner test.

The corpus is **reliable for presence, unreliable for absence.** What replaced the thesis:
durability (which openings survive, and how long), positional divides, and what a client
already owns and under-runs. Those are confirmable and improve with more data.

## Current state

- 102 skincare brands ranked; 25 researched in depth
- 139 competitor ad openings analysed across 12 advertisers
- 9 cleared scripts + 1 pitch document for Frøya Organics
- Known gap: corpus is challenger-only by construction and reads incumbent-held positions as
  empty. Fix (incumbent seed list) specced in `docs/DESIGN.md` §4, not yet built.
