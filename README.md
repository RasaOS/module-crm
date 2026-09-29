# Rasa · Module · CRM

**Canonical name:** `rasa.module.crm`
**Repo / folder:** `module-crm`
**Kind:** `module` (mounts into a `domain` or a `tenant`)
**Contract:** Element Contract v1.3.0 · records-family/1
**Version:** 0.2.0
**Status:** 0.2.0 built on branch `claude/records-family`; 0.1.0 was a local-only shell and was never published.

## What this is

The address book, the customer accounts and the sales funnel, one record per
file:

- **Contact cards** — every person and organization you deal with, aligned
  with vCard 4.0 (RFC 6350): structured names, emails / phones / addresses /
  URLs with labels and one preferred each, chat handles, birthdays, groups,
  relations, and links to the accounts a person works with you on. A card
  needs no account. Duplicates fold together with `crm contact merge`;
  archived cards are never deleted.
- **Accounts** — the customer hub, `acct-<slug>`. "Current customers" are
  the accounts in the active status. This module **owns the account
  registry**: when it is mounted, it is the one list of customers the other
  business modules join to.
- **Leads** — opportunities that move through the project's stages (the
  stage is the directory) to **won**, which makes the account a current
  customer in the same act, or **lost**, which keeps the reason.

```
lead ──advance──▶ … ──advance --met …──▶ qualified ──▶ … ──win──▶ won  (account → active)
                                                            └──lose──▶ lost (reason kept)
```

Qualifying a lead **hard-stops** until the project declares what "qualified"
means (`qualification` in `crm/crm.config.yml`), and then every criterion
must be asserted with `--met`.

## The records family

One of four modules built to one standard — **records-family/1** — with
`rasa.module.notes` (notes and the decision ledger), `rasa.module.schedule`
(the calendar) and `rasa.module.messages` (email, texts, chat, calls,
voicemail, letters). Same file grammar, same history log, same validator
conventions, and references that resolve across all four when they are
mounted together: an event's attendees, a thread's participants and a note's
subject can all be `CARD-…` ids, and an event or a thread can name an
`acct-…`. The shared core (`records.py`) is byte-identical in each, and each
module's release gate proves it.

## Install

```bash
bin/init /path/to/project
```

Installs `.claude/crm-rules.md`, `.claude/schemas/crm/`, the `/contact`,
`/account` and `/lead` skills, and two programs — `.claude/bin/crm` and
`.claude/bin/check-crm` — plus the project-owned `crm/` ledger and the
`.claude/crm-gate.md` seam. Pure Python 3 standard library: nothing else to
install, no network, no version control needed.

```bash
.claude/bin/crm account new "Acme Inc." --slug acme
.claude/bin/crm contact new "Jane Doe" --email work:jane@acme.example --account acct-acme:decision-maker:primary
.claude/bin/crm lead new "Acme renewal" --account acct-acme --contact CARD-0001 --value 12000 --currency USD
.claude/bin/crm lead advance LEAD-0001 --to qualified --met need,budget,decision-maker
.claude/bin/crm lead win LEAD-0001
.claude/bin/crm pipeline
.claude/bin/crm import contacts.vcf --dry-run
.claude/bin/check-crm
```

## Interop and privacy

vCard files in and out: `crm import` reads vCard 3.0 and 4.0 (dedupe by UID,
then by email; never overwrites), `crm export` writes vCard 4.0. No tool in
this module opens a network connection — syncing with an address-book
service belongs to Connections (canon task SA-031), not here. A contact card
is personal data about someone else; what may be recorded is the project's
call, written in `.claude/crm-gate.md`.

## Layout

- `content/crm-rules.md` — the installed law (family conventions + crm law)
- `content/schemas/` — card, account, lead and config JSON Schemas
- `content/bin/` — the `crm` tool, the `check-crm` validator, the `rasa_crm` package (including `vcard.py`)
- `content/skills/` — `/contact`, `/account`, `/lead`
- `seed/` — the project-owned seam, config, history header and directory placeholders
- `content/BUILD_PLAN.md` — the design record
- `bin/check-manifest` — the release gate (14 checks); `bin/init` — the installer
- `tests/` — the family-core suite (identical in all four modules) and the crm suite
