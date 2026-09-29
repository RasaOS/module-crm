---
name: contact
description: Keep the address book — add a person or organization as a vCard-aligned contact card, look someone up, update their emails, phones, addresses, handles, birthday or groups, attach them to a customer account, fold two duplicate cards into one, archive a card, see upcoming birthdays, or import/export a .vcf address book. Writes go through .claude/bin/crm so the card, the history line and the content cache change as one act. Use for "/contact", "add Jane to contacts", "what's Dana's number", "update her email", "she moved to Globex", "these two are the same person", "who has a birthday this month", "import my contacts.vcf", "export the clients group".
---

# /contact — the address book

You decide **what** to record about a person and whether it belongs here;
`.claude/bin/crm` makes the change. Never write, move or delete a card file
by hand — the tool keeps the history log and the content cache honest, and a
hand move or hand delete is exactly what `check-crm` reports as an error.

The law is `.claude/crm-rules.md` §1–§3 and §7. What may be recorded about a
person is `.claude/crm-gate.md` §4. If they ever disagree with this skill,
they win.

## Before the first write in a session

1. Read `crm/crm.config.yml` — the declared labels, groups and contact roles
   (a non-empty list is a closed vocabulary) and `default_actor`.
2. Read `.claude/crm-gate.md` §4 — the privacy rails. A card is personal data
   about someone else: record what the relationship needs, nothing more.
3. Know who is writing: `--by <handle>`, or `$RASA_ACTOR` / `default_actor`.
   Never invent a person; if nobody is declared, ask.

## Look before you add

```
.claude/bin/crm contact find dana
.claude/bin/crm contact find 555 0100          # phone digits work too
```

If the person is already here, update that card instead of adding a second
one. `crm contact new` warns when an email is already on another card.

## Adding

```
.claude/bin/crm contact new "Jane Doe" --given Jane --family Doe \
    --email work:jane@acme.example --phone "mobile:+1 555 0100" \
    --org "Acme Inc." --title "Head of Operations" \
    --account acct-acme:decision-maker:primary --group clients --birthday 04-12
.claude/bin/crm contact new "Globex" --kind org --url work:https://globex.example
```

- The quoted name is the display name (vCard FN) and the card's title. Pass
  the structured parts (`--given`, `--family`, `--prefix` …) when you know
  them; don't guess how to split a name.
- A card needs no account. Attach one (`--account`) only when the person
  works with you on that customer's behalf; mark `:primary` for the one main
  contact (only one per account).
- Birthdays without a year are `--MM-DD` (type `04-12` or `--birthday=--04-12`).

## Updating

```
.claude/bin/crm contact set    CARD-0042 title "COO"
.claude/bin/crm contact set    CARD-0042 name.family Doe-Smith
.claude/bin/crm contact add    CARD-0042 email home:jane@example.org --pref
.claude/bin/crm contact add    CARD-0042 address "label=home;street=1 Elm St;locality=Springfield;region=IL;code=62704;country=US"
.claude/bin/crm contact add    CARD-0042 handle signal:+15550100
.claude/bin/crm contact add    CARD-0042 accounts acct-globex:billing
.claude/bin/crm contact remove CARD-0042 accounts acct-acme
.claude/bin/crm contact pref   CARD-0042 phone mobile
.claude/bin/crm contact rename CARD-0042 "Jane Doe-Smith"
```

- `label:value` for emails, phones and URLs; `service:value` for handles;
  `k=v;k=v` for addresses (and for anything else when you want to be
  explicit). `remove` and `pref` take the value, the label, or `#n`.
- Notes about the person go in the card's body: edit the file, then
  `.claude/bin/crm touch CARD-0042`.

## Duplicates

```
.claude/bin/crm contact merge CARD-0042 CARD-0077
```

Confirm with the user that the two cards really are one person before you
fold them — a shared email is a hint, not proof. KEEP gets everything DROP
had that it lacked; where they disagree KEEP wins and the tool prints what it
kept (tell the user). DROP is archived with `merged_into`, and anything that
pointed at it still resolves.

## Birthdays, groups, finding

```
.claude/bin/crm birthdays --next 14
.claude/bin/crm groups
.claude/bin/crm contact list --group clients
.claude/bin/crm contact show CARD-0042
```

## Address-book files

```
.claude/bin/crm import ~/Downloads/contacts.vcf --dry-run      # look first
.claude/bin/crm import ~/Downloads/contacts.vcf
.claude/bin/crm import ~/Downloads/contacts.vcf --update       # fold into cards already here
.claude/bin/crm export --group clients --out clients.vcf
```

Always `--dry-run` an import first and show the user the summary: what would
be created, what matched an existing card, what was dropped and why. After an
import, remind them to review what came in against the privacy rails.

## Finish

Run `.claude/bin/check-crm` after a batch of changes. Report what changed
(card ids) in a line or two; don't paste whole cards back unless asked.
