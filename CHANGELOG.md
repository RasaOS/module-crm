# CHANGELOG — `rasa.module.crm`

Reverse-chronological. Each entry is a version bump.

---

## 0.1.0 — INITIAL SHELL (2026-07-09)

Initial shell of the **combined CRM** module — contacts, leads, AND current
customers in one module, all joined by the shared account handle
`@acct-<slug>`. Ships the spine + the specification + the adapter seam + three
live-ledger templates; skills deferred per extract-after-proof.

### What ships

- **The spine** — `content/crm-rules.md` (installs to `.claude/crm-rules.md`,
  file-replace): the three records it owns (**Account** / **Contact** /
  **Lead**) and their canonical field sets, the
  `new → contacted → qualified → proposal → won | lost` pipeline lifecycle and
  the **won → account-active** link, the account spine crm **owns** locally,
  the boundary against the split business-ops modules, and the ledger
  conventions.
- **The specification** — `content/BUILD_PLAN.md`: the Account/Contact/Lead
  entity model, the lifecycle + the won→active link, the deliberate divergence
  (crm owns the account registry instead of deferring to SA-032), the adapter
  seam, the deferred `/account` `/contact` `/lead` `/qualify` `/crm` skills
  (M-1..M-5), the soft cross-refs, and an honest scope section.
- **The adapter seam** — `seed/crm-gate.md.template` (installs to
  `.claude/crm-gate.md`, skip-if-exists): the four per-business things —
  pipeline stages + qualification bar, lead-source taxonomy,
  customer-status/churn taxonomy, contact-roles taxonomy. Placeholder-free,
  honest defaults + commented examples.
- **The three live ledgers** (all skip-if-exists) —
  `seed/crm/ACCOUNTS.md.template` → `crm/ACCOUNTS.md` (the customer hub /
  current-customers registry, grouped by status),
  `seed/crm/CONTACTS.md.template` → `crm/CONTACTS.md` (the people, grouped by
  account), `seed/crm/LEADS.md.template` → `crm/LEADS.md` (the pipeline board,
  grouped by stage). Each carries a couple of cross-linked example entries
  (incl. one won lead that flipped its account active) with a delete-the-
  examples note.
- `content/README.md` — author-time doc describing what installs where.

### Notes

- **The combined one (deliberate divergence).** Where the split RasaOS
  business-ops set (`leads` / `schedule` / `contracts` / `invoices` /
  `field-log`) each defers the account record to the unbuilt account hub
  primitive (canon task **SA-032**), crm — by the owner's explicit choice —
  **owns the account registry itself** in `crm/ACCOUNTS.md` and is the accounts
  source of truth. A co-mounted split module joins to crm's `ACCOUNTS.md` by
  `@acct-<slug>`.
- **Won → active is the load-bearing link.** A lead reaching `won` flips its
  account to `active` (a current customer); `lost` is terminal and never
  deleted (a lost lead is memory).
- **Skills deferred.** `/account`, `/contact`, `/lead`, `/qualify`, `/crm` are
  the build phase (BUILD_PLAN M-1..M-5), held until a real parent declares the
  module in `requires.elements[]` (the `module.tasks` extract-after-proof
  precedent).
- **Account spine threaded.** Every Contact and Lead carries `@acct-<slug>`;
  crm materializes the account itself, so the handle both joins and resolves.
- **Soft references only.** `field-log` (visit / kickoff), `contracts` (won →
  contract), `invoices` (active customer → billed), `tasks` (next_action →
  TASK-NNN) — all present-if-mounted, never `requires.elements[]`.
- Forked from the `rasa.module.field-log` v0.1.3 module shell; generic
  `/sync` + `/promote` + `/whoami` and the SA-025 identity layer carried over.
- `bin/check-manifest` GREEN.

### Deferred to next version

- **v0.2.0** — author the `/account`, `/contact`, `/lead`, `/qualify`, `/crm`
  skills, once a real consumer declares the module. `bin/init` smoke-tested
  into it.
- Create `RasaOS/module-crm` on GitHub; first commit + tag + push; register in
  `elements/REGISTRY.md` + `elements/CHANGELOG.md`.
