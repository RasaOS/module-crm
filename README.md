# Rasa · Module · CRM

**Canonical name:** `rasa.module.crm`
**Repo / folder:** `module-crm`
**Kind:** `module` (canon Spec §6)
**Contract:** Element Contract v1.3.0
**Version:** 0.1.0 (initial shell)
**Status:** v0.1.0 shell — spine + spec + adapter seam + three ledger
templates. Skills deferred to the build phase.

## What this is

The **combined CRM** module of the RasaOS business-ops set: **contacts, leads,
AND current customers in one module**, all joined by the shared account handle
`@acct-<slug>`. It owns three records — the **Account** (the customer hub), the
**Contact** (a person), and the **Lead** (a sales opportunity) — and a live
link between them: when a lead is **won**, its account flips to `active`, i.e.
becomes a current customer.

**The deliberate divergence.** The split RasaOS business-ops set (`leads` /
`schedule` / `contracts` / `invoices` / `field-log`) each defers the account's
own record to the not-yet-built account hub primitive (canon task **SA-032**).
By the owner's explicit choice, `rasa.module.crm` does the opposite: it **owns
the account registry itself**, materializing the hub locally in
`crm/ACCOUNTS.md`. crm is the accounts source of truth — if a split module is
co-mounted, it joins to crm's `ACCOUNTS.md`. v0.1.0 is still a disciplined
shell.

## The records it owns

Three records, one spine (`@acct-<slug>`):

- **Account** — `handle` (`@acct-<slug>`), `name`, `status`
  (`prospect | active | churned`), `tier`, `owner`, `since`, `contacts`
  (`CON-NNN` list), `notes`. **`active` = a current customer.**
- **Contact** — `id` (`CON-NNN`), `account` (`@acct-<slug>`), `name`, `role`,
  `email`, `phone`, `primary`, `notes`.
- **Lead** — `id` (`LEAD-NNN`), `account`, `contact`, `source`, `stage`
  (`new → contacted → qualified → proposal → won | lost`), `value`, `owner`,
  `next_action`, `next_action_date`, `created`, `notes`.

**Won → active:** a won lead flips its account to `active`; `lost` is terminal
and never deleted. Full definition in `content/crm-rules.md`.

## Element- vs project-owned files

| Source | Installs to | Policy | Owner |
|---|---|---|---|
| `content/crm-rules.md` | `.claude/crm-rules.md` | file-replace | **Element** — the spine; refreshes on upgrade. |
| `seed/crm-gate.md.template` | `.claude/crm-gate.md` | skip-if-exists | **Project** — the seam (stages + qualification bar, source / status / churn / roles taxonomies). |
| `seed/crm/ACCOUNTS.md.template` | `crm/ACCOUNTS.md` | skip-if-exists | **Project** — the account/customer hub (current-customers registry). |
| `seed/crm/CONTACTS.md.template` | `crm/CONTACTS.md` | skip-if-exists | **Project** — the people ledger. |
| `seed/crm/LEADS.md.template` | `crm/LEADS.md` | skip-if-exists | **Project** — the pipeline board. |
| `seed/rasa.lock.json.template` | `.claude/rasa.lock.json` | init-only-with-sha | Connection-Contract lockfile, SHA-stamped at init. |

`content/README.md` + `content/BUILD_PLAN.md` are author-time docs (opt-in),
not installed into consumers.

## The account spine (owned here)

Every Contact and Lead references its customer as `@acct-<slug>` — the same
opaque, stable handle the whole business-ops set shares. Unlike the split set,
crm **materializes the account itself** in `crm/ACCOUNTS.md` rather than
deferring the account record to the account hub (canon task **SA-032 —
engagement-hub primitive**). crm is the accounts source of truth: a co-mounted
split module (`field-log`, `invoices`, `contracts`) joins to crm's
`ACCOUNTS.md` by the shared handle. When the hub lands, crm's local registry
refactors to the canonical hub with no change to the records that reference it.

## Skills deferred to the build phase

The `/account`, `/contact`, `/lead`, `/qualify`, and `/crm` skills are **not**
in v0.1.0. Per the RasaOS extract-after-proof precedent (`module.tasks`),
they're held until a real parent declares `rasa.module.crm` in its
`requires.elements[]`. It clears that gate by declaration, not anticipation.
See `content/BUILD_PLAN.md` (M-1..M-5) for their contracts.

## See also

- `~/rAI/rasa-os/elements/module-field-log/` — the shell precedent (spine +
  spec + seam + ledger, skills deferred) this module follows; crm diverges by
  **owning** the account registry field-log defers.
- Canon Spec §6 — the `module` kind definition; `ELEMENT_CONTRACT.md` §7 —
  install policies.
- `~/rAI/rasa-os/elements/REGISTRY.md` — register this Element here on first ship.
