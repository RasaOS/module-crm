# CLAUDE.md — `rasa.module.crm`

> **Who you are (SA-025).** `rasa.module.crm` — the RasaOS module for CRM. Substrate: **RasaOS**; role: **module**. On install `bin/init` renders this into `.claude/rasa-identity.md`; `/whoami` composes the full identity with the project's deployment layer.


Per-repo working contract for Claude sessions opened inside this folder.
Extends `~/.claude/CLAUDE.md` and the workspace `~/rAI/rasa-os/CLAUDE.md`
(the `rasa.tenant.rasaos` tenant's contract); does not override them.

## What you are when you're in this folder

You are working on **`rasa.module.crm`** — a `module`-kind, toolkit-shaped
business-ops Element. It is the **combined CRM**: **contacts, leads, AND
current customers in one module**, all joined by the shared account handle
`@acct-<slug>`.

It owns **three records**:

- **Account** — the customer/company hub. "Current customers" are accounts
  with `status: active`.
- **Contact** — a person at an account (`CON-NNN`).
- **Lead** — a sales opportunity (`LEAD-NNN`), moving
  `new → contacted → qualified → proposal → won | lost`.

The **key lifecycle link**: when a lead reaches **won**, its account flips
`status → active` — a won lead becomes a current customer. `lost` is terminal
and never deleted (a lost lead is memory).

The portable spine is `content/crm-rules.md`; the per-business slice (pipeline
stages + qualification bar, lead-source taxonomy, customer-status/churn
taxonomy, contact-roles taxonomy) is the project-owned `.claude/crm-gate.md`
seam. The full specification and build plan are in `content/BUILD_PLAN.md`.

### The deliberate divergence — crm owns the account registry

The split RasaOS business-ops set (`leads` / `schedule` / `contracts` /
`invoices` / `field-log`) each **defers** the account's own record to the
unbuilt account hub primitive (canon task **SA-032**) — none seeds an accounts
registry. **`rasa.module.crm` deliberately does the opposite**, by the owner's
explicit choice: it **owns the account registry itself**, materializing the
hub locally in `crm/ACCOUNTS.md`. crm is the accounts **source of truth** — if
a split module is co-mounted, it joins to crm's `ACCOUNTS.md` by
`@acct-<slug>`. Do not seed a second, competing accounts registry.

### Skills are deferred (extract-after-proof)

v0.1.0 is a **shell**: spine + spec + seam + three ledger templates, **no
skills**. The `/account`, `/contact`, `/lead`, `/qualify`, `/crm` skills are
the build phase, held until a real parent declares this module in its
`requires.elements[]` (the `module.tasks` precedent). It clears the gate by
declaration, not anticipation. Don't author the skills ahead of that.

## Status

**v0.1.0 — initial shell.** Spine (`content/crm-rules.md`) + spec
(`content/BUILD_PLAN.md`) + adapter seam (`seed/crm-gate.md.template`) + three
live-ledger templates (`seed/crm/ACCOUNTS.md.template`,
`seed/crm/CONTACTS.md.template`, `seed/crm/LEADS.md.template`). Skills
deferred. See CHANGELOG.md.

## Source of truth

- **`~/rAI/rasa-os/canon/`** — authoritative for every architectural
  decision (Spec §6 defines the `module` kind). Canon wins.
- **`elements/module-field-log/`** — the shell precedent this Element forked
  from. Shape questions go there, not here (but note crm diverges by **owning**
  the account registry that field-log defers).
- **`rasa.json`** — this Element's formal declaration.
- **`~/rAI/rasa-os/elements/REGISTRY.md`** — the live workspace snapshot.

## Don'ts

- **You are NOT the template.** If this contract ever describes
  `module-field-log` (or any other Element), the template-CLAUDE.md
  drift class is back — flag it.
- **Don't author content ahead of the authoring phase** without the user
  driving.
- **Don't `bin/init` this Element into itself.** `content/` is the
  source (workspace rule).
- **Don't push to GitHub from the Cowork sandbox.** Local commit + tag;
  the user pushes (workspace rule).

## How a version bump works

Each bump: edit `VERSION` + `rasa.json#version`, write a CHANGELOG entry,
run `bin/check-manifest`, commit + tag `v<version>`. Update
`~/rAI/rasa-os/elements/REGISTRY.md` +
`~/rAI/rasa-os/elements/CHANGELOG.md` (track #2).
