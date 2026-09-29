# CRM rules — `rasa.module.crm` 0.2.0

The law for everything under `crm/`: the address book (every person and
organization you deal with, as vCard-aligned contact cards), the accounts
(the customers — the hub everything else hangs off) and the sales funnel
(leads moving through stages to won or lost). **Read this file before adding
a contact, attaching a person to an account, capturing or moving a lead,
qualifying one, importing an address book, or answering "who are our
customers, and what is in the pipeline?"**

This file is **Element-owned** — it is replaced on upgrade. It deliberately
does not decide the things that vary from business to business:

| seam | owner | holds |
|---|---|---|
| `.claude/crm-gate.md` | the project | what "qualified" means, each stage's entry and exit, what "active customer" and churn mean, what may be recorded about a person (judgement) |
| `crm/crm.config.yml` | the project | the stages, the qualification criteria by name, sources, account statuses, roles, groups, labels, currency, actors (checked) |

`crm lead advance` into the qualified stage **hard-stops** until
`qualification` is declared, and then requires every declared criterion to
be asserted with `--met`: guessing what "qualified" means for a business is
the one inference this module refuses to make.

Two programs, installed at `.claude/bin/`:

- **`crm <record> <verb>`** — the only sanctioned way to change the ledger.
- **`check-crm [--fix]`** — the enforcement. Run it before you call
  anything finished.

<!-- BEGIN records-family/1 -->
## The family conventions — records-family/1

This module is one of four that share one way of keeping records:
`rasa.module.notes` (notes + decisions), `rasa.module.schedule` (the
calendar), `rasa.module.crm` (the address book, accounts, the sales funnel) and
`rasa.module.messages` (every kind of message). This section is **identical
in all four rules files**; each module's own law follows it. The shared code
that enforces it (`records.py`) is identical in all four as well, and each
module's own gate (`bin/check-manifest`) proves both.

Rules marked **F-nn** are checked by the validator under that id. Rules
marked **judgement** are for a person; no machine can settle them.

### One module, one root

Each module owns one directory at the project root — `notes/`, `schedule/`,
`crm/`, `messages/` — and writes nothing outside it except its installed
surface under `.claude/`. Inside a root, `history.tsv`,
`<module>.config.yml`, `.state/` and `_archive/` are reserved.

### One record, one file

- A record is one UTF-8, LF, newline-terminated `.md` file (**F-01**):
  frontmatter between two `---` lines, then a markdown body.
- The filename is `<ID>-<slug>.md` (or exactly `<ID>.md` for a record type
  without a title) (**F-02**). The slug is lower-case words joined by `-`,
  at most 60 characters, and cosmetic: nothing ever joins on it.
- The id prefix says what the record is, and it must belong to this module
  (**F-03**).
- **The title is the H1.** Exactly one `# ` line, and it is the first
  non-blank line of the body (**F-04**). There is no `title:` key.
- **One fact, one home.** A fact is stored twice only when it is immutable
  and machine-written. Anything derivable — backlinks, "superseded", "past",
  "needs reply", an account's contacts — is computed, never stored.

### The frontmatter grammar — a strict subset of YAML

Any YAML tool can read these files; the validator accepts only this subset
and names the line it rejects (**F-05**).

```yaml
---
# comments are whole lines
id: CARD-0042
tags: [family, climbing]
name: {given: Jane, family: Doe}
email:
  - {label: work, value: jane@acme.com, pref: true}
x-source_system: legacy-crm
---
```

- Keys are lower-case (`a-z 0-9 _`); `x-<name>` is the extension namespace,
  kept verbatim and never interpreted. Any other key the record type does not
  define is an error (**F-06**). A key appears once (**F-07**).
- A value is a scalar, a flow list `[a, b]`, a flow map `{k: v}`, or a block
  list of scalars or flow maps (`  - ` two spaces, dash, space). Nothing
  nests deeper. No null, no `~`, no anchors, no multi-line values, no comment
  after a value. **To say nothing, omit the key.**
- Every value is read as text; the record type's JSON Schema says what it
  must look like. The tools write keys in the schema's order and quote a
  value whenever another YAML reader could misread it.

### Ids and references

- Every record has one id, never reused and never renumbered (**F-08**
  unique, **F-09** grammar). Ids are `PREFIX-NNNN` (four digits or more);
  the one exception is the account, keyed `acct-<slug>`.

  | prefix | record | module |
  |---|---|---|
  | `NOTE`, `DEC` | note, decision | notes |
  | `EVT` | event | schedule |
  | `CARD`, `acct-<slug>`, `LEAD` | contact card, account, lead | crm |
  | `THR`, `MSG` | thread, message | messages |
  | `TASK` | task (read, never written) | `rasa.module.tasks` |

- **Ids are the only join key.** In frontmatter, a reference is a bare id
  (`about: [CARD-0042]`). In a body, it is a wiki-link `[[CARD-0042]]` or
  `[[CARD-0042|Jane]]`; `@acct-<slug>` in prose also names an account.
- References resolve across the whole family. A frontmatter reference into a
  mounted module that names no record is an error (**F-10**); a body link
  that names no record is a warning (**F-11**); a reference into a module
  that is not mounted here is unverifiable and only noted (**F-12**). No
  module ever requires another.

### The history log — `<root>/history.tsv`

```
at	id	verb	from	to	actor	note
2026-09-28T14:03:11Z	NOTE-0001	new	-	inbox	chazz
2026-09-28T14:09:40Z	NOTE-0001	move	inbox	work	chazz
```

- Seven tab-separated columns under that exact header (**F-13**); `at` is a
  UTC stamp and never runs backwards (**F-14**).
- `from` and `to` are the record's place (its directory inside the root) or a
  `key=value` status, or `-`.
- Every record on disk was filed by a `new` or `import` line (**F-15**), and
  sits where its last place line says (**F-16**). A filed id whose file is
  gone is reported (**F-17**); its number is never issued again.
- Only the tools append to it. **Never edit it by hand.** `check --fix`
  repairs F-15/F-16 with a `reconcile` line by `unknown`; it never invents
  a person or a date.

### `updated` is a fact

The tools keep a cache of each record's content in `<root>/.state/` (it has
its own `.gitignore`). A record whose content changed while `updated` did
not is an error (**F-18**) — run `<tool> touch <ID>`. Some records are
**frozen** (a ratified decision; a message once sent or received): changing
their content at all is an error (**F-19**). Frozen records are superseded
or followed by a new record, never rewritten.

### Archive, never delete

The tools never delete a record. `archive` moves it under `_archive/` and
`restore` brings it back; records with a lifecycle end in a terminal state
instead. Deleting by hand is detected (**F-17**). **Judgement:** a person
may still choose to erase personal data for a legal or privacy reason — do
it deliberately, outside the tools, and say so in the project's own record.

### Configuration — `<root>/<module>.config.yml`

- Same grammar; `schema: rasa.module.<module>/1` names the ledger format;
  unknown keys and malformed values are errors (**F-20**). A project with no
  config is valid, except for the one command behind the module's hard-stop.
- **Declare to constrain.** Every vocabulary — tags, types, notebooks,
  calendars, groups, stages, channels, labels — follows one rule: absent or
  `[]` means free (only the grammar is checked); a non-empty list is closed,
  and anything undeclared is an error (**F-21**).
- `actors` (declare to constrain) and `default_actor` are common to all four.

### Actors, dates and times

- Every `created_by` and every history actor is a handle
  (`^[a-z0-9][a-z0-9._-]{0,31}$`) or `unknown` (**F-22**). The tools take
  `--by`, else `$RASA_ACTOR`, else `default_actor`, else they refuse —
  attribution is never invented.
- `created` and `updated` are real `YYYY-MM-DD` dates, never in the future,
  and `updated` is never before `created` (**F-23**).
- A moment is RFC 3339 **with an offset** (`2026-09-28T14:00:00-04:00`),
  never a bare local time (**F-24**). A timezone is an IANA name that
  resolves (**F-25**).
- Relative input — `today`, `tomorrow`, `+3d`, `fri 9am` — is resolved when
  it is captured and stored absolute.
- Every other field obeys its record type's JSON Schema, installed under
  `.claude/schemas/<module>/` (**F-26**).
- A `.md` file inside a root that is not a record is listed once and left
  alone (**F-27**).

### The tools

- Two programs per module under `.claude/bin/`: the tool (`notes`,
  `schedule`, `crm`, `messages`) and its validator (`check-notes`, …).
  Pure Python standard library: no network, no version control, nothing to
  install.
- **Every change goes through the tool.** One command validates, writes the
  record atomically, appends the history line and refreshes the cache — one
  act, under a lock. A refused command writes nothing and exits 1; an
  unusable environment exits 2. `--dry-run` shows what would happen;
  `--json` gives machine output.
- The validator exits 0 when there are no errors (warnings allowed). Run it
  before calling anything finished.

### The outside world

These records hold personal data about other people. **No tool in this
family opens a network connection, sends anything, or syncs anything** — each
module's gate refuses to ship one that tries. Moving data in and out is done with files
(`.ics`, `.vcf`, `.eml`, mbox, SMS backup XML). Sending and syncing belong
to Connections (canon task SA-031), not to this family. **Judgement:**
record about people only what the project's seam allows.
<!-- END records-family/1 -->

## 1. What this module keeps

Three records, one root, joined by ids:

| record | id | file | what it is |
|---|---|---|---|
| **contact card** | `CARD-nnnn` | `crm/contacts/CARD-0001-jane-doe.md` | one person or organization — anyone you deal with, customer or not |
| **account** | `acct-<slug>` | `crm/accounts/acct-acme.md` | a customer or company: the hub |
| **lead** | `LEAD-nnnn` | `crm/leads/<stage>/LEAD-0001-acme-renewal.md` | a sales opportunity against an account |

```
crm/
  crm.config.yml             what the project declares
  history.tsv                every change, one line each
  contacts/                  the address book
  contacts/_archive/         archived and merged-away cards, never deleted
  accounts/                  one file per account; the file name is the id
  leads/new/ … leads/won/ leads/lost/   one directory per stage
```

- **The address book is for everyone.** A card does not need an account:
  your accountant, a supplier's driver and a friend's partner are cards too.
  A card is *attached* to an account when the person works with you on the
  customer's behalf — judgement.
- **The account is the hub.** "Current customers" are exactly the accounts
  in the active status. An account's people are derived from the cards that
  name it; its deals from the leads that name it. Neither list is stored on
  the account (one fact, one home; the account has no key for them, **F-06**).
- **This module owns the account registry — deliberately.** The split
  business-ops modules (`rasa.module.leads`, `contracts`, `invoices`,
  `field-log`) treat `@acct-<slug>` as an opaque join key and keep no
  account records. `rasa.module.crm` materializes the account itself. When
  it is mounted, it is the accounts source of truth for the project: a
  co-mounted split module joins to `crm/accounts/` by the same handle.
  **Do not keep a second, competing accounts list** — judgement.
- The contact id is **`CARD`, not `CON`** (**F-09**): `rasa.module.contracts`
  already mints `CON-nnn`, and one prefix must mean one thing across a
  project.

## 2. The contact card

Aligned with vCard 4.0 (RFC 6350), so any address book can take it in and
give it back (§7).

```yaml
---
id: CARD-0042
created: 2026-09-28
created_by: chazz
updated: 2026-09-30
name: {given: Jane, family: Doe}
org: Acme Inc.
title: Head of Operations
email:
  - {label: work, value: jane@acme.example, pref: true}
  - {label: home, value: jane.doe@example.org}
phone:
  - {label: mobile, value: +1 555 0100, pref: true}
address:
  - {label: work, street: 1 Main St, locality: Springfield, region: IL, code: "62701", country: US}
handle:
  - {service: signal, value: "+15550100"}
birthday: --04-12
groups: [clients]
accounts:
  - {acct: acct-acme, role: decision-maker, primary: true}
related:
  - {rel: colleague, who: CARD-0051}
uid: urn:uuid:5b1c0c1e-3f7a-4a7e-9a55-0d2b8d6a2f11
---

# Jane Doe

Prefers email before 10am. Met at the spring trade fair.
```

| key | vCard | what it is |
|---|---|---|
| `id`, `created`, `created_by`, `updated` | — | bookkeeping; the tools write them |
| the H1 | FN | the display name — the title of the card (**F-04**) |
| `kind` | KIND | `org` for an organization; absent = an individual |
| `name` | N | `{prefix, given, additional, family, suffix}` — the structured name |
| `nickname` | NICKNAME | a list |
| `org`, `title` | ORG, TITLE | where they work and their job title, as text |
| `email`, `phone` | EMAIL, TEL | lists of `{label, value, pref}` |
| `address` | ADR | list of `{label, street, locality, region, code, country, pref}` |
| `url` | URL | list of `{label, value}` |
| `handle` | IMPP | chat and social handles, `{service, value}` |
| `birthday`, `anniversary` | BDAY, ANNIVERSARY | `YYYY-MM-DD`, or `--MM-DD` when the year is unknown |
| `groups` | CATEGORIES | address-book groups |
| `accounts` | — | `{acct, role, primary}` — the customer accounts this person is attached to |
| `related` | RELATED | `{rel, who}` — other cards (spouse, colleague, agent …) |
| `tz`, `lang`, `photo` | TZ, LANG, PHOTO | IANA zone; language tag; a URI or a project-relative path — never image data |
| `uid` | UID | stamped once by the tools (`urn:uuid:…`), or kept from an import; the key import dedupes on |
| `merged_into` | — | only on an archived card that was folded into another (§3) |

- A card lives in `crm/contacts/`, or in `crm/contacts/_archive/` once
  archived — nowhere else (**C-01**).
- Every field obeys `.claude/schemas/crm/card.schema.json` (**F-26**).
- **At most one preferred item** per list: one `pref: true` among the
  emails, one among the phones, one among the addresses (**C-07**). `pref`
  is only ever `true`; an item that is not preferred omits the key.
- A card names an account at most once, and **an account has at most one
  primary contact** across all live cards (**C-08**). Archived cards do not
  count.
- A card is never related to itself (**C-09**); `related` names another card
  that exists (**F-10**).
- If `labels`, `groups` or `contact_roles` are declared, every email /
  phone / address / URL label, every group and every account role is one of
  them (**F-21**).
- The same email on two live cards is reported — probably one person twice
  (**C-13**, a warning; the fix is `crm contact merge`).
- **Record only what the relationship needs** — judgement, governed by
  `.claude/crm-gate.md` §4. A card is personal data about someone else.

## 3. Changing a card

Every change goes through the tool; each is one act with one history line
(a change made any other way is caught: **F-15**, **F-16**, **F-18**).

```
crm contact new "Jane Doe" --given Jane --family Doe \
    --email work:jane@acme.example --phone "mobile:+1 555 0100" \
    --account acct-acme:decision-maker:primary --group clients --birthday 04-12
crm contact set    CARD-0042 title "Head of Operations"
crm contact set    CARD-0042 name.additional Q.
crm contact unset  CARD-0042 anniversary
crm contact add    CARD-0042 email home:jane.doe@example.org --pref
crm contact add    CARD-0042 address "label=home;street=1 Elm St;locality=Springfield;region=IL;code=62704;country=US"
crm contact add    CARD-0042 handle signal:+15550100
crm contact add    CARD-0042 related colleague:CARD-0051
crm contact remove CARD-0042 email jane.doe@example.org
crm contact pref   CARD-0042 phone mobile
crm contact rename CARD-0042 "Jane Q. Doe"
```

**The item grammar.** `label:value` for an email, phone or URL
(`work:jane@acme.example`, `mobile:+1 555 0100`, `home:https://jane.example`);
`service:value` for a handle (`signal:+15550100`); `acct-x[:role[:primary]]`
for an account link; `rel:CARD-nnnn` for a relation; and `k=v;k=v` for any of
them — the only form for an address. `--pref` makes the new item the
preferred one and clears the others. `remove` and `pref` name an item by its
value, its label (when only one item has it) or its position (`#2`). The tool
checks every item against the schema and the declared vocabularies before it
writes (**F-26**, **F-21**).

**Merging duplicates.** `crm contact merge KEEP DROP` folds DROP into KEEP in
one act: every list is unioned into KEEP, a field KEEP lacks is filled from
DROP, a field both have and disagree on keeps KEEP's value (the tool prints
each one it kept), DROP's notes are appended to KEEP's body, and DROP moves to
`contacts/_archive/` with `merged_into: KEEP`. Both get a history line.
`merged_into` is set only this way: only on an archived card, never on itself,
and it names a live card (**C-10**). References to DROP keep resolving — an
archived card is still a record — and `crm contact show DROP` says where it
went. Whether two cards are the same person is judgement: an email in common
is a hint, not proof.

**Archive, never delete.** `crm contact archive` moves a card to
`contacts/_archive/`; `crm contact restore` brings it back. A merged card
restores only with `--unmerge`, which clears `merged_into` — otherwise it
would bring the duplicate back, and a live card never carries `merged_into`
(**C-10**). Deleting a card by hand is reported (**F-17**).

**Editing by hand** is allowed for the body (the notes). Then run
`crm touch CARD-nnnn` so `updated` stays true (**F-18**).

## 4. The account

```yaml
---
id: acct-acme
created: 2026-03-02
created_by: chazz
updated: 2026-09-28
status: active
since: 2026-09-28
tier: mid-market
owner: chazz
website: https://acme.example
email:
  - {label: billing, value: billing@acme.example, pref: true}
tags: [renewal-2027]
---

# Acme Inc.

Two sites; the Springfield plant is the decision centre.
```

| key | required | what it is |
|---|---|---|
| `id` | yes | `acct-<slug>` — the id, the file name and the `@acct-<slug>` join key |
| `created`, `created_by`, `updated` | yes | bookkeeping |
| `status` | yes | one of `account_statuses` (default `prospect`, `active`, `churned`) |
| `since` | no | the day it entered its current status; never in the future |
| `tier`, `tags` | no | declare `tiers` / `tags` to constrain (**F-21**) |
| `owner` | no | who is accountable for the relationship (a handle) |
| `website`, `email`, `phone`, `address` | no | the account's own details, same shapes as a card's |

- An account lives in `crm/accounts/` and **the file is exactly
  `<id>.md`** — the stem is the id, and there is no slug after it (**C-01**,
  **C-02**). The display name is the H1; `crm account rename` changes it,
  never the id. An id is never renamed and never reused (**F-08**).
- `status` is one of the account statuses (**C-11**). A new account starts
  in the first one. **Status changes only through the tool** —
  `crm account status acct-x STATUS`, or `crm lead win` — so the history
  records every change; a status edited by hand no longer matches the
  history and is reported (**C-15**; `check --fix` records it with a
  `reconcile` line).
- `since` is the day the account entered its current status; each status
  change stamps it, and it is never in the future (**C-16**).
- **Accounts are never archived** — churn is a status, and a churned
  customer is history worth keeping (**C-01**).
- What "active" and "churned" mean for this business is judgement, written
  in `.claude/crm-gate.md` §3.
- `crm account show acct-x` is the account's whole picture: its people (from
  the cards), its leads by stage, and — when those modules are mounted, read
  only — how many events, message threads and notes elsewhere in the family
  name it.

## 5. The lead and the funnel

```yaml
---
id: LEAD-0007
created: 2026-09-01
created_by: chazz
updated: 2026-09-28
account: acct-acme
contact: CARD-0042
source: referral
owner: chazz
value: "12000"
currency: USD
expected_close: 2026-11-15
next_action: Send the revised quote
next_action_due: 2026-10-02
qualified_on: 2026-09-20
---

# Acme — second-site rollout
```

| key | required | what it is |
|---|---|---|
| `account` | yes | the account the opportunity is against — a lead always belongs to a customer |
| `contact` | no | the person the deal is worked with (a card) |
| `source`, `owner` | no | where it came from (declare `sources` to constrain, **F-21**); who moves it |
| `value`, `currency` | no | the estimated value and its ISO 4217 currency, always together (**C-14**) |
| `expected_close`, `next_action`, `next_action_due` | no | the open loop; a due date needs an action (**F-26**) |
| `closed`, `lost_reason`, `qualified_on` | — | stamped by the lifecycle verbs, never by hand |

**The stage is the directory.** A lead lives one level under `crm/leads/`,
in a directory named for its stage (**C-01**), and that stage is one of the
declared `stages` (**C-03**). There is no stage key; moving a lead is moving
its file, which only the tool does (**F-16**).

```
new ──▶ contacted ──▶ qualified ──▶ proposal ──▶ won
                                           └──▶ lost
```

The default funnel above is replaced by declaring `stages`; won, lost and
qualified are named by `won_stage`, `lost_stage` and `qualified_stage`.

- **New leads start in the first stage.** `crm lead new "Title" --account
  acct-x` files it there, and the filing line records that place (**F-15**).
- **Advancing.** `crm lead advance LEAD --to STAGE` moves a lead between open
  stages, forwards or back.
- **Qualifying — the hard-stop.** Entering the qualified stage, or any open
  stage after it, for a lead not yet qualified requires the declared
  `qualification` criteria: the tool refuses until they are declared, and
  then refuses unless every one is asserted with `--met a,b,c`. It stamps
  `qualified_on` and writes the criteria into the history line. A lead at or
  past the qualified stage — including a won lead — has `qualified_on`; a
  lead before it does not (a lost lead may or may not);
  `qualified_on` is never before `created`, after `closed`, or in the future
  (**C-06**). Moving a lead back before the qualified stage clears it.
- **Whether a criterion is really met** is judgement — `.claude/crm-gate.md`
  §1 says what each one means. `--met` is a person's assertion; make it
  honestly.
- **Winning.** A deal is never won unqualified. A lead that was not
  qualified on the way is qualified as it is won — the same hard-stop, the
  same `--met a,b,c` for every declared criterion — so a won lead always
  carries `qualified_on` (**C-06**). `crm lead win LEAD` is one act on two
  records: the lead moves to the won stage with `closed` stamped, and — unless its account is already
  in the active status — the account moves to the active status with `since`
  stamped. Two records, two history lines. **A won lead is the moment a
  prospect becomes a current customer.** A won lead whose account is still in
  the initial status is reported (**C-12**, a warning).
- **Losing.** `crm lead lose LEAD --reason "…"` moves it to the lost stage
  with `closed` and `lost_reason`. The reason is required (**C-05**): a lost lead is
  memory, and why it was lost is often the most useful thing in the ledger.
  Nothing on the account changes.
- `closed` is present exactly on won and lost leads, and never before
  `created` or in the future (**C-04**); `lost_reason` exactly on lost ones
  (**C-05**).
- **Reopening.** `crm lead reopen LEAD --to STAGE` moves a won or lost lead
  back to an open stage and clears `closed` and `lost_reason`. It never
  touches the account: if a win is undone, whether the account is still a
  customer is a separate decision (`crm account status`) — judgement.
- **Leads are never archived and never deleted** — won and lost are their
  terminal states (an `_archive/` under `leads/` is not a stage, **C-03**;
  **F-17** reports a deleted file).
- **`value` is an estimate.** It sizes and ranks the funnel; booked revenue
  lives in a contract or an invoice, not here — judgement.
- Other lead fields change with `crm lead set|unset LEAD FIELD …`; `closed`,
  `lost_reason` and `qualified_on` refuse — only the lifecycle verbs write
  them, and a hand edit that breaks their stage conditions is caught
  (**C-04**, **C-05**, **C-06**).

## 6. Views

- **`crm pipeline`** — the board: every stage in order with its lead count
  and its value summed **per currency** (amounts in different currencies are
  never added together), plus the total of the open stages. `--account`
  narrows it; `--leads` lists the leads under the board.
- **`crm birthdays [--next 30]`** — birthdays in the next N days, today
  included, with the age they turn when the year is known. A `--MM-DD`
  birthday has no age. A 29 February birthday is shown on 28 February in a
  common year. `--anniversaries` adds anniversaries.
- **`crm groups`** — the groups with their live-card counts.
- **`crm contact list · find · show`**, **`crm account list · show`**,
  **`crm lead list · show`**, **`crm history [ID]`** — read-only. Every read
  verb takes `--json`.

## 7. Address books in and out — vCard files

- **`crm export [CARD…] [--group G] [--account acct-x] [--out FILE]`**
  writes vCard 4.0: CRLF line endings, lines folded at 75 octets, text
  escaped; FN, N, NICKNAME, ORG, TITLE, EMAIL / TEL / ADR / URL with their
  TYPE and `PREF=1`, IMPP for handles, BDAY and ANNIVERSARY (including
  `--MMDD`), CATEGORIES for groups, NOTE for the body, UID, KIND, TZ, LANG,
  PHOTO (a URI only) and RELATED (by the related card's UID). A label that is
  not a standard type travels as an `X-ABLabel` group, as the common address
  books do. `--out` never replaces an existing file without `--force`.
- **`crm import FILE.vcf`** reads vCard 3.0 and 4.0 (and the usual 2.1
  habits): folded lines, escapes, `TYPE` in either syntax, QUOTED-PRINTABLE
  with CHARSET, grouped properties (`item1.EMAIL` + `item1.X-ABLabel`), and
  both preference styles. Embedded photo data is never stored; the import
  says it skipped it. Anything that fails the schema or a declared
  vocabulary is dropped **and reported** — nothing invalid is written
  (**F-26**, **F-21**).
- **Dedupe, never overwrite.** An incoming card that matches one here — by
  UID first (a card merged away resolves to the card that absorbed it), then
  by an exact email — is skipped and named. With `--update` it is folded in
  the way `merge` folds: missing fields filled, lists unioned, and every
  disagreement kept as it is here and printed. The history records each
  created card as `import` and each folded one as `update`.
- **Review what you import** — judgement. An exported address book carries
  everything its owner ever typed; `.claude/crm-gate.md` §4 decides what may
  stay.

## 8. The tool

| verb | does |
|---|---|
| `crm contact new "Name" [--given G --family F …] [--email L:ADDR]… [--phone L:NUM]… [--address K=V;…]… [--url L:URL]… [--handle S:H]… [--org O] [--title T] [--account acct-x[:role[:primary]]]… [--related REL:CARD]… [--group G]… [--birthday D] [--kind org] [--body …]` | add a card |
| `crm contact set · unset · add · remove · pref ID FIELD …` | edit a card's fields (§3) |
| `crm contact rename ID "Name"` · `merge KEEP DROP` · `archive ID` · `restore ID [--unmerge]` | rename · fold duplicates · archive · bring back |
| `crm account new "Name" [--slug s] [--status S] [--tier T] [--owner O] [--website U] …` | add an account |
| `crm account status acct-x STATUS [--since D]` | change its status |
| `crm account set · unset · add · remove · pref · rename …` | edit an account |
| `crm lead new "Title" --account acct-x [--contact CARD] [--source S] [--value N --currency C] [--next "…" --due D]` | capture a lead |
| `crm lead advance ID --to STAGE [--met c1,c2]` | move it; qualify it |
| `crm lead win ID` · `lose ID --reason R` · `reopen ID --to STAGE` | close it · reopen it |
| `crm lead set · unset · rename …` | edit a lead |
| `crm pipeline` · `birthdays` · `groups` | views |
| `crm import FILE.vcf [--update] [--group G]` · `crm export … [--out FILE]` | vCard in and out |
| `crm touch ID` · `crm history [ID]` · `crm check [--fix]` | record a hand edit · the log · validate |

Every write verb takes `--by`, `--dry-run` and `--json`.

## 9. Soft cross-references

This module stands alone and plays well with its neighbours when they are
mounted. None is ever a `requires.elements[]` dependency.

- **`rasa.module.schedule`** — an event's `account` is an `acct-<slug>`,
  its attendees and organizer are cards. **`rasa.module.messages`** — a
  thread's participants resolve to cards, a thread can name an account.
  **`rasa.module.notes`** — a note is `about` a card, an account or a lead.
  All of them resolve here when crm is mounted (**F-10**, **F-12**).
- **`rasa.module.contracts`** — a won lead hands off to a contract; crm
  records the win and makes the account a customer, it never writes the
  agreement. **`rasa.module.invoices`** — an active customer is billed; crm
  answers "who is a customer", invoices owns the money.
  **`rasa.module.field-log`** — a visit joins to the account by
  `@acct-<slug>`; a won lead can prompt a kickoff visit.
- **`rasa.module.tasks`** — a lead's `next_action` can become a `TASK-…`
  when the work needs assigning; `next_action` stays the lightweight view.
- If a neighbour is not mounted the hand-off simply does not happen; the
  record still reaches its terminal state. **Never harden a hand-off into a
  dependency** — judgement.

## 10. What no machine will catch

Every invariant is cited at the rule it enforces: F-01…F-27 in the family
conventions above; C-01 §2 §4 §5 · C-02 §4 · C-03 §5 · C-04 C-05 C-06 §5 ·
C-07 C-08 C-09 §2 · C-10 §3 · C-11 C-15 C-16 §4 · C-12 C-14 §5 · C-13 §2.
These are the ones nobody checks but you:

- whether a lead really met the criteria its `--met` asserted (§5)
- whether a person's card holds only what the relationship needs, and
  whether an import was reviewed (§2, §7)
- whether two cards are the same person before they are merged (§3)
- whether an account is really still a customer — churn is a call only a
  person can make (§4)
- whether a lost reason is honest enough to learn from (§5)
- whether a value is a real estimate, and whether the next action is the
  real next action (§5)
- whether a second accounts list has crept in somewhere else (§1)
