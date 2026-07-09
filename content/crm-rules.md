# CRM Rules

The portable CRM spine that `rasa.module.crm` installs at
`.claude/crm-rules.md`. It covers the three records this module owns —
**Account**, **Contact**, and **Lead** — their canonical field sets, the
pipeline lifecycle, the shared account-handle spine that joins all three (and
which this module deliberately **owns locally**), the boundary against the
split business-ops modules, and the ledger conventions. **Read this file when
adding a customer account, filing a contact, capturing or advancing a lead,
qualifying an opportunity, or asking "who are our current customers, and
what's in the pipeline for this account?"**

This file is **Element-owned** — it refreshes on upgrade. It deliberately
does **not** decide the things that vary per business:

- The business's **pipeline stages** + entry/exit criteria and its
  **qualification bar** (what makes a lead "qualified"); its **lead-source
  taxonomy**; its **customer-status taxonomy** (what "active customer" means
  and what counts as **churn**); and its **contact-roles taxonomy**.

Those live in the project-owned **`.claude/crm-gate.md`** (the crm analogue
of the task module's done-gate and the release module's release-gate). This
file references the seam; it hardcodes none of it. The `/qualify` step and
any stage advance **read the gate** for the business's own definitions —
inventing a sales process for a business we've never seen is the one
inference this module refuses to make.

## What this module owns — three records on one spine

This module owns **three records**, all joined by the shared account handle
`@acct-<slug>`:

1. **Account** — the customer/company record. The **hub**. "Current
   customers" are simply the accounts with `status: active`.
2. **Contact** — a person at an account. `CON-NNN`.
3. **Lead** — a sales opportunity against an account. `LEAD-NNN`.

Contacts and leads both point at an Account by `@acct-<slug>`; contacts and
leads point at each other by `CON-NNN`. The Account is the center everything
hangs off — it is what makes this a *combined* CRM (contacts, leads, and
current customers in one place) rather than three disconnected ledgers.

### It owns the account registry (deliberate divergence)

> **This is the design choice that sets `rasa.module.crm` apart.** The split
> RasaOS business-ops modules (`leads` / `schedule` / `contracts` /
> `invoices` / `field-log`) each treat `@acct-<slug>` as an opaque join key
> and **defer the account's own record** to the not-yet-built account hub
> primitive (canon task **SA-032 — engagement-hub primitive**) — none of them
> seeds an accounts registry. `rasa.module.crm` **does the opposite, by the
> owner's explicit choice**: it **owns the account registry itself**,
> materializing the account hub locally in `crm/ACCOUNTS.md`. If any split
> business-ops module is co-mounted alongside crm, **it joins to crm's
> `ACCOUNTS.md` by `@acct-<slug>`** — crm becomes the accounts **source of
> truth** for the deployment, and the split modules resolve display names and
> customer status against it instead of deferring to SA-032. Combined-CRM
> deployments and split-module deployments are two supported shapes; crm is
> the combined one.

## The three records — canonical field sets

One record = one markdown entry in the record's live ledger. The canonical
fields every consuming business carries at minimum:

### Account — `crm/ACCOUNTS.md` (the hub)

| Field | Type | What it is |
|---|---|---|
| `handle` | `@acct-<slug>` | The account id **and** the shared join spine. Required; the identity of the account. |
| `name` | text | The company / customer display name. |
| `status` | `prospect \| active \| churned` | Where the account stands. The real taxonomy lives in the gate. **`active` = a current customer.** |
| `tier` | text | The account's tier / segment (the business's own scale — lives in the gate). |
| `owner` | text | The person accountable for the relationship. |
| `since` | absolute date | When the account became what it is (e.g. when it went `active`). Never relative. |
| `contacts` | list of `CON-NNN` | The people at this account (join to `crm/CONTACTS.md`). |
| `notes` | prose | Running context on the relationship. |

### Contact — `crm/CONTACTS.md` (the people)

| Field | Type | What it is |
|---|---|---|
| `id` | `CON-NNN` | Monotonic contact id; never reused. |
| `account` | `@acct-<slug>` | The account this person belongs to. Required — a contact with no account is an orphan. |
| `name` | text | The person's name. |
| `role` | text | Their role / title. The **contact-roles taxonomy** (decision-maker, champion, technical, billing, …) lives in the gate. |
| `email` | text | Email. |
| `phone` | text | Phone. |
| `primary` | bool | Whether this is the primary contact for the account. At most one primary per account. |
| `notes` | prose | Anything else worth keeping on the person. |

### Lead — `crm/LEADS.md` (the pipeline)

| Field | Type | What it is |
|---|---|---|
| `id` | `LEAD-NNN` | Monotonic lead id; never reused. |
| `account` | `@acct-<slug>` | The account the opportunity is against. Required. |
| `contact` | `CON-NNN` or name | The person you're working the deal with. |
| `source` | from the gate | Where the lead came from — from the business's **source taxonomy** in the gate. |
| `stage` | pipeline stage | Current stage (see lifecycle). The business's real stage list lives in the gate. |
| `value` | number + currency | Estimated deal value. An estimate to size the pipeline, not booked revenue. |
| `owner` | text | The person accountable for advancing the lead. |
| `next_action` | one line | The single next thing that moves the lead forward. |
| `next_action_date` | absolute date | When that next action is due. |
| `created` | absolute date | When the lead was captured. |
| `notes` | prose | Running context — call notes, objections, history. |

Rules for the records:

- **`account` is the spine.** Every contact and every lead carries a
  `@acct-<slug>`, and every account owns that handle. A contact or lead with
  no account is an orphan — it belongs to an account or it doesn't belong here.
- **Ids monotonic, never reused.** `CON-NNN`, `LEAD-NNN`. A dead lead keeps
  its number; a new record gets the next one.
- **Dates absolute** (`2026-07-05`), never relative ("next week").
- **`value` is an estimate.** It sizes and ranks the pipeline; the booked
  figure lands in a contract (soft hand-off), not here.
- **`status: active` is the definition of a current customer.** The
  current-customers list is exactly `ACCOUNTS.md` filtered to `status: active`.

## The pipeline lifecycle — and the won → active link

A lead moves through a small, ordered set of stages. State is a property of
the lead record, not a separate ledger. The **default** lifecycle this module
ships is:

```
new ──▶ contacted ──▶ qualified ──▶ proposal ──▶ won
                                             └──▶ lost
```

| Stage | Meaning |
|---|---|
| **new** | Captured, not yet worked. The raw top of funnel. |
| **contacted** | First outreach made; a conversation has started. |
| **qualified** | Confirmed a real fit + budget + need — the **gate** defines exactly what "qualified" requires. |
| **proposal** | A proposal / quote is out; terms under negotiation. |
| **won** | Closed-won. **The account flips `status → active`** — a won lead becomes a current customer. |
| **lost** | Closed-lost. Terminal; record why in `notes`. **Never deleted** — a lost lead is institutional memory. |

**The key lifecycle link: won → active.** When a lead reaches `won`, its
Account's `status` flips to `active` in `crm/ACCOUNTS.md` (set `since` to the
win date). A won lead *is* the moment a prospect becomes a current customer —
that transition is the join between the pipeline and the hub, and it is the
one cross-record write this module makes. `lost` is terminal and writes
nothing to the account; the lead stays in the ledger as memory.

**The business's real stages live in the gate.** Some businesses run this
five-stage funnel; some collapse `contacted`/`qualified` or add a `nurture`
holding stage. `.claude/crm-gate.md` is the authoritative stage list + the
entry/exit criteria for each. This file's lifecycle is the default the gate
overrides — never advance a lead against a stage the business's gate doesn't
declare.

## Customer / Account spine — owned here, not deferred

Every record this module owns references its customer by a stable **account
handle**: `@acct-<slug>` (for example `@acct-acme`). The handle is an opaque,
stable join key **and**, in this module, an entry in a registry crm actually
owns.

This is where crm **diverges** from its split siblings. The sibling
business-ops modules never seed an accounts registry — they hold `@acct-<slug>`
as a bare join key and defer the account's real record to the canonical hub
(canon **SA-032**). `rasa.module.crm` **materializes that hub locally**: the
account's name, status, tier, owner, and contacts live in `crm/ACCOUNTS.md`,
which crm owns and maintains. So within a crm deployment:

- The handle both **joins** records and **resolves** to a real account entry —
  no deferral, no missing hub.
- If a split business-ops module (`field-log`, `invoices`, …) is co-mounted,
  **it joins to crm's `ACCOUNTS.md`** by the same `@acct-<slug>`. crm is the
  accounts source of truth; the split module reads display names and status
  from it rather than deferring to SA-032.
- When SA-032 eventually lands as a first-class primitive, crm's local
  registry refactors to the canonical hub with **no change to the records
  that reference it** — the handle is unchanged.

Do not run two competing accounts registries in one deployment. If crm is
mounted, crm's `ACCOUNTS.md` is the registry.

## The boundary against adjacent modules — soft references

crm stands alone. When siblings are mounted it hands off by the shared
account handle — but every one of these is **soft**: present-if-mounted,
graceful-if-absent. **None is a `requires.elements[]` dependency.**

- **`rasa.module.field-log`** — a field visit joins to a crm Account by
  `@acct-<slug>`; a **won** lead can trigger a kickoff visit. crm is the
  accounts source of truth the field log resolves its account against; crm
  does not schedule or log the visit.
- **`rasa.module.contracts`** — a **won** lead hands off to a contract (the
  won deal becomes a signed agreement). crm records the win and flips the
  account active; it does not write the contract.
- **`rasa.module.invoices`** — an **active** customer is billed. crm owns the
  "who is a current customer" answer; invoices owns the money.
- **`rasa.module.tasks`** — a lead's `next_action` can become an assignable
  `TASK-NNN`; the `next_action` field here stays the lightweight open-loop
  view.

If a sibling isn't mounted, the hand-off simply doesn't happen — the record
still reaches its terminal state cleanly. **Never harden a hand-off into a
hard dependency.**

## The adapter seam — `.claude/crm-gate.md`

The one thing this module cannot know for a business it's never seen. The
gate holds the four things that genuinely vary per CRM:

1. **Pipeline stages + the qualification bar** — the exact ordered stage list
   for THIS business, with the **entry/exit criteria** for each, and the
   concrete bar a lead must clear to be marked `qualified` (budget confirmed?
   decision-maker identified? a named need?). `/qualify` reads this and
   **will not invent a qualification bar**.
2. **Lead-source taxonomy** — the business's allowed `source` values
   (e.g. `referral | inbound | event | outbound`).
3. **Customer-status taxonomy** — what `prospect / active / churned` mean for
   this business: specifically **what makes an account an "active customer"**
   and **what counts as churn** (the definition that moves an account
   `active → churned`).
4. **Contact-roles taxonomy** — the business's `role` values for contacts
   (e.g. `decision-maker | champion | technical | billing | user`).

Ships with honest defaults + commented examples; the business fills it in.
This file (the spine) references the gate; it hardcodes none of the four.

## Ledger conventions

- **Three live ledgers**, all git-versioned, project-owned (seeded
  skip-if-exists):
  - `crm/ACCOUNTS.md` — the account/customer hub, **grouped by status**
    (active customers first). The current-customers registry.
  - `crm/CONTACTS.md` — the people, **grouped by account**.
  - `crm/LEADS.md` — the pipeline board, **grouped by stage**; won/lost stay
    in the ledger for history.
- Markdown, human-first. Frontmatter/tables are fine, but each ledger must
  read cleanly top-to-bottom to a person — the retrievability is a human
  reading the pipeline as a funnel or the customer list in order, not a query.
- **Cross-link by handle/id.** Accounts list their `CON-NNN` contacts; leads
  and contacts carry their `@acct-<slug>`. The three ledgers are one graph
  joined on those keys.
- **Never delete a lead.** A lost lead is data — why it was lost is often the
  most useful thing in the ledger. Move it to terminal, don't remove it. The
  same holds for a churned account: flip `status → churned`, don't delete it.
- Ids monotonic (`CON-NNN`, `LEAD-NNN`), dates absolute.

## Skills (deferred — the build phase)

v0.1.0 is a shell: the spine (this file), the specification
(`content/BUILD_PLAN.md`), the seam template, and the three ledger templates.
The **skills are not authored yet** — they are held per the RasaOS
extract-after-proof precedent (`rasa.module.tasks`, `rasa.module.notes`),
built once a real consumer declares this module in `requires.elements[]`. The
intended skills, specified as milestones in `BUILD_PLAN.md`:

- **`/account`** — add/update a customer account; flip `status`
  (`prospect` / `active` / `churned`); assign `@acct-<slug>`.
- **`/contact`** — add/update a person; assign `CON-NNN`; attach to an account.
- **`/lead`** — capture an opportunity + advance it through the stages; assign
  `LEAD-NNN`.
- **`/qualify`** — advance a lead through qualification against the gate's
  bar; **hard-stops** if the bar is unfilled.
- **`/crm`** — read/render: the pipeline board + the current-customers list +
  an account's full 360 (its contacts + open leads + status). Read-only.

Until then, the three ledgers are maintained by hand against the discipline in
this file. Do not stub the skills — the shell is the deliverable.
