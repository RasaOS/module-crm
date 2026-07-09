# `rasa.module.crm` — content

What this module ships and where it installs. This file is author-time
documentation (not installed into consumer projects).

## The one-liner

The **combined CRM** module: **contacts, leads, AND current customers in one
module**, all joined by the shared account handle `@acct-<slug>`. Three
records — **Account** (the customer hub), **Contact** (a person), **Lead** (an
opportunity) — with a live link: when a lead is **won**, its account flips to
`active` (a current customer). Unlike the split business-ops set, crm **owns
the account registry itself** rather than deferring it.

## What installs where

| Source | Installs to | Policy | What it is |
|---|---|---|---|
| `content/crm-rules.md` | `.claude/crm-rules.md` | file-replace | The spine — the Account/Contact/Lead records, the pipeline lifecycle + the won → active link, the account spine crm owns, the sibling boundary. Element-owned; refreshed on upgrade. |
| `seed/crm-gate.md.template` | `.claude/crm-gate.md` | skip-if-exists | **The seam** — the business's pipeline stages + qualification bar, lead-source taxonomy, customer-status/churn taxonomy, contact-roles taxonomy. Project-owned; the business fills it. |
| `seed/crm/ACCOUNTS.md.template` | `crm/ACCOUNTS.md` | skip-if-exists | The account/customer hub — the current-customers registry. Project-owned. |
| `seed/crm/CONTACTS.md.template` | `crm/CONTACTS.md` | skip-if-exists | The people ledger. Project-owned. |
| `seed/crm/LEADS.md.template` | `crm/LEADS.md` | skip-if-exists | The pipeline board. Project-owned. |
| `seed/rasa.lock.json.template` | `.claude/rasa.lock.json` | init-only-with-sha | Connection-Contract lockfile, SHA-stamped at init. |

## What is NOT here yet

The `/account`, `/contact`, `/lead`, `/qualify`, `/crm` **skills** — they are
the build phase. See [`BUILD_PLAN.md`](BUILD_PLAN.md) for their contracts and
the extract-after-proof gate. v0.1.0 is deliberately a shell: spine + spec +
seam + the three ledger templates.

## The account spine (owned here)

Every Contact and Lead references its account as `@acct-<slug>` — and, unlike
the split business-ops set, this module **materializes the account itself** in
`crm/ACCOUNTS.md` rather than deferring the account record to the unbuilt hub
primitive (canon **SA-032**). crm is the accounts source of truth: if a split
module (`field-log`, `invoices`, `contracts`) is co-mounted, it joins to crm's
`ACCOUNTS.md` by the shared handle. "Current customers" = accounts with
`status: active`; a won lead is what flips an account there.

## The shape

Toolkit module, `requires.parent_kind: [domain, tenant]`. Pure Element-layer
convention — no kernel engine. Cross-refs to `field-log`, `contracts`,
`invoices`, and `tasks` are all soft (present-if-mounted).

## See also

- [`BUILD_PLAN.md`](BUILD_PLAN.md) — the full spec + build plan.
- `content/crm-rules.md` — the installed spine.
- `elements/module-field-log/` — the shell precedent (spine + spec + seam +
  ledger, skills deferred) this module follows; crm diverges from it by
  **owning** the account registry the split set defers.
- Canon `ELEMENT_CONTRACT.md` §7 — install policies; Spec §6 — the
  `module` kind.
