# -*- coding: utf-8 -*-
"""validate.py — check-crm: every invariant in .claude/crm-rules.md, mechanically.

Family invariants F-01..F-27 come from records.py; the crm invariants
C-01..C-16 are here. Exit 0 = no errors (warnings allowed), 1 = errors,
2 = cannot run.

The per-record checks (check_one) are also what the crm tool runs on a record
before it writes it, so the tool can never write what this validator rejects.
"""

import argparse
import os
from collections import OrderedDict

from . import model as M
from . import records as R


def run(ctx, fix=False):
    report = R.Report(M.CHECK)
    if not os.path.isdir(ctx.root):
        report.error("F-15", "there is no %s/ directory here (%s)" % (M.ROOT, ctx.project),
                     fix="install rasa.module.crm with its bin/init, or pass --root")
        return report
    today = R.today()

    # ---- config ---------------------------------------------------------
    for inv, line, msg in ctx.config_problems:
        report.error(inv, msg, where=ctx.rel_root(M.CONFIG_NAME), line=line)
    cfg = ctx.settings
    actors = R.declared(cfg, "actors")

    # ---- the files ------------------------------------------------------
    records, strays = ctx.scan()
    report.records = len(records)
    if strays:
        report.info("F-27", "not records, left alone: %s" % ", ".join(
            ctx.rel_root(s) for s in strays), where=M.ROOT)

    index = R.family_index(ctx.project)
    mounted = R.mounted_modules(ctx.project)
    usable = []
    for rec in records:
        where = ctx.rel_of(rec)
        schema = ctx.schema_for(rec)
        if schema is None:
            report.error("F-03", "%s is not a crm record type (CARD, acct-, LEAD)" % rec.stem,
                         where=where)
            continue
        if not R.check_record_common(rec, schema, report, where, actors=actors, today_=today):
            continue
        if rec.prefix not in M.PREFIX_TYPE:
            continue
        usable.append(rec)
        check_one(ctx, rec, where, report, today)
        for key, ref in R.frontmatter_refs(rec, schema):
            R.check_ref(ref, index, mounted, report, where, rec.line_of(key), key=key)
        for ref, line in R.body_refs(rec):
            R.check_ref(ref, index, mounted, report, where, line, body=True)

    R.check_unique_ids(usable, report, ctx.rel_of)
    cards = [r for r in usable if r.prefix == "CARD"]
    accounts = [r for r in usable if r.prefix == "acct"]
    leads = [r for r in usable if r.prefix == "LEAD"]
    check_primaries(ctx, cards, report)
    check_merges(ctx, cards, report)
    check_duplicate_emails(ctx, cards, report)
    check_won_accounts(ctx, leads, accounts, report)

    # ---- history ----------------------------------------------------------
    rows, problems, exists = R.load_history(ctx.history_path)
    hrel = ctx.rel_root("history.tsv")
    for inv, line, msg in problems:
        report.error(inv, msg, where=hrel, line=line)
    fixes = []
    R.check_history_common(usable, rows, exists, report,
                           module_ids_ok=lambda rid: R.ref_prefix(rid) in M.PREFIX_TYPE,
                           place_of=M.Ctx.place_of, rel_of=ctx.rel_of, history_rel=hrel,
                           cli=M.CLI, fixes=fixes,
                           present_ids=R.ids_on_disk(records))
    for row in rows:
        if R.ref_prefix(row.id) not in M.PREFIX_TYPE:
            report.error("F-13", "%s does not belong to crm" % row.id, where=hrel,
                         line=row.lineno)
        if actors is not None and row.actor not in actors and row.actor != "unknown":
            report.error("F-22", "actor '%s' is not declared" % row.actor, where=hrel,
                         line=row.lineno)
    status_fixes = check_status_history(ctx, accounts, rows, report)

    # ---- digests ----------------------------------------------------------
    table, had_table = R.load_digests(ctx.root)
    fresh = R.check_digests(usable, table, report, ctx.rel_of, M.CLI,
                            is_frozen=lambda r: False, mutable_keys_of=lambda r: [],
                            today_=today)

    # ---- --fix: the mechanical subset, then re-check ------------------------
    if fix and (fixes or status_fixes):
        with ctx.lock():
            entries = []
            seen = set()
            for kind, rec in fixes:
                if rec.id in seen:
                    continue
                seen.add(rec.id)
                note = "reconciled"
                entries.append((rec.id, "reconcile", "-", M.Ctx.place_of(rec), "unknown", note))
            if not exists:
                entries.sort(key=lambda e: e[0])
            for rec, was, now in status_fixes:
                entries.append((rec.id, "reconcile", "status=" + was, "status=" + now, "unknown",
                                "reconciled"))
            ctx.log(entries)
        report.notes.append("--fix appended %d reconcile line(s) to %s" % (len(entries), hrel))
        return run(ctx, fix=False)

    if report.ok:
        if fresh != table or not had_table:
            R.save_digests(ctx.root, fresh)
            if not had_table and usable:
                report.notes.append("seeded the content cache (%s/.state/digests.tsv)" % M.ROOT)
    return report


# ---------------------------------------------------------------------------
# per-record law (also the tool's pre-write guard)
# ---------------------------------------------------------------------------

def check_one(ctx, rec, where, report, today):
    t = M.Ctx.type_of(rec)
    if t == "card":
        check_card(ctx, rec, where, report)
    elif t == "account":
        check_account(ctx, rec, where, report, today)
    elif t == "lead":
        check_lead(ctx, rec, where, report, today)


def _labels(ctx, rec, where, report, fields):
    labels = ctx.declared("labels")
    for f in fields:
        for it in M.items(rec.fm, f):
            if isinstance(it.get("label"), str):
                R.check_declared(it["label"], labels, report, "%s label" % f, where,
                                 rec.line_of(f))


def _prefs(rec, where, report, fields):
    """C-07: at most one preferred item per list field."""
    for f in fields:
        n = sum(1 for it in M.items(rec.fm, f) if M.truthy(it.get("pref")))
        if n > 1:
            report.error("C-07", "%s has %d items marked pref; at most one is preferred" % (f, n),
                         where=where, line=rec.line_of(f),
                         fix="%s contact pref %s %s <which>" % (M.CLI, rec.id, f)
                         if rec.prefix == "CARD" else None)


def check_card(ctx, rec, where, report):
    # C-01 a card lives in contacts/ (or contacts/_archive/ once archived)
    if rec.dir not in (M.CONTACTS_DIR, M.CARD_ARCHIVE_DIR):
        report.error("C-01", "a contact card lives in %s/%s/ (or %s/%s/ once archived), not in "
                             "'%s'" % (M.ROOT, M.CONTACTS_DIR, M.ROOT, M.CARD_ARCHIVE_DIR,
                                       rec.dir or "."), where=where)
    _prefs(rec, where, report, M.PREF_FIELDS)
    _labels(ctx, rec, where, report, M.LABELLED_FIELDS)
    groups = ctx.declared("groups")
    for g in M.strings(rec.fm, "groups"):
        R.check_declared(g, groups, report, "group", where, rec.line_of("groups"))
    roles = ctx.declared("contact_roles")
    seen = set()
    for it in M.items(rec.fm, "accounts"):
        if isinstance(it.get("role"), str):
            R.check_declared(it["role"], roles, report, "contact role", where,
                             rec.line_of("accounts"))
        # C-08 (local half) a card names an account once
        acct = it.get("acct")
        if acct in seen:
            report.error("C-08", "%s is listed twice in accounts; one link per account" % acct,
                         where=where, line=rec.line_of("accounts"))
        seen.add(acct)
    # C-09 a card is not related to itself
    for it in M.items(rec.fm, "related"):
        if it.get("who") == rec.id:
            report.error("C-09", "a card cannot be related to itself", where=where,
                         line=rec.line_of("related"),
                         fix="%s contact remove %s related %s" % (M.CLI, rec.id, rec.id))
    # C-10 (local half) merged_into only on an archived card
    target = rec.fm.get("merged_into")
    if isinstance(target, str):
        if not rec.archived:
            report.error("C-10", "merged_into is set on a live card; only the archived duplicate "
                                 "of a merge carries it", where=where,
                         line=rec.line_of("merged_into"))
        if target == rec.id:
            report.error("C-10", "a card cannot be merged into itself", where=where,
                         line=rec.line_of("merged_into"))


def check_account(ctx, rec, where, report, today):
    # C-01 an account lives in accounts/, never archived
    if rec.dir != M.ACCOUNTS_DIR:
        report.error("C-01", "an account lives in %s/%s/ and is never archived (its status "
                             "carries churn), not in '%s'" % (M.ROOT, M.ACCOUNTS_DIR,
                                                             rec.dir or "."), where=where)
    # C-02 the file stem IS the id
    if rec.id and rec.stem != rec.id:
        report.error("C-02", "an account's file is exactly '%s.md' — the stem is the id" % rec.id,
                     where=where)
    # C-11 the status is a declared account status
    st = rec.fm.get("status")
    if isinstance(st, str) and st not in ctx.statuses:
        report.error("C-11", "status '%s' is not an account status (%s)" % (
            st, ", ".join(ctx.statuses)), where=where, line=rec.line_of("status"),
            fix="%s account status %s <status>" % (M.CLI, rec.id))
    # C-16 since is not in the future
    since = R.parse_date(rec.fm.get("since")) if isinstance(rec.fm.get("since"), str) else None
    if since and since > today:
        report.error("C-16", "since %s is in the future (today is %s)" % (since, today),
                     where=where, line=rec.line_of("since"))
    _prefs(rec, where, report, M.PREF_FIELDS)
    _labels(ctx, rec, where, report, M.LABELLED_FIELDS)
    if isinstance(rec.fm.get("tier"), str):
        R.check_declared(rec.fm["tier"], ctx.declared("tiers"), report, "tier", where,
                         rec.line_of("tier"))
    tags = ctx.declared("tags")
    for t in M.strings(rec.fm, "tags"):
        R.check_declared(t, tags, report, "tag", where, rec.line_of("tags"))


def _date(rec, key):
    v = rec.fm.get(key)
    return R.parse_date(v) if isinstance(v, str) else None


def check_lead(ctx, rec, where, report, today):
    stage = M.Ctx.stage_of(rec)
    # C-01 a lead lives one level under leads/
    if stage is None:
        report.error("C-01", "a lead lives in %s/%s/<stage>/, not in '%s'" % (
            M.ROOT, M.LEADS_DIR, rec.dir or "."), where=where)
        return
    # C-03 the stage directory is a declared stage
    if stage not in ctx.stages:
        report.error("C-03", "'%s' is not a stage (%s); the directory is the stage" % (
            stage, ", ".join(ctx.stages)), where=where,
            fix="declare '%s' in stages, or move the file into a declared stage and run "
                "%s check --fix" % (stage, M.CLI))
        return
    created = _date(rec, "created")
    closed = _date(rec, "closed")
    terminal = stage in ctx.terminal_stages
    # C-04 closed exactly in the terminal stages
    if terminal and "closed" not in rec.fm:
        report.error("C-04", "a lead in '%s' needs 'closed' (the day it was %s)" % (
            stage, "won" if stage == ctx.won_stage else "lost"), where=where)
    if not terminal and "closed" in rec.fm:
        report.error("C-04", "'closed' on a lead in the open stage '%s'; only won and lost "
                             "leads are closed" % stage, where=where, line=rec.line_of("closed"),
                     fix="%s lead reopen %s --to %s" % (M.CLI, rec.id, stage))
    if closed and created and closed < created:
        report.error("C-04", "closed %s is earlier than created %s" % (closed, created),
                     where=where, line=rec.line_of("closed"))
    if closed and closed > today:
        report.error("C-04", "closed %s is in the future" % closed, where=where,
                     line=rec.line_of("closed"))
    # C-05 lost_reason exactly in the lost stage
    if stage == ctx.lost_stage and "lost_reason" not in rec.fm:
        report.error("C-05", "a lost lead records why: 'lost_reason' is required", where=where)
    if stage != ctx.lost_stage and "lost_reason" in rec.fm:
        report.error("C-05", "'lost_reason' on a lead that is not lost", where=where,
                     line=rec.line_of("lost_reason"))
    # C-06 qualified_on: required at/after the qualified stage (open), absent before it
    q = _date(rec, "qualified_on")
    if ctx.needs_qualification(stage) and "qualified_on" not in rec.fm:
        report.error("C-06", "a lead in '%s' (at or past '%s') must have been qualified: "
                             "'qualified_on' is missing" % (stage, ctx.qualified_stage),
                     where=where,
                     fix="%s lead advance %s --to %s --met <criteria>  (from an earlier stage)"
                         % (M.CLI, rec.id, ctx.qualified_stage))
    if ctx.before_qualified(stage) and "qualified_on" in rec.fm:
        report.error("C-06", "'qualified_on' on a lead in '%s', before '%s'" % (
            stage, ctx.qualified_stage), where=where, line=rec.line_of("qualified_on"))
    if q and created and q < created:
        report.error("C-06", "qualified_on %s is earlier than created %s" % (q, created),
                     where=where, line=rec.line_of("qualified_on"))
    if q and q > today:
        report.error("C-06", "qualified_on %s is in the future" % q, where=where,
                     line=rec.line_of("qualified_on"))
    if q and closed and q > closed:
        report.error("C-06", "qualified_on %s is after closed %s" % (q, closed), where=where,
                     line=rec.line_of("qualified_on"))
    # C-14 value and currency travel together
    if "value" in rec.fm and "currency" not in rec.fm:
        report.error("C-14", "a value needs its currency", where=where, line=rec.line_of("value"),
                     fix="%s lead set %s currency <ISO 4217 code>" % (M.CLI, rec.id))
    if "currency" in rec.fm and "value" not in rec.fm:
        report.error("C-14", "a currency with no value", where=where,
                     line=rec.line_of("currency"), fix="%s lead unset %s currency" % (M.CLI, rec.id))
    if isinstance(rec.fm.get("source"), str):
        R.check_declared(rec.fm["source"], ctx.declared("sources"), report, "source", where,
                         rec.line_of("source"))


# ---------------------------------------------------------------------------
# cross-record law
# ---------------------------------------------------------------------------

def primaries(cards, skip=None):
    """acct -> [card ids marked primary], live cards only."""
    out = OrderedDict()
    for c in cards:
        if c.archived or c.id == skip:
            continue
        for it in M.items(c.fm, "accounts"):
            if M.truthy(it.get("primary")) and isinstance(it.get("acct"), str):
                out.setdefault(it["acct"], []).append(c.id)
    return out


def check_primaries(ctx, cards, report):
    """C-08: at most one primary contact per account, across live cards."""
    by_id = {c.id: c for c in cards}
    for acct, ids in primaries(cards).items():
        if len(ids) > 1:
            report.error("C-08", "%s has %d primary contacts (%s); at most one" % (
                acct, len(ids), ", ".join(ids)), where=ctx.rel_of(by_id[ids[-1]]),
                fix="%s contact remove %s accounts %s, then %s contact add %s accounts %s:<role> "
                    "(without :primary)" % (M.CLI, ids[-1], acct, M.CLI, ids[-1], acct))


def check_merges(ctx, cards, report):
    """C-10 (cross half): merged_into names a live card."""
    by_id = {c.id: c for c in cards}
    for c in cards:
        target = c.fm.get("merged_into")
        if not isinstance(target, str) or target == c.id:
            continue
        t = by_id.get(target)
        if t is None:
            report.error("C-10", "merged_into %s: no such card" % target, where=ctx.rel_of(c),
                         line=c.line_of("merged_into"))
        elif t.archived:
            report.error("C-10", "merged_into %s, which is itself archived; a merge points at the "
                                 "live card%s" % (target, (" (%s)" % t.fm["merged_into"])
                                                  if isinstance(t.fm.get("merged_into"), str)
                                                  else ""),
                         where=ctx.rel_of(c), line=c.line_of("merged_into"))


def check_duplicate_emails(ctx, cards, report):
    """C-13 (warning): the same email on two live cards is probably one person twice."""
    seen = OrderedDict()
    for c in cards:
        if c.archived:
            continue
        for it in M.items(c.fm, "email"):
            v = (it.get("value") or "").strip().lower()
            if v:
                seen.setdefault(v, [])
                if c.id not in seen[v]:
                    seen[v].append(c.id)
    by_id = {c.id: c for c in cards}
    for email, ids in seen.items():
        if len(ids) > 1:
            report.warn("C-13", "%s is on %d live cards (%s) — the same person twice?" % (
                email, len(ids), ", ".join(ids)), where=ctx.rel_of(by_id[ids[-1]]),
                fix="%s contact merge %s %s  (if they are one person)" % (M.CLI, ids[0], ids[-1]))


def check_won_accounts(ctx, leads, accounts, report):
    """C-12 (warning): a won lead's account has not left the initial status."""
    if ctx.initial_status == ctx.active_status:
        return
    by_id = {a.id: a for a in accounts}
    for lead in leads:
        if M.Ctx.stage_of(lead) != ctx.won_stage:
            continue
        acct = by_id.get(lead.fm.get("account"))
        if acct is not None and acct.fm.get("status") == ctx.initial_status:
            report.warn("C-12", "%s was won but %s is still '%s'" % (
                lead.id, acct.id, ctx.initial_status), where=ctx.rel_of(acct),
                fix="%s account status %s %s" % (M.CLI, acct.id, ctx.active_status))


def check_status_history(ctx, accounts, rows, report):
    """C-15: an account's status is the one its history last recorded. -> fixes."""
    by_id = R.history_by_id(rows)
    fixes = []
    for a in accounts:
        st = a.fm.get("status")
        if not isinstance(st, str):
            continue
        was = M.recorded_status(by_id.get(a.id, []))
        if was is not None and was != st:
            report.error("C-15", "%s says status '%s' but its history last recorded '%s' "
                                 "(changed by hand?)" % (a.id, st, was), where=ctx.rel_of(a),
                         line=a.line_of("status"),
                         fix="%s check --fix  (records the change as a 'reconcile' line), or "
                             "put it back and use %s account status" % (M.CLI, M.CLI),
                         fixable=True)
            fixes.append((a, was, st))
    return fixes


def main(argv=None, bin_dir=None):
    def _main(argv):
        ap = argparse.ArgumentParser(prog=M.CHECK, description="Validate the crm ledger "
                                     "against .claude/crm-rules.md (records-family/1).")
        ap.add_argument("--root", help="project root (default: the project that owns this tool)")
        ap.add_argument("--fix", action="store_true",
                        help="repair the mechanical subset (history reconcile lines); never "
                             "invents a person or a date")
        ap.add_argument("--json", action="store_true", help="machine-readable report")
        ap.add_argument("--quiet", action="store_true", help="errors only")
        a = ap.parse_args(argv)
        ctx = M.Ctx(a.root, bin_dir)
        report = run(ctx, fix=a.fix)
        report.render(as_json=a.json, quiet=a.quiet)
        return report.exit_code()
    return R.run_main(_main, argv)
