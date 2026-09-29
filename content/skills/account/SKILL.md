---
name: account
description: Keep the customer accounts — add a customer or company (acct-<slug>), change its status (prospect, active, churned, or the project's own), set its tier, owner or details, list the current customers, or show an account's whole picture — its people, its leads by stage, and what else in the project names it. Writes go through .claude/bin/crm. Use for "/account", "add Acme as a customer", "who are our current customers", "mark Globex as churned", "what's going on with Acme", "who's our contact at Initech", "show me the Acme account".
---

# /account — the customer hub

An account is a customer or company; "current customers" are exactly the
accounts in the active status. This module **owns the account registry**:
when it is mounted, `crm/accounts/` is the one list of customers in the
project. Never start a second one elsewhere.

The law is `.claude/crm-rules.md` §1 and §4. What "active" and "churned"
mean here is `.claude/crm-gate.md` §3.

## Adding

```
.claude/bin/crm account new "Acme Inc." --slug acme --tier mid-market \
    --owner chazz --website https://acme.example
```

- The id is `acct-<slug>` and it is permanent: it is the file name and the
  `@acct-<slug>` handle every other module joins on. Pick a short, stable
  slug (`acme`, not `acme-inc-2026`). `crm account rename` changes the
  display name later; nothing changes the id.
- A new account starts in the first status (`prospect` by default). If it is
  already a customer, say so: `--status active --since 2019-03-01`.
- Check it doesn't exist first: `.claude/bin/crm account list`.

## Status

```
.claude/bin/crm account status acct-acme churned --note "contract not renewed"
```

- Status changes only through the tool (or `crm lead win`, which makes an
  account a customer). Each change stamps `since` and writes a history line;
  a status edited by hand is reported by `check-crm`.
- **Churn is a judgement call.** Apply the definition in
  `.claude/crm-gate.md` §3; if it doesn't settle the case, ask the user —
  don't mark a customer churned on a hunch.

## Details

```
.claude/bin/crm account set    acct-acme tier strategic
.claude/bin/crm account add    acct-acme email billing:billing@acme.example --pref
.claude/bin/crm account add    acct-acme tags renewal-2027
.claude/bin/crm account rename acct-acme "Acme Holdings"
```

The account's people are not stored on it — they are the cards that name it.
To attach a person: `.claude/bin/crm contact add CARD-0042 accounts
acct-acme:billing` (see /contact).

## The whole picture

```
.claude/bin/crm account show acct-acme
.claude/bin/crm account list --status active       # current customers
.claude/bin/crm pipeline --account acct-acme
```

`account show` lists the people (primary first), the leads by stage, and —
when the calendar, messages or notes modules are mounted — how many events,
threads and notes name the account. When asked "what's going on with X",
start there, then read the leads and threads it points to.

## Finish

Run `.claude/bin/check-crm` after changes. Report the account id and what
changed.
