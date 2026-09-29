---
name: lead
description: Work the sales funnel — capture a lead against an account, set its value, source, owner and next action, move it through the stages, qualify it against the project's declared criteria, close it as won (which makes the account a current customer) or lost (with the reason), reopen it, and show the pipeline board with value per stage. Writes go through .claude/bin/crm. Use for "/lead", "new opportunity with Acme", "move the Acme deal to proposal", "is this lead qualified", "we won Globex", "we lost Initech to a rival", "what's in the pipeline", "what's the next step on LEAD-7".
---

# /lead — the sales funnel

A lead is one opportunity against one account. Its stage is the directory it
lives in; only the tool moves it. The law is `.claude/crm-rules.md` §5–§6.
What each stage and each qualification criterion means is
`.claude/crm-gate.md` §1–§2.

## Capturing

```
.claude/bin/crm lead new "Acme — second-site rollout" --account acct-acme \
    --contact CARD-0042 --source referral --value 12000 --currency USD \
    --next "Send the revised quote" --due fri
```

- Every lead is against an account. If the customer isn't an account yet,
  add it first (/account) — don't park a lead without one.
- `--value` is an estimate that sizes the funnel, not booked revenue; it
  always carries a currency (`--currency`, or the project's
  `default_currency`).
- New leads start in the first stage.

## Moving

```
.claude/bin/crm lead advance LEAD-0007 --to contacted
.claude/bin/crm lead set     LEAD-0007 next_action "Book the site visit"
.claude/bin/crm lead set     LEAD-0007 next_action_due +1w
```

## Qualifying — the hard-stop

```
.claude/bin/crm lead advance LEAD-0007 --to qualified --met need,budget,decision-maker
```

1. If the project has not declared `qualification` in `crm/crm.config.yml`,
   the tool refuses — **and so do you**. Ask the user what makes a lead
   qualified in their business, have them declare the criteria (and describe
   each in `.claude/crm-gate.md` §1). Never invent a qualification bar.
2. Read what each criterion means in `.claude/crm-gate.md` §1, and check it
   against what you actually know about the lead. Ask the user about any
   criterion you can't confirm.
3. Assert only what is true: `--met` must name every declared criterion, and
   it is a person's statement that each one holds. If one isn't met, the lead
   isn't qualified — say which, and leave it where it is.

The tool stamps `qualified_on` and records the criteria in the history.
Moving past the qualified stage (to proposal, say) needs the same, if the
lead was never qualified.

## Closing

```
.claude/bin/crm lead win  LEAD-0007
.claude/bin/crm lead lose LEAD-0009 --reason "Chose a local supplier on price"
.claude/bin/crm lead reopen LEAD-0009 --to contacted
```

- **A deal is never won unqualified.** If the lead was never qualified, the
  win qualifies it: run `crm lead win LEAD-0007 --met a,b,c` with every
  declared criterion — after the same conversation as above. With no
  `qualification` declared, the win refuses (the hard-stop), and so do you.
- **Win** closes the lead and, in the same act, makes its account a current
  customer (unless it already is). Tell the user both happened. If
  contracts or invoices are mounted, the next step lives there — offer it.
- **Lose** needs the reason. Write it for the person who reads it in a year:
  what actually decided it, not "no response".
- Leads are never deleted; won and lost are where they end. Reopening never
  changes the account — if a win is undone, ask whether the account is still
  a customer.

## The board

```
.claude/bin/crm pipeline
.claude/bin/crm pipeline --account acct-acme --leads
.claude/bin/crm lead list --open
.claude/bin/crm lead show LEAD-0007
```

Values are summed per currency, never across currencies. When asked "what's
in the pipeline", show the board, then name the open leads whose next action
is overdue.

## Finish

Run `.claude/bin/check-crm` after changes. Report the lead ids, their new
stages, and any account that became a customer.
