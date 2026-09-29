# `rasa.module.crm` — design record

Author-time document; not installed (`opt-in`). The installed law is
`content/crm-rules.md`; this file is the *why* behind it.

---

## 1. What changed in 0.2.0, and why

**Owner direction, 2026-09-28:** *"we need modules for each of the
following… notes, calendar events, messages, contacts — we need as much
structure and organization as we can get."* Asked where contacts should go,
the owner chose to **fold them into `rasa.module.crm`** rather than add a
`module.contacts`: crm's Contact becomes the vCard 4.0 (RFC 6350) aligned
address book for **all** people and organizations — a contact no longer
needs an account — while the Account (the customer hub) and the Lead (the
sales funnel) are kept and re-stored to the same standard. Asked how deep,
the owner chose the **`rasa.module.tasks` v1.0.0 standard**: numbered
invariants, JSON Schemas, one record per file, an atomic tool, an
append-only history, a validator and a release gate.

0.1.0 was a shell — a prose spine, a specification, a seam and three
hand-kept ledger files (`ACCOUNTS.md`, `CONTACTS.md`, `LEADS.md`), no tool,
never pushed. Its still-true content is folded into 0.2.0:

| 0.1.0 said | 0.2.0 does |
|---|---|
| crm owns the account registry (the deliberate divergence from the split business-ops modules) | kept — `crm/accounts/`, one file per account, the stem is the id; crm-rules §1 |
| won → the account becomes active | enforced as one act: `crm lead win` writes both records and two history lines; C-12 warns when a won lead's account never moved |
| lost is terminal and never deleted; record why | `crm lead lose --reason` is required; C-04/C-05 hold `closed`/`lost_reason` to the stage; F-17 reports a deleted lead |
| never delete an account; churn is a status | accounts are never archived (C-01); status changes are logged and checked against history (C-15) |
| at most one primary contact per account | C-08, across live cards; the tool refuses a second primary |
| ids monotonic, dates absolute | the family core (F-08, F-23; relative input resolved at capture) |
| the gate holds stages, qualification bar, sources, statuses/churn, roles | split into the machine half (`crm.config.yml`, checked) and the judgement half (`.claude/crm-gate.md`, prose) |
| `/qualify` hard-stops when the bar is unfilled | the hard-stop is in the tool: `crm lead advance` into the qualified stage refuses until `qualification` is declared, then requires `--met` for every criterion |
| "SA-032 — engagement-hub primitive" | removed: no canon task by that name exists (the number belongs to an unrelated task). The divergence is described without a task number. |

**The extract-after-proof gate.** 0.1.0 held the skills until a real parent
declared the module. That gate was lifted by the owner's direct request, not
by a consumer appearing — there is still **no installed consumer** (every
`rasa.lock.json` and `rasa.json` under the workspace volume and the home
directory was searched on 2026-09-28). What the gate protected against is now
carried by the 1.0.0 bar below.

## 2. The records family

crm 0.2.0 is one of four modules built together to one standard,
**records-family/1** (notes, schedule, crm, messages). The shared conventions
are stated once — the family block in each rules file, identical in all four
— and enforced once, by `records.py`, identical in all four.
`bin/check-manifest` proves both against the `FAMILY` stamp and compares the
stamp with every sibling on disk. See `module-notes/content/BUILD_PLAN.md` §2
for the family-wide design choices; they apply here unchanged.

## 3. crm-specific decisions

| decision | why |
|---|---|
| Contact id prefix **`CARD`**, not `CON` | `rasa.module.contracts` already mints `CON-nnn`; one prefix must mean one thing in a project that mounts both |
| A card needs no account | the address book is for everyone (owner decision); the customer link is `accounts: [{acct, role, primary}]` on the card |
| vCard 4.0 field names and shapes (FN = H1, N as a map, labelled lists with one `pref`) | any address book can take the data in and give it back; the mapping is 1:1 for everything we store |
| `pref` and `primary` are only ever `true` | "to say nothing, omit the key" — `pref: false` would be a second representation of the default |
| An account's contacts and leads are derived, never stored on the account | one fact, one home; the 0.1.0 `contacts:` list on the account drifted by construction |
| The account id is `acct-<slug>` and the file stem **is** the id (no slug suffix) | it is the business-ops `@acct-<slug>` join key; the family core already resolves `acct-` ids from `crm/accounts/` |
| `since` = the day the account entered its current status | one meaning for every status (prospect since, customer since, churned since); every status change stamps it |
| Account status only through the tool, checked against history (C-15) | `crm lead win` writes status; a hand edit would make the history lie about when a customer became one |
| The stage is the lead's directory; no `stage` key | the `rasa.module.tasks` survey showed a state field disagreeing with its directory in 301 of 536 files; the directory cannot disagree with itself |
| `stages` and `account_statuses` have defaults and are always closed | the tool cannot file a lead or create an account without them; every other vocabulary is declare-to-constrain |
| Qualification criteria are names in config, meanings in the gate | the tool can check that each named criterion was asserted; only a person can judge that it is true |
| `--met` must name every criterion | a partial assertion is not a qualification; the history line records exactly what was asserted |
| Qualifying is required to enter the qualified stage **or any later open stage** | otherwise advancing straight to `proposal` would skip the hard-stop |
| Moving back before the qualified stage clears `qualified_on` | a lead that is no longer qualified must be re-qualified against the current criteria |
| A deal is never won unqualified: `win` qualifies an unqualified lead (same hard-stop, same `--met`), and C-06 requires `qualified_on` on every won lead | otherwise `win` straight from `contacted` walks round the one gate this module exists to hold (found in the orchestrator's hands-on pass, 2026-09-29) |
| `win` flips the account only when it is not already active | a second win for a live customer changes nothing on the account; one history line then, not two |
| `reopen` never touches the account | undoing a win does not undo a customer relationship; that is `crm account status`, a person's call |
| `value` + `currency` always together; sums per currency | adding USD to EUR is a lie a board should never tell |
| A 29 February birthday shows on 28 February in common years | the common convention; stated in the rules so nobody is surprised |
| `merge` unions lists, fills gaps, keeps KEEP on conflicts and prints them; DROP archived with `merged_into` | never overwrite silently; references to DROP keep resolving; `show DROP` says where it went |
| A merged card restores only with `--unmerge` | restoring it plainly would bring the duplicate back with a dangling `merged_into` |
| Every new card gets `uid: urn:uuid:…` | the stable key an export→import round trip dedupes on; imported cards keep their own UID |
| Import dedupe: UID, then exact email; skip unless `--update`; `--update` folds like merge | an address-book import must be repeatable without creating duplicates or destroying local edits |
| Non-standard labels export as `itemN.X-ABLabel` | what Apple and Google Contacts read and write; a bare `TYPE=assistant` is not portable |
| Embedded photo data is never stored | a card is text; binary data belongs in files a card can point at |
| The tool runs the validator's per-record checks (`validate.check_one`) before every write | the tool cannot write what `check-crm` would reject; one law, one implementation |
| Generic `set/unset/add/remove/pref` instead of one verb per field | 20+ fields on a card; one grammar, validated against the schema, is smaller and stricter than 20 verbs |
| `merge` allowlisted in four named files | the owner specified `crm contact merge`; it is address-book vocabulary here, and the rest of the hard rule still applies to those files |

## 4. Invariant map

| id | rule | where |
|---|---|---|
| F-01…F-27 | the family conventions | `records.py`, family block |
| C-01 | location: cards in `contacts/` or `contacts/_archive/`; accounts in `accounts/`, never archived; leads one level under `leads/` | `validate.check_card` / `check_account` / `check_lead` |
| C-02 | an account's file is exactly `<id>.md` | `validate.check_account` |
| C-03 | a lead's stage directory is a declared stage | `validate.check_lead` |
| C-04 | `closed` exactly in won/lost; not before `created`, not in the future | `validate.check_lead` |
| C-05 | `lost_reason` exactly in the lost stage | `validate.check_lead` |
| C-06 | `qualified_on` required at/after the qualified stage (open), absent before it; dated sanely | `validate.check_lead` |
| C-07 | at most one `pref: true` per list field (cards and accounts) | `validate._prefs` |
| C-08 | a card names an account once; at most one primary per account across live cards | `validate.check_card` + `check_primaries`; the tool refuses |
| C-09 | a card is not related to itself | `validate.check_card` |
| C-10 | `merged_into` only on an archived card; not itself; names a live card | `validate.check_card` + `check_merges` |
| C-11 | account status is one of `account_statuses` | `validate.check_account` |
| C-12 | (warning) a won lead's account is not still in the initial status | `validate.check_won_accounts` |
| C-13 | (warning) the same email on two live cards | `validate.check_duplicate_emails` |
| C-14 | `value` and `currency` together | `validate.check_lead` |
| C-15 | an account's status equals the one its history last recorded (fixable: reconcile line) | `validate.check_status_history` |
| C-16 | an account's `since` is not in the future | `validate.check_account` |

Declared vocabularies (labels, groups, contact roles, sources, tiers, tags)
are reported under the family invariant **F-21**, as in every family module;
the two always-closed lists have their own ids (C-03 stages, C-11 statuses).

## 5. Deferred, deliberately

- **Syncing with an address-book or CRM service** (CardDAV, Google, a hosted
  CRM). That is Connections (canon SA-031); this module is files only.
- **Activities / interaction log per contact.** Calls, emails and meetings
  are messages and events in the sibling modules; `crm account show` counts
  them. A crm-local activity record would store the same fact twice.
- **Photos as managed files.** `photo` is a URI or a path; the module stores
  no image data and manages no image directory.
- **vCard `KIND:group` and `KIND:location`, `MEMBER`, `GENDER`, `ROLE`,
  `LOGO`, `SOUND`, `KEY`, `GEO`.** Not needed yet; the import names what it
  skipped.
- **ORG units** (`ORG:Acme;Sales`). Import keeps the organization and
  reports the dropped units.
- **Multi-currency conversion.** Sums are per currency by design.
- **Lead line items, probability/weighting, forecasting.** Estimate-level
  `value` only; forecasting is a reporting concern above this ledger.
- **Migration from 0.1.0 ledgers.** No one installed 0.1.0. If one surfaces,
  the conversion is mechanical: each ACCOUNTS entry → `crm account new`,
  each CONTACTS entry → `crm contact new --account …`, each LEADS entry →
  `crm lead new` + `advance` (with `--met` for qualified ones).

## 6. Version plan

- **0.2.0** — this: the address book, accounts and funnel to the
  records-family/1 standard, with vCard interop. Local branch; merge/tag/push
  on the owner's go-ahead.
- **0.2.x** — fixes from the first real consumer.
- **1.0.0** — the record shapes, the seam and the install layout locked,
  after at least two real projects have run crm unchanged. A shape change
  after that is a major version with a migration tool, as in
  `rasa.module.tasks`.
