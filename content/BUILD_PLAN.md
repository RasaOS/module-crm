# `rasa.module.crm` — Specification & Build Plan

**Status:** v0.1.0 = spine + spec + seam + three ledger templates. The skills
are the build phase (M-1..M-5 below) — specified here, not implemented, gated
per extract-after-proof.

This is the author-time specification. The installed spine is
`content/crm-rules.md`; this file is the design record behind it.

---

## Why this module exists (and why it's the combined one)

The RasaOS business-ops set is normally **split**: `leads`, `schedule`,
`contracts`, `invoices`, `field-log` — five modules, each owning one record,
all sharing the `@acct-<slug>` account handle, and each **deferring the
account's own record** to the not-yet-built account hub primitive (canon task
**SA-032 — engagement-hub primitive**). None of the split modules seeds an
accounts registry; the hub is the missing center they all point at.

`rasa.module.crm` is a **deliberate divergence** from that split set, by the
owner's explicit choice. It is the **combined CRM**: contacts, leads, **and**
current customers in ONE module. Its defining decision is that it **does not
defer the account** — it **owns the account registry itself**, materializing
the hub locally in `crm/ACCOUNTS.md`. Where the split modules wait for SA-032,
crm ships the accounts center now and becomes the source of truth for the
deployment: if a split module is co-mounted, it joins to crm's `ACCOUNTS.md`.

That is the whole thesis. A combined-CRM deployment and a split-module
deployment are two supported shapes; crm is the combined one, and the account
registry is the thing it owns that the split set doesn't.

## Non-goals (hard boundaries)

- **Not the contract.** A **won** lead *hands off* to `rasa.module.contracts`;
  crm records the win and flips the account `active`, but never writes the
  signed agreement or the booked figure.
- **Not the invoice.** *Billing* an active customer is `rasa.module.invoices`.
  crm answers "who is a current customer"; invoices owns the money.
- **Not the field log.** A **won** lead can trigger a kickoff *visit*
  (`rasa.module.field-log`); crm doesn't log the visit — it is the accounts
  source of truth the visit resolves against.
- **Not a marketing-automation firehose.** Human-authored records — an account,
  a person, an opportunity — not an auto-logged stream of every email open.

---

## Entity model

Three project-owned live ledgers + one project-owned seam. The records are
**Account**, **Contact**, and **Lead**, joined by `@acct-<slug>` (and by
`CON-NNN` between contacts and leads).

### `crm/ACCOUNTS.md` (the hub) — the current-customers registry
One entry per account. **crm owns this** (the divergence). Grouped by status,
active customers first.

| Field | Type | Notes |
|---|---|---|
| `handle` | `@acct-<slug>` | **The id + shared join spine.** Required. |
| `name` | text | Company / customer display name. |
| `status` | `prospect \| active \| churned` | **`active` = a current customer.** Real taxonomy in the gate. |
| `tier` | text | Account tier / segment (business's scale — gate). |
| `owner` | text | Relationship owner. |
| `since` | absolute date | When it became what it is (e.g. went active). |
| `contacts` | list of `CON-NNN` | The people at this account. |
| `notes` | prose | Relationship context. |

### `crm/CONTACTS.md` (the people)
One entry per person at an account. Grouped by account.

| Field | Type | Notes |
|---|---|---|
| `id` | `CON-NNN` | Monotonic; never reused. |
| `account` | `@acct-<slug>` | **Required.** The account this person belongs to. |
| `name` | text | The person's name. |
| `role` | text | Role/title (roles taxonomy in the gate). |
| `email` | text | Email. |
| `phone` | text | Phone. |
| `primary` | bool | Primary contact for the account (≤ 1 per account). |
| `notes` | prose | Anything else. |

### `crm/LEADS.md` (the pipeline)
One entry per opportunity. Grouped by stage; won/lost stay in the ledger.

| Field | Type | Notes |
|---|---|---|
| `id` | `LEAD-NNN` | Monotonic; never reused. |
| `account` | `@acct-<slug>` | **Required.** The account the opportunity is against. |
| `contact` | `CON-NNN` / name | The person you're working it with. |
| `source` | gate taxonomy | Where the lead came from. |
| `stage` | pipeline stage | Current stage (gate defines the real list). |
| `value` | number + currency | Estimate to size the pipeline; not booked revenue. |
| `owner` | text | Accountable for advancing it. |
| `next_action` | one line | The single next step. |
| `next_action_date` | absolute date | When it's due. |
| `created` | absolute date | When captured. |
| `notes` | prose | Call notes, objections, history. |

Rules: `account` required on every record; ids monotonic; dates absolute;
never delete a lead (lost is memory) or an account (churned is history); at
most one primary contact per account.

### `.claude/crm-gate.md` (the seam) — the per-business slice
See "The adapter seam" below.

---

## The states / lifecycle — and the won → active link

The **Lead** carries the lifecycle:
**new → contacted → qualified → proposal → won | lost**, with `won`/`lost`
terminal (both stay in the ledger).

- **new** — captured, not worked.
- **contacted** — first outreach; conversation started.
- **qualified** — clears the gate's qualification bar.
- **proposal** — a proposal/quote is out; negotiating.
- **won** — closed-won. **The account flips `status → active`** (a won lead is
  a new current customer); set the account's `since` to the win date. This is
  the one cross-record write the module makes — the join between the pipeline
  and the hub.
- **lost** — closed-lost; record why. Writes nothing to the account; stays in
  the ledger as memory.

The **Account** carries its own status lifecycle:
**prospect → active → churned** (never deleted; churn flips status). What
"active" and "churned" mean is defined in the gate.

---

## The adapter seam — `.claude/crm-gate.md`

The crux of the design, mirroring `module.tasks`' done-gate. It holds the four
things that genuinely vary per business:

1. **Pipeline stages + qualification bar** — the ordered stage list for THIS
   business, the entry/exit criteria per stage, and the concrete bar a lead
   must clear to be `qualified`. `/qualify` reads it and **hard-stops** if the
   bar is unfilled.
2. **Lead-source taxonomy** — the allowed `source` values.
3. **Customer-status taxonomy** — what `prospect / active / churned` mean:
   what makes an account an "active customer" and what counts as **churn**.
4. **Contact-roles taxonomy** — the allowed `role` values for contacts.

Why a seam and not fixed logic: a self-serve SaaS funnel and a services
pipeline share the *records*, not the *stages* or the *qualification bar*. The
horizontal core is the three records + the won→active discipline; the vertical
part is the business's own definitions. `/qualify` reads the gate so it never
invents a sales process — the one inference the module refuses to make.

---

## Skills (the build phase — M-1..M-5) — DEFERRED, not implemented here

Five skills, MVP-scoped. Each is a thin driver over the ledgers + gate; the
discipline lives in `crm-rules.md`, not duplicated per skill. **None are
implemented in v0.1.0** — they are listed as the build plan.

### M-1 — `/account`
- **`/account`** — add or update a customer account in `crm/ACCOUNTS.md`.
  Assigns `@acct-<slug>` on create; sets/updates `name`, `tier`, `owner`,
  `contacts`; **flips `status`** (`prospect` / `active` / `churned`) per the
  gate's customer-status taxonomy, stamping `since` on a status change.

### M-2 — `/contact`
- **`/contact`** — add or update a person in `crm/CONTACTS.md`. Assigns the
  next `CON-NNN`, attaches the contact to an account (`@acct-<slug>`, required),
  sets `role` (from the gate's roles taxonomy), `email`, `phone`, `primary?`,
  and appends the id to the account's `contacts` list.

### M-3 — `/lead`
- **`/lead`** — capture an opportunity or advance an existing one through the
  stages in `crm/LEADS.md`. Assigns the next `LEAD-NNN`; collects `account`
  (required), `contact`, `source`, `value`, `owner`, `next_action` +
  `next_action_date`. On advance to **won**, prompts to flip the account
  `active` (the won→active link); on **lost**, records why and keeps it.

### M-4 — `/qualify`
- **`/qualify LEAD-NNN`** — advance a lead through qualification. Reads
  `.claude/crm-gate.md` for the qualification bar, walks its criteria, and
  advances the lead to `qualified` (or records why it didn't clear).
  **Hard-stops with a clear message if the gate has no qualification bar** —
  won't invent one.

### M-5 — `/crm`
- **`/crm [account @acct-<slug>]`** — read/render. Default: the **pipeline
  board** (leads by stage) + the **current-customers list** (accounts with
  `status: active`). Filtered by account, it's that account's **full 360** —
  its contacts + open leads + status + relationship notes. Read-only.

**Style/quality bar:** match `module.field-log` / `module.leads` SKILL.md
files — a crisp operation list, honest hard-stop behavior, no invented
plumbing. Fan-out plan when the gate opens: author `/qualify` as the reference
skill (it's the gate-reading, hard-stopping one), then `/account` `/contact`
`/lead` in parallel against it, and `/crm` last as the read surface; gate each
independently.

---

## Soft cross-references

All soft — present-if-mounted, graceful-if-absent, never `requires.elements[]`.
crm is the accounts source of truth all of these resolve against:

- **`rasa.module.field-log`** — a field visit joins to a crm Account by
  `@acct-<slug>`; a **won** lead can trigger a kickoff visit.
- **`rasa.module.contracts`** — a **won** lead hands off to a contract.
- **`rasa.module.invoices`** — an **active** customer is billed.
- **`rasa.module.tasks`** — a lead's `next_action` can become a `TASK-NNN`.

---

## HONEST SCOPE / deferred

- **v0.1.0 (this) ships a SHELL.** The spine (`crm-rules.md`), the spec (this
  file), the seam template, and the three ledger templates
  (`ACCOUNTS`/`CONTACTS`/`LEADS`). **No skills.** The three records, the
  pipeline lifecycle, and the won→active link are specified; the `/account`,
  `/contact`, `/lead`, `/qualify`, `/crm` drivers are *not written*.
- **Skills are gated per extract-after-proof.** The discipline is: hold the
  skill build until a real parent (a `domain` or `tenant`) declares
  `rasa.module.crm` in its `requires.elements[]`. It clears the gate by
  declaration, not anticipation.
- **crm OWNS the account registry (the divergence).** Unlike the split set,
  crm does not defer the account to SA-032 — it materializes it in
  `crm/ACCOUNTS.md`. When SA-032 lands as a first-class primitive, crm's local
  registry refactors to the canonical hub with **no change to the records that
  reference it** by `@acct-<slug>`.
- **Stages, qualification bar, source / status / churn / roles taxonomies are
  all in the seam**, not the spine. A business must fill `.claude/crm-gate.md`
  before `/qualify` can run against a real bar.

---

## Version plan

- **v0.1.0 (this)** — spine + spec + seam template + three ledger templates.
  No skills.
- **v0.2.0** — M-1..M-5 skills authored, once a real consumer declares the
  module. `bin/init` smoke-tested into that consumer.
- **v1.0.0** — the seam format + the three ledger shapes + the record fields
  locked after the loop has run through the module (not just by hand) in a
  real CRM deployment.
