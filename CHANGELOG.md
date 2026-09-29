# CHANGELOG — `rasa.module.crm`

Reverse-chronological. Each entry is a version bump.

---

## 0.2.0 — 2026-09-28 — the address book, accounts and the funnel, as records (records-family/1)

**Breaking.** The ledger shape changes from three markdown files
(`crm/ACCOUNTS.md`, `CONTACTS.md`, `LEADS.md`) to one file per record, and
the contact id changes from `CON-NNN` to `CARD-nnnn`. **No migration is
needed:** 0.1.0 was a local-only shell that was never pushed, and no project
has installed it (every `rasa.lock.json` and `rasa.json` on the workspace
volume and under the home directory was searched on 2026-09-28 — none
declares or pins this module).

Owner direction: *"we need modules for each of the following… notes,
calendar events, messages, contacts — as much structure and organization as
we can get."* Contacts were **folded into this module** rather than given a
module of their own: the Contact becomes the vCard 4.0 (RFC 6350) aligned
address book for **all** people and organizations — a contact no longer
needs an account — while the Account and the Lead are kept and re-stored to
the same standard. Built together with `rasa.module.notes` 0.2.0,
`rasa.module.schedule` 0.2.0 and the new `rasa.module.messages` 0.1.0 as one
family, to the `rasa.module.tasks` v1.0.0 standard.

### Family core 1.0.1

Ships `records.py` **1.0.1**, byte-identical in notes, schedule, crm and
messages. Two defects were found while the family was built, and fixed in
all four at once rather than worked around in one:

- a quoted flow-map value holding `,` `[` `]` `{` `}` (a street "Suite 5,
  Floor 2", a name "Doe, Jane") was written but could not be read back —
  found independently by the crm and messages builds;
- a file too broken to parse was also reported as deleted (F-17); it is now
  reported only for what is wrong with it.

Every write path now proves the rendered record reads back exactly as
written (`R.verify_roundtrip`) before it touches the disk. `bin/init` never
copies bytecode, and the release gate fails if any sits under `content/` or
`seed/`. Integration run 2026-09-29: all four family modules plus
`rasa.module.tasks` installed into one project, cross-linked records, every
validator clean, a hand-deleted contact caught by its referrers.

### Added

- **Contact cards** — `crm/contacts/CARD-nnnn-<slug>.md`: FN as the H1,
  structured `name`, `nickname`, `org`, `title`, labelled `email` / `phone`
  / `address` / `url` lists with at most one `pref` each, `handle`
  (IMPP), `birthday` / `anniversary` (including `--MM-DD`), `groups`,
  `accounts` (`{acct, role, primary}` — at most one primary per account),
  `related`, `tz`, `lang`, `photo`, `uid`. Archive/restore to
  `crm/contacts/_archive/`; `crm contact merge KEEP DROP` folds duplicates
  (DROP archived with `merged_into`, still resolvable).
- **Generic field editing** — `crm <record> set | unset | add | remove |
  pref ID FIELD …` with a shorthand item grammar (`work:jane@acme.example`,
  `mobile:+1 555 0100`, `signal:+15550100`, `acct-x:role:primary`,
  `k=v;k=v` for addresses), every item checked against the schema before
  writing.
- **Accounts** — `crm/accounts/acct-<slug>.md` (the stem is the id): status
  from `account_statuses`, `since`, tier, owner, the account's own contact
  details, tags. Status changes only through the tool and is checked against
  the history (C-15). `crm account show` joins the account's people, its
  leads by stage, and read-only counts of the events, threads and notes that
  name it elsewhere in the family.
- **Leads** — `crm/leads/<stage>/LEAD-nnnn-<slug>.md`, the directory is the
  stage. `advance`; **the qualification hard-stop** (config `qualification`,
  every criterion asserted with `--met`, `qualified_on` stamped); `win`
  (closes the lead **and** moves the account to the active status — two
  records, two history lines, one act; **a deal is never won unqualified** —
  an unqualified lead is qualified as it is won, behind the same hard-stop); `lose --reason`; `reopen`.
- **Views** — `crm pipeline` (count and value per stage, summed per
  currency), `crm birthdays --next N` (handles `--MM-DD` and 29 February),
  `crm groups`, list/find/show for every record.
- **vCard interop** — `vcard.py`: export vCard 4.0 (folded at 75 octets,
  escaped, CRLF; non-standard labels as `X-ABLabel` groups); import vCard 3.0
  and 4.0 (unfolding, unescaping, both TYPE syntaxes, QUOTED-PRINTABLE with
  CHARSET, `item1.` groups, 3.0 `TYPE=pref` and 4.0 `PREF=n`, embedded photos
  skipped and reported); dedupe by UID then exact email; `--update` folds in
  without overwriting.
- **Two programs** — `.claude/bin/crm` and `.claude/bin/check-crm`
  (F-01…F-27 family invariants + C-01…C-16; `--fix` appends reconcile lines
  for hand moves and hand status edits, and never invents a person or a
  date). The tool runs the validator's per-record law on every record before
  it writes it.
- **JSON Schemas** for the card, the account, the lead and the config,
  installed under `.claude/schemas/crm/`.
- **`crm/crm.config.yml`** (stages, won/lost/qualified stage names,
  qualification, sources, account statuses, active status, tiers, tags,
  contact roles, groups, labels, default currency, actors) and a reworked
  `.claude/crm-gate.md` seam — judgement only: what each qualification
  criterion means, stage entry/exit, active and churn, and the privacy rails
  for recording people.
- **Skills** `/contact`, `/account`, `/lead`.
- **Release gate** — `bin/check-manifest` runs the 14 records-family checks.
  Four ALLOWLIST rows let the owner-specified `crm contact merge` verb name
  itself in the files that carry it.
- **Tests** — `tests/test_records_core.py` (family core, identical in all
  four modules) and `tests/test_crm_cli.py`.

### Removed

- `seed/crm/{ACCOUNTS,CONTACTS,LEADS}.md.template` — replaced by per-record
  files.
- The `/sync`, `/promote` and `/whoami` skills and the
  `.claude/rasa-deployment.md` seed — on the `rasa.module.tasks` v1.0.0
  precedent: a mounted module must not claim skill names or identity files a
  parent owns.
- The citation of "SA-032 — engagement-hub primitive": no such canon task
  exists under that name (SA-032 is an unrelated task). The account-hub
  divergence is unchanged and is now described without a task number.
- The planned `/qualify` and `/crm` skills: qualifying is `crm lead advance
  --met` (inside `/lead`), and the read views are `/account` and `/lead`.

### Changed

- The skill-build gate ("hold until a real consumer declares the module")
  was lifted by the owner's direct request, not by a consumer appearing.
  The 1.0.0 bar — real projects running the shape unchanged — still stands.
- Permissions add `shell:exec` (the installed programs are run).

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
  (crm owns the account registry instead of deferring it [^1]), the adapter
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
  primitive [^1], crm — by the owner's explicit choice —
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

[^1]: As first written, this entry cited the unbuilt account-hub primitive as
"canon task SA-032". That was wrong — SA-032 is an unrelated canon task, and
no task by that name exists. The citation was removed in 0.2.0; the
divergence it described is unchanged.
