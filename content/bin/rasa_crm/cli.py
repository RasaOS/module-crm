# -*- coding: utf-8 -*-
"""cli.py — `crm`, the one way to change a crm ledger.

Every write verb is one act under the ledger lock: check preconditions,
write the record(s) atomically, append the history line(s), refresh the
content cache. A refused command writes nothing (exit 1). Before writing, the
tool holds the record to the same per-record law the validator runs, so it
cannot write what check-crm would reject. The law is .claude/crm-rules.md;
this file executes it and does not redefine it.

  crm contact  new | set | unset | add | remove | pref | rename | merge |
               archive | restore | show | list | find
  crm account  new | status | set | unset | add | remove | pref | rename | show | list
  crm lead     new | advance | win | lose | reopen | set | unset | rename | show | list
  crm pipeline · birthdays · groups · import · export · touch · history · check
"""

import argparse
import calendar
import datetime as _dt
import os
import re
import sys
import uuid
from collections import OrderedDict
from decimal import Decimal, InvalidOperation

from . import fields as F
from . import model as M
from . import records as R
from . import validate as V
from . import vcard as VC


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _out(a, human, data):
    if getattr(a, "json", False):
        R.emit_json(data)
    else:
        sys.stdout.write(human if human.endswith("\n") else human + "\n")


def _note(text):
    sys.stderr.write("note: %s\n" % text)


def _title(text, what="a name"):
    t = (text or "").strip()
    if not t:
        raise R.Refusal("%s cannot be empty" % what)
    if "\n" in t:
        raise R.Refusal("%s is one line" % what)
    return t


def _today():
    return R.today().isoformat()


def _bump(fm):
    fm["updated"] = _today()
    return fm


def _copy(fm):
    """A frontmatter copy whose lists and maps can be changed without touching the original."""
    out = OrderedDict()
    for k, v in fm.items():
        if isinstance(v, list):
            out[k] = [OrderedDict(i) if isinstance(i, dict) else i for i in v]
        elif isinstance(v, dict):
            out[k] = OrderedDict(v)
        else:
            out[k] = v
    return out


def _rel(ctx, path):
    return R.rel_posix(path, ctx.project)


def _candidate(ctx, rel, fm, body, schema):
    """The record exactly as it will be read back once written."""
    text = M.render(fm, body, schema)
    lines, first, b, bfirst, _err = R.split_frontmatter(text)
    values, info, errors = R.parse_mapping(lines, first)
    rec = R.Record(ctx.abs(rel), rel)
    rec.fm, rec.info, rec.parsed, rec.body, rec.text = values, info, not errors, b, text
    rec.body_lineno = bfirst
    return rec


def _guard(ctx, rel, fm, body, schema, records=None):
    """Hold a record about to be written to the per-record law (schema + C-invariants +
    declared vocabularies) and, for a card, to the one-primary-per-account rule."""
    problems = R.schema_errors(schema, fm)
    if problems:
        inv, path, msg = problems[0]
        raise R.Refusal("%s: %s %s (%s)" % (fm.get("id"), path, msg, inv))
    rec = _candidate(ctx, rel, fm, body, schema)
    report = R.Report(M.CLI)
    V.check_one(ctx, rec, ctx.rel_root(rel), report, R.today())
    errs = [f for f in report.findings if f.severity == R.ERROR]
    if errs:
        raise R.Refusal("%s: %s (%s)" % (fm.get("id"), errs[0].msg, errs[0].inv))
    if records is not None and str(fm.get("id", "")).startswith("CARD-"):
        others = V.primaries([r for r in records if r.prefix == "CARD"], skip=fm.get("id"))
        for it in M.items(fm, "accounts"):
            if M.truthy(it.get("primary")) and others.get(it.get("acct")):
                raise R.Refusal("%s already has a primary contact (%s); take :primary off that "
                                "card first" % (it["acct"], ", ".join(others[it["acct"]])))
    return rec


def _write(ctx, rec, fm, body=None, dst_rel=None, records=None):
    """Guard, write in place, then move to dst_rel (if given). -> the new rel."""
    schema = ctx.schema_for(rec)
    body = rec.body if body is None else body
    dst_rel = dst_rel or rec.rel
    _guard(ctx, dst_rel, fm, body, schema, records=records)
    dst = ctx.abs(dst_rel)
    if dst_rel != rec.rel and os.path.exists(dst):
        raise R.Refusal("refusing to overwrite %s" % _rel(ctx, dst))
    ctx.write(rec.path, fm, body, schema, rec.info)
    if dst_rel != rec.rel:
        R.move_path(rec.path, dst)
        R.prune_empty_dirs(os.path.dirname(rec.path), ctx.root)
    ctx.refresh_digest(dst, dst_rel)
    return dst_rel


def _render(ctx, rec, fm, body=None):
    return M.render(fm, rec.body if body is None else body, ctx.schema_for(rec), rec.info)


def _ids(records):
    return [r.id for r in records if r.id]


def _live_card(ctx, records, cid, what="--contact"):
    for r in records:
        if r.id == cid and r.prefix == "CARD":
            if r.archived:
                where = r.fm.get("merged_into")
                raise R.Refusal("%s %s is archived%s" % (what, cid, (
                    "; it was merged into %s — use that" % where) if isinstance(where, str)
                    else "; restore it first"))
            return r
    raise R.Refusal("%s %s: no such contact card" % (what, cid))


def _account(ctx, records, aid, what="--account"):
    if not R.RX_ACCT_ID.match(aid or ""):
        raise R.Refusal("%s '%s' is not an account id (acct-<slug>)" % (what, aid))
    for r in records:
        if r.id == aid and r.prefix == "acct":
            return r
    raise R.Refusal("%s %s: no such account (crm account new …)" % (what, aid))


def take_flags(a, tokens, extra=()):
    """Pull --by/--root/--dry-run/--json (and `extra` switches) out of a REMAINDER list,
    so 'set CARD-0001 title "X" --by chazz' works. A --MM-DD date is a value, not a flag."""
    rest, i = [], 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("--by", "--root") and i + 1 < len(tokens):
            setattr(a, t[2:], tokens[i + 1])
            i += 2
            continue
        if t == "--dry-run":
            a.dry_run = True
        elif t == "--json":
            a.json = True
        elif t in extra:
            setattr(a, t[2:].replace("-", "_"), True)
        elif t == "--":
            rest.extend(tokens[i + 1:])
            break
        elif t.startswith("--") and len(t) > 2 and not R.RX_PARTIAL_DATE.match(t):
            raise R.Refusal("unknown option %s" % t)
        else:
            rest.append(t)
        i += 1
    return rest


def _decimal(text):
    t = (text or "").strip().replace(",", "")
    if not re.match(r"^[0-9]+(?:\.[0-9]+)?$", t):
        raise R.Refusal("value '%s' is not an amount (1200, 1200.50)" % text)
    return t


def _currency(ctx, given):
    cur = (given or ctx.settings.get("default_currency") or "").upper()
    if not cur:
        raise R.Refusal("a value needs its currency: pass --currency (USD, EUR, …) or declare "
                        "default_currency in %s" % ctx.rel_root(M.CONFIG_NAME))
    if not re.match(r"^[A-Z]{3}$", cur):
        raise R.Refusal("currency '%s' is not an ISO 4217 code (USD, EUR, …)" % given)
    return cur


def _rename_h1(rec, title):
    if rec.h1 is None:
        raise R.Refusal("%s has no H1 to rename; run %s" % (rec.id, M.CHECK))
    lines = rec.body.split("\n")
    idx = rec.h1_lineno - rec.body_lineno
    old = lines[idx][2:].strip()
    lines[idx] = "# " + title
    return old, "\n".join(lines)


# ---------------------------------------------------------------------------
# generic field editing — set / unset / add / remove / pref
# ---------------------------------------------------------------------------

EDITABLE_HINT = {
    "card": "kind, name (or name.given …), nickname, org, title, email, phone, address, url, "
            "handle, birthday, anniversary, groups, accounts, related, tz, lang, photo, uid",
    "account": "since, tier, owner, website, email, phone, address, tags",
    "lead": "account, contact, source, owner, value, currency, expected_close, next_action, "
            "next_action_due",
}


def _edit(ctx, a, want, op):
    tokens = take_flags(a, list(a.args or []), extra=("--pref",))
    if not tokens:
        raise R.Refusal("which field? (%s)" % EDITABLE_HINT[want])
    field, values = tokens[0], tokens[1:]
    need = 0 if op == "unset" else 1
    if len(values) != need:
        raise R.Refusal("%s takes %s after the field (quote a value with spaces)" % (
            op, "nothing" if need == 0 else "one value"))
    value = values[0] if values else None
    if a.pref and op != "add":
        raise R.Refusal("--pref goes with add (to move the preference, use pref)")
    ctx.require_root()
    cfg = ctx.usable_config()
    actor = R.resolve_actor(a.by, cfg)
    with ctx.lock():
        records, _ = ctx.scan()
        rec = ctx.find(a.id, want)
        if rec.archived:
            raise R.Refusal("%s is archived; restore it first" % rec.id)
        schema = ctx.schema_for(rec)
        base, _dot, part = field.partition(".")
        if base in F.PROTECTED[want]:
            raise R.Refusal("%s cannot be edited: %s" % (base, F.PROTECTED_WHY.get(base, "")))
        kind = F.field_kind(schema, base)
        if kind is None:
            raise R.Refusal("'%s' is not a %s field (%s)" % (base, M.TYPE_WORD[want],
                                                            EDITABLE_HINT[want]))
        if part and kind != "map":
            raise R.Refusal("'%s' has no parts" % base)
        fm = _copy(rec.fm)
        note = ""
        if op == "set":
            note = _op_set(ctx, records, rec, fm, want, base, part, kind, value, schema)
        elif op == "unset":
            note = _op_unset(fm, want, base, part, kind)
        elif op == "add":
            note = _op_add(ctx, records, rec, fm, want, base, kind, value, schema, a.pref)
        elif op == "remove":
            note = _op_remove(fm, base, kind, value)
        else:
            note = _op_pref(fm, base, kind, value)
        _bump(fm)
        if a.dry_run:
            _guard(ctx, rec.rel, fm, rec.body, schema, records=records)
            _out(a, _render(ctx, rec, fm), {"dry_run": True, "id": rec.id})
            return 0
        _write(ctx, rec, fm, records=records)
        ctx.log([(rec.id, op, "-", "-", actor, note)])
    _out(a, "%s  %s" % (rec.id, note), {"id": rec.id, "op": op, "field": field, "note": note})
    return 0


def _op_set(ctx, records, rec, fm, want, base, part, kind, value, schema):
    if kind in ("list", "items"):
        raise R.Refusal("%s is a list: use add and remove" % base)
    if kind == "map":
        name = OrderedDict(fm.get(base) or {})
        parts = list(((schema["properties"][base]).get("properties") or {}).keys())
        if part:
            if part not in parts:
                raise R.Refusal("%s has the parts %s" % (base, ", ".join(parts)))
            name[part] = value.strip()
        else:
            name = F.parse_kv(value)
            bad = [k for k in name if k not in parts]
            if bad:
                raise R.Refusal("%s has the parts %s (not %s)" % (base, ", ".join(parts),
                                                                  ", ".join(bad)))
        fm[base] = OrderedDict((k, name[k]) for k in parts if k in name)
        return "%s=%s" % (field_label(base, part), value.strip())
    v = F.normalize_scalar(want, base, value)
    if want == "lead" and base == "value":
        v = _decimal(value)
        if "currency" not in fm:
            fm["currency"] = _currency(ctx, None)
    if want == "lead" and base == "currency" and "value" not in fm:
        raise R.Refusal("a currency with no value says nothing; set the value first")
    if want == "lead" and base == "contact":
        _live_card(ctx, records, v, "contact")
    if want == "lead" and base == "account":
        _account(ctx, records, v, "account")
    if v is None:
        fm.pop(base, None)
    else:
        fm[base] = v
    return "%s=%s" % (base, v if v is not None else value.strip())


def field_label(base, part):
    return "%s.%s" % (base, part) if part else base


def _op_unset(fm, want, base, part, kind):
    if kind == "map" and part:
        m = OrderedDict(fm.get(base) or {})
        if part not in m:
            raise R.Refusal("%s.%s is not set" % (base, part))
        m.pop(part)
        if m:
            fm[base] = m
        else:
            fm.pop(base)
        return "%s.%s" % (base, part)
    if base not in fm:
        raise R.Refusal("%s is not set" % base)
    if want == "lead" and base == "currency" and "value" in fm:
        raise R.Refusal("the value needs its currency; unset the value (both go)")
    if want == "lead" and base == "next_action" and "next_action_due" in fm:
        raise R.Refusal("next_action_due needs a next_action; unset next_action_due first")
    fm.pop(base)
    if want == "lead" and base == "value":
        fm.pop("currency", None)
        return "value (and its currency)"
    return base


def _op_add(ctx, records, rec, fm, want, base, kind, value, schema, pref):
    if kind == "list":
        v = value.strip().lower() if base in ("groups", "tags") else value.strip()
        cur = list(M.strings(fm, base))
        if v in cur:
            raise R.Refusal("%s already has %s %s" % (rec.id, base, v))
        fm[base] = cur + [v]
        return "%s +%s" % (base, v)
    if kind != "items":
        raise R.Refusal("%s is not a list: use set" % base)
    item = F.check_item(schema, base, F.parse_item(base, value, pref=pref))
    cur = [OrderedDict(i) for i in M.items(fm, base)]
    if any(F.identity(base, i) == F.identity(base, item) for i in cur):
        raise R.Refusal("%s already has %s %s" % (rec.id, base, F.shorthand(base, item)))
    if base == "accounts":
        _account(ctx, records, item["acct"], "accounts")
    if base == "related":
        if item["who"] == rec.id:
            raise R.Refusal("a card cannot be related to itself (C-09)")
        _live_card(ctx, records, item["who"], "related")
    if M.truthy(item.get("pref")):
        for i in cur:
            i.pop("pref", None)
    fm[base] = cur + [item]
    return "%s +%s%s" % (base, F.shorthand(base, item), " (pref)" if pref else "")


def _op_remove(fm, base, kind, value):
    if kind == "list":
        cur = list(M.strings(fm, base))
        if value not in cur:
            raise R.Refusal("%s has no %s" % (base, value))
        cur.remove(value)
        if cur:
            fm[base] = cur
        else:
            fm.pop(base, None)
        return "%s -%s" % (base, value)
    if kind != "items":
        raise R.Refusal("%s is not a list: use unset" % base)
    cur = [OrderedDict(i) for i in M.items(fm, base)]
    hits = F.match(base, cur, value)
    if not hits:
        raise R.Refusal("no %s matches '%s' (%s)" % (base, value, ", ".join(
            "#%d %s" % (n + 1, F.shorthand(base, i)) for n, i in enumerate(cur)) or "none"))
    if len(hits) > 1:
        raise R.Refusal("'%s' matches %d %s items (%s); name one, or use #n" % (
            value, len(hits), base, ", ".join("#%d %s" % (n + 1, F.shorthand(base, cur[n]))
                                              for n in hits)))
    gone = cur.pop(hits[0])
    if cur:
        fm[base] = cur
    else:
        fm.pop(base, None)
    return "%s -%s" % (base, F.shorthand(base, gone))


def _op_pref(fm, base, kind, value):
    if base not in M.PREF_FIELDS:
        raise R.Refusal("pref applies to %s" % ", ".join(M.PREF_FIELDS))
    cur = [OrderedDict(i) for i in M.items(fm, base)]
    hits = F.match(base, cur, value)
    if len(hits) != 1:
        raise R.Refusal("'%s' must name exactly one %s item (%s)" % (value, base, ", ".join(
            "#%d %s" % (n + 1, F.shorthand(base, i)) for n, i in enumerate(cur)) or "none"))
    for n, i in enumerate(cur):
        if n == hits[0]:
            i["pref"] = "true"
        else:
            i.pop("pref", None)
    fm[base] = cur
    return "%s pref %s" % (base, F.shorthand(base, cur[hits[0]]))


# ---------------------------------------------------------------------------
# contacts
# ---------------------------------------------------------------------------

def cmd_contact_new(ctx, a):
    ctx.require_root()
    cfg = ctx.usable_config()
    actor = R.resolve_actor(a.by, cfg)
    fn = _title(a.name, "a name")
    schema = ctx.schemas["card"]
    fields = OrderedDict()
    if a.kind:
        k = F.normalize_scalar("card", "kind", a.kind)
        if k:
            fields["kind"] = k
    name = OrderedDict((k, getattr(a, k).strip()) for k in
                       ("prefix", "given", "additional", "family", "suffix") if getattr(a, k))
    if name:
        fields["name"] = name
    if a.nickname:
        fields["nickname"] = list(OrderedDict.fromkeys(n.strip() for n in a.nickname))
    for key in ("org", "title"):
        if getattr(a, key):
            fields[key] = getattr(a, key).strip()
    for field, given in (("email", a.email), ("phone", a.phone), ("address", a.address),
                         ("url", a.url), ("handle", a.handle), ("accounts", a.account),
                         ("related", a.related)):
        items = []
        for text in given or []:
            it = F.check_item(schema, field, F.parse_item(field, text))
            if any(F.identity(field, i) == F.identity(field, it) for i in items):
                raise R.Refusal("%s %s is given twice" % (field, F.shorthand(field, it)))
            items.append(it)
        if items:
            fields[field] = items
    for key in ("birthday", "anniversary", "tz", "lang", "photo"):
        if getattr(a, key):
            fields[key] = F.normalize_scalar("card", key, getattr(a, key))
    if a.group:
        fields["groups"] = list(OrderedDict.fromkeys(g.strip().lower() for g in a.group))
    text = R.read_text_arg(a.body, a.body_file, a.stdin)
    with ctx.lock():
        rows = ctx.history()
        records, _ = ctx.scan()
        for it in fields.get("accounts", []):
            _account(ctx, records, it["acct"], "--account")
        for it in fields.get("related", []):
            _live_card(ctx, records, it["who"], "--related")
        rid = R.format_id("CARD", R.next_number("CARD", _ids(records), rows))
        today = _today()
        fm = OrderedDict([("id", rid), ("created", today), ("created_by", actor),
                          ("updated", today)])
        fm.update(fields)
        fm["uid"] = "urn:uuid:%s" % uuid.uuid4()
        rel = "%s/%s-%s.md" % (M.CONTACTS_DIR, rid, R.slugify(fn))
        body = R.new_body(fn, text)
        _guard(ctx, rel, fm, body, schema, records=records)
        dups = _email_owners(records, fm, rid)
        if a.dry_run:
            _out(a, "would create %s\n%s" % (ctx.rel_root(rel), M.render(fm, body, schema)),
                 {"dry_run": True, "id": rid, "path": ctx.rel_root(rel)})
            return 0
        path = ctx.abs(rel)
        ctx.write(path, fm, body, schema)
        ctx.log([(rid, "new", "-", M.CONTACTS_DIR, actor, "")])
        ctx.refresh_digest(path, rel)
    for email, owners in dups.items():
        _note("%s is also on %s — the same person? (%s contact merge %s %s)" % (
            email, ", ".join(owners), M.CLI, owners[0], rid))
    _out(a, "%s  %s" % (rid, ctx.rel_root(rel)), {"id": rid, "path": ctx.rel_root(rel)})
    return 0


def _email_owners(records, fm, rid):
    mine = set((i.get("value") or "").lower() for i in M.items(fm, "email"))
    out = OrderedDict()
    for r in records:
        if r.prefix != "CARD" or r.archived or r.id == rid:
            continue
        for i in M.items(r.fm, "email"):
            v = (i.get("value") or "").lower()
            if v in mine:
                out.setdefault(v, []).append(r.id)
    return out


def cmd_rename(ctx, a, want):
    ctx.require_root()
    actor = R.resolve_actor(a.by, ctx.usable_config())
    title = _title(a.title, "a name" if want != "lead" else "a title")
    with ctx.lock():
        records, _ = ctx.scan()
        rec = ctx.find(a.id, want)
        if rec.archived:
            raise R.Refusal("%s is archived; restore it first" % rec.id)
        old, body = _rename_h1(rec, title)
        if old == title:
            raise R.Refusal("%s is already called %r" % (rec.id, title))
        fm = _bump(_copy(rec.fm))
        if want == "account":
            dst_rel = rec.rel        # the stem is the id; only the display name changes
        else:
            dst_rel = "%s/%s-%s.md" % (rec.dir, rec.id, R.slugify(title))
        if a.dry_run:
            _guard(ctx, dst_rel, fm, body, ctx.schema_for(rec))
            _out(a, "would rename %s: %r -> %r (%s)" % (rec.id, old, title,
                                                        ctx.rel_root(dst_rel)), {"dry_run": True})
            return 0
        _write(ctx, rec, fm, body, dst_rel, records=records)
        ctx.log([(rec.id, "rename", "-", "-", actor, "%s -> %s" % (old, title))])
    _out(a, "%s  %s" % (rec.id, title), {"id": rec.id, "name": title})
    return 0


def _fold(schema, dst, incoming, self_id):
    """Fold the fields of `incoming` into frontmatter `dst` (in place): fill what is missing,
    union the lists, never overwrite. -> (changes, conflicts) in words."""
    changes, conflicts = [], []
    for key, val in incoming.items():
        kind = F.field_kind(schema, key)
        if kind is None or key in ("id", "created", "created_by", "updated", "merged_into"):
            continue
        if kind == "scalar":
            if key not in dst:
                dst[key] = val
                changes.append("+%s" % key)
            elif dst[key] != val:
                conflicts.append("kept %s %r (the other says %r)" % (key, dst[key], val))
        elif kind == "map":
            m = OrderedDict(dst.get(key) or {})
            for part, pv in (val or {}).items():
                if part not in m:
                    m[part] = pv
                    changes.append("+%s.%s" % (key, part))
                elif m[part] != pv:
                    conflicts.append("kept %s.%s %r (the other says %r)" % (key, part, m[part], pv))
            order = list(((schema["properties"][key]).get("properties") or {}).keys())
            if m:
                dst[key] = OrderedDict((k, m[k]) for k in order if k in m)
        elif kind == "list":
            cur = list(M.strings(dst, key))
            for v in val or []:
                if v not in cur:
                    cur.append(v)
                    changes.append("+%s %s" % (key, v))
            if cur:
                dst[key] = cur
        else:
            cur = [OrderedDict(i) for i in M.items(dst, key)]
            has_pref = any(M.truthy(i.get("pref")) for i in cur)
            for it in val or []:
                it = OrderedDict(it)
                if key == "related" and it.get("who") == self_id:
                    continue
                same = [i for i in cur if F.identity(key, i) == F.identity(key, it)]
                if same:
                    if key == "accounts" and M.truthy(it.get("primary")) and \
                            not M.truthy(same[0].get("primary")):
                        same[0]["primary"] = "true"
                        changes.append("accounts %s now primary" % it.get("acct"))
                    continue
                if M.truthy(it.get("pref")):
                    if has_pref:
                        it.pop("pref")
                    has_pref = True
                cur.append(it)
                changes.append("+%s %s" % (key, F.shorthand(key, it)))
            if cur:
                dst[key] = cur
    return changes, conflicts


def cmd_contact_merge(ctx, a):
    ctx.require_root()
    actor = R.resolve_actor(a.by, ctx.usable_config())
    if a.keep == a.drop:
        raise R.Refusal("a card cannot absorb itself")
    with ctx.lock():
        records, _ = ctx.scan()
        keep = ctx.find(a.keep, "card")
        drop = ctx.find(a.drop, "card")
        for r in (keep, drop):
            if r.archived:
                raise R.Refusal("%s is archived; only live cards are combined" % r.id)
        schema = ctx.schemas["card"]
        kfm = _copy(keep.fm)
        theirs = _copy(drop.fm)
        theirs.pop("uid", None)      # each card keeps its own UID; DROP's still resolves to KEEP
        # KEEP takes over DROP's primary links; DROP leaves the live set in the same act
        changes, conflicts = _fold(schema, kfm, theirs, keep.id)
        kbody = keep.body
        dtext = VC.body_text(drop)
        if dtext and dtext not in keep.body:
            kbody = keep.body.rstrip("\n") + "\n\nFrom [[%s]] (%s):\n\n%s\n" % (
                drop.id, drop.h1 or drop.id, dtext)
            changes.append("+notes")
        _bump(kfm)
        dfm = _bump(_copy(drop.fm))
        dfm["merged_into"] = keep.id
        drop_rel = "%s/%s" % (M.CARD_ARCHIVE_DIR, drop.name)
        rest = [r for r in records if r.id != drop.id]
        if a.dry_run:
            _guard(ctx, keep.rel, kfm, kbody, schema, records=rest)
            _guard(ctx, drop_rel, dfm, drop.body, schema)
            _out(a, "would fold %s into %s (%s)%s" % (
                drop.id, keep.id, ", ".join(changes) or "nothing new",
                "".join("\n  %s" % c for c in conflicts)), {"dry_run": True})
            return 0
        _write(ctx, drop, dfm, dst_rel=drop_rel)
        _write(ctx, keep, kfm, kbody, records=rest)
        ctx.log([(keep.id, "merge", "-", "-", actor, "absorbed %s" % drop.id),
                 (drop.id, "merge", M.CONTACTS_DIR, M.CARD_ARCHIVE_DIR, actor,
                  "merged into %s" % keep.id)])
    msg = "%s  absorbed %s (%s); %s archived with merged_into: %s" % (
        keep.id, drop.id, ", ".join(changes) or "nothing new", drop.id, keep.id)
    for c in conflicts:
        msg += "\n  %s" % c
    _out(a, msg, {"keep": keep.id, "drop": drop.id, "changes": changes, "conflicts": conflicts})
    return 0


def cmd_contact_archive(ctx, a, restore=False):
    ctx.require_root()
    actor = R.resolve_actor(a.by, ctx.usable_config())
    with ctx.lock():
        records, _ = ctx.scan()
        rec = ctx.find(a.id, "card")
        if restore != rec.archived:
            raise R.Refusal("%s is %s" % (rec.id, "not archived" if restore else "already archived"))
        fm = None
        if restore:
            target = rec.fm.get("merged_into")
            if isinstance(target, str) and not a.unmerge:
                raise R.Refusal("%s was merged into %s; restoring it would bring back a duplicate. "
                                "If the merge was a mistake, pass --unmerge" % (rec.id, target))
            if isinstance(target, str):
                fm = _bump(_copy(rec.fm))
                fm.pop("merged_into")
            src_dir, dst_dir = M.CARD_ARCHIVE_DIR, M.CONTACTS_DIR
        else:
            src_dir, dst_dir = M.CONTACTS_DIR, M.CARD_ARCHIVE_DIR
        dst_rel = "%s/%s" % (dst_dir, rec.name)
        if a.dry_run:
            _out(a, "would %s %s: %s -> %s" % ("restore" if restore else "archive", rec.id,
                                                src_dir, dst_dir), {"dry_run": True})
            return 0
        if fm is not None:
            _write(ctx, rec, fm, dst_rel=dst_rel, records=records)
        else:
            _guard(ctx, dst_rel, rec.fm, rec.body, ctx.schemas["card"],
                   records=records if restore else None)
            R.move_path(rec.path, ctx.abs(dst_rel))
        note = a.note or ("unmerged from %s" % rec.fm.get("merged_into") if fm is not None else "")
        ctx.log([(rec.id, "restore" if restore else "archive", rec.dir, dst_dir, actor, note)])
    _out(a, "%s  %s -> %s" % (rec.id, rec.dir, dst_dir), {"id": rec.id, "to": dst_dir})
    return 0


def _card_row(rec):
    fm = rec.fm
    email = next((i["value"] for i in M.items(fm, "email") if M.truthy(i.get("pref"))), None) \
        or next((i.get("value") for i in M.items(fm, "email")), "")
    phone = next((i["value"] for i in M.items(fm, "phone") if M.truthy(i.get("pref"))), None) \
        or next((i.get("value") for i in M.items(fm, "phone")), "")
    return [rec.id, rec.h1 or "", fm.get("org") or "", email or "", phone or "",
            ",".join(M.strings(fm, "groups"))]


def _sort_name(rec):
    name = rec.fm.get("name") if isinstance(rec.fm.get("name"), dict) else {}
    return ((name.get("family") or rec.h1 or "").casefold(), (rec.h1 or "").casefold())


def cmd_contact_list(ctx, a):
    ctx.require_root()
    records, _ = ctx.scan()
    cards = [r for r in records if r.prefix == "CARD" and r.parsed]
    if a.archived:
        cards = [r for r in cards if r.archived]
    elif not a.all:
        cards = [r for r in cards if not r.archived]
    if a.group:
        cards = [r for r in cards if a.group in M.strings(r.fm, "groups")]
    if a.account:
        cards = [r for r in cards if any(i.get("acct") == a.account
                                         for i in M.items(r.fm, "accounts"))]
    if a.org:
        cards = [r for r in cards if (r.fm.get("org") or "").lower() == a.org.lower()]
    cards.sort(key=_sort_name)
    if a.json:
        R.emit_json([M.summary(r) for r in cards])
        return 0
    if not cards:
        print("(no contacts)")
        return 0
    R.table([_card_row(r) for r in cards], ["id", "name", "org", "email", "phone", "groups"])
    return 0


def cmd_contact_find(ctx, a):
    ctx.require_root()
    q = " ".join(a.text).strip().lower()
    if not q:
        raise R.Refusal("find what?")
    digits = re.sub(r"\D", "", q)
    records, _ = ctx.scan()
    hits = []
    for r in records:
        if r.prefix != "CARD" or not r.parsed or (r.archived and not a.all):
            continue
        fm = r.fm
        hay = [r.h1 or "", fm.get("org") or "", fm.get("title") or ""]
        hay += M.strings(fm, "nickname") + M.strings(fm, "groups")
        if isinstance(fm.get("name"), dict):
            hay += list(fm["name"].values())
        hay += [i.get("value", "") for f in ("email", "url", "handle") for i in M.items(fm, f)]
        text_hit = any(q in (h or "").lower() for h in hay)
        phone_hit = len(digits) >= 3 and any(
            digits in re.sub(r"\D", "", i.get("value", "")) for i in M.items(fm, "phone"))
        if text_hit or phone_hit:
            hits.append(r)
    hits.sort(key=_sort_name)
    if a.json:
        R.emit_json([M.summary(r) for r in hits])
        return 0
    if not hits:
        print("(no contact matches %r)" % q)
        return 0
    R.table([_card_row(r) for r in hits], ["id", "name", "org", "email", "phone", "groups"])
    return 0


def cmd_contact_show(ctx, a):
    ctx.require_root()
    rec = ctx.find(a.id, "card")
    records, _ = ctx.scan()
    by_id = {r.id: r for r in records}
    target = rec.fm.get("merged_into")
    leads = [r for r in records if r.prefix == "LEAD" and r.fm.get("contact") == rec.id]
    if a.json:
        d = M.summary(rec)
        d["body"] = rec.body
        if isinstance(target, str):
            d["now"] = target
        d["leads"] = [OrderedDict([("id", l.id), ("stage", M.Ctx.stage_of(l)), ("title", l.h1)])
                      for l in leads]
        R.emit_json(d)
        return 0
    if isinstance(target, str):
        t = by_id.get(target)
        print("%s was merged into %s — %s (%s)\n" % (rec.id, target, t.h1 if t else "?",
                                                     ctx.rel_of(t) if t else "missing"))
    sys.stdout.write("%s\n\n%s" % (ctx.rel_of(rec), rec.text))
    for it in M.items(rec.fm, "accounts"):
        acct = by_id.get(it.get("acct"))
        print("account: %s — %s%s%s" % (it.get("acct"), acct.h1 if acct else "(missing)",
                                        (", " + it["role"]) if it.get("role") else "",
                                        " (primary)" if M.truthy(it.get("primary")) else ""))
    for l in leads:
        print("lead:    %s  %s  %s" % (l.id, M.Ctx.stage_of(l), l.h1 or ""))
    return 0


# ---------------------------------------------------------------------------
# accounts
# ---------------------------------------------------------------------------

def _status(ctx, status):
    s = (status or "").strip().lower()
    if s not in ctx.statuses:
        raise R.Refusal("status '%s' is not an account status (%s)" % (status,
                                                                       ", ".join(ctx.statuses)))
    return s


def _since(text):
    d = R.resolve_day(text)
    if d > R.today():
        raise R.Refusal("since %s is in the future" % d)
    return d.isoformat()


def cmd_account_new(ctx, a):
    ctx.require_root()
    cfg = ctx.usable_config()
    actor = R.resolve_actor(a.by, cfg)
    name = _title(a.name, "a name")
    slug = (a.slug or R.slugify(name)).strip().lower()
    if not R.RX_SLUG.match(slug) or len(slug) > 60:
        raise R.Refusal("slug '%s' must be lower-case words joined by '-', at most 60 characters"
                        % slug)
    aid = "acct-" + slug
    status = _status(ctx, a.status or ctx.initial_status)
    schema = ctx.schemas["account"]
    fields = OrderedDict([("status", status), ("since", _since(a.since or "today"))])
    for key in ("tier", "owner", "website"):
        if getattr(a, key):
            fields[key] = F.normalize_scalar("account", key, getattr(a, key))
    for field, given in (("email", a.email), ("phone", a.phone), ("address", a.address)):
        items = []
        for text in given or []:
            it = F.check_item(schema, field, F.parse_item(field, text))
            if any(F.identity(field, i) == F.identity(field, it) for i in items):
                raise R.Refusal("%s %s is given twice" % (field, F.shorthand(field, it)))
            items.append(it)
        if items:
            fields[field] = items
    if a.tag:
        fields["tags"] = list(OrderedDict.fromkeys(t.strip().lower() for t in a.tag))
    text = R.read_text_arg(a.body, a.body_file, a.stdin)
    with ctx.lock():
        rows = ctx.history()
        records, _ = ctx.scan()
        if aid in _ids(records):
            raise R.Refusal("%s already exists; pass --slug for a different account" % aid)
        if any(r.id == aid for r in rows):
            raise R.Refusal("%s was used before (see %s history %s); ids are never reissued — "
                            "pass --slug" % (aid, M.CLI, aid))
        today = _today()
        fm = OrderedDict([("id", aid), ("created", today), ("created_by", actor),
                          ("updated", today)])
        fm.update(fields)
        rel = "%s/%s.md" % (M.ACCOUNTS_DIR, aid)
        body = R.new_body(name, text)
        _guard(ctx, rel, fm, body, schema)
        if a.dry_run:
            _out(a, "would create %s\n%s" % (ctx.rel_root(rel), M.render(fm, body, schema)),
                 {"dry_run": True, "id": aid})
            return 0
        path = ctx.abs(rel)
        ctx.write(path, fm, body, schema)
        ctx.log([(aid, "new", "-", M.ACCOUNTS_DIR, actor, "status=%s" % status)])
        ctx.refresh_digest(path, rel)
    _out(a, "%s  %s" % (aid, ctx.rel_root(rel)), {"id": aid, "path": ctx.rel_root(rel)})
    return 0


def cmd_account_status(ctx, a):
    ctx.require_root()
    actor = R.resolve_actor(a.by, ctx.usable_config())
    status = _status(ctx, a.status)
    with ctx.lock():
        rec = ctx.find(a.id, "account")
        old = rec.fm.get("status")
        if old == status:
            raise R.Refusal("%s is already %s (since %s)" % (rec.id, status,
                                                            rec.fm.get("since", "?")))
        fm = _bump(_copy(rec.fm))
        fm["status"] = status
        fm["since"] = _since(a.since or "today")
        if a.dry_run:
            _guard(ctx, rec.rel, fm, rec.body, ctx.schema_for(rec))
            _out(a, _render(ctx, rec, fm), {"dry_run": True})
            return 0
        _write(ctx, rec, fm)
        ctx.log([(rec.id, "status", "status=%s" % old, "status=%s" % status, actor,
                  a.note or "")])
    _out(a, "%s  %s -> %s" % (rec.id, old, status), {"id": rec.id, "from": old, "to": status})
    return 0


def _account_view(ctx, rec, records):
    cards = [r for r in records if r.prefix == "CARD" and r.parsed and not r.archived]
    contacts = []
    for c in cards:
        for it in M.items(c.fm, "accounts"):
            if it.get("acct") == rec.id:
                contacts.append(OrderedDict([("id", c.id), ("name", c.h1),
                                             ("role", it.get("role")),
                                             ("primary", M.truthy(it.get("primary")))]))
    contacts.sort(key=lambda c: (not c["primary"], (c["name"] or "").casefold()))
    leads = OrderedDict((s, []) for s in ctx.stages)
    for l in records:
        if l.prefix == "LEAD" and l.parsed and l.fm.get("account") == rec.id:
            st = M.Ctx.stage_of(l) or "?"
            leads.setdefault(st, []).append(OrderedDict([
                ("id", l.id), ("title", l.h1), ("value", l.fm.get("value")),
                ("currency", l.fm.get("currency"))]))
    elsewhere = OrderedDict()
    mounted = R.mounted_modules(ctx.project)
    back = R.find_backlinks(ctx.project, rec.id, exclude_path=rec.path)
    for module, what in (("schedule", "events"), ("messages", "threads"), ("notes", "notes")):
        if module not in mounted:
            elsewhere[module] = None
            continue
        paths = set(p for m, p, _ln, _l in back if m == module)
        if module == "messages":
            n = len(set(m.group(0) for m in (re.search(r"THR-[0-9]{4,}", p) for p in paths) if m))
        else:
            n = len(paths)
        elsewhere[module] = OrderedDict([("what", what), ("count", n)])
    return contacts, OrderedDict((k, v) for k, v in leads.items() if v), elsewhere


def cmd_account_show(ctx, a):
    ctx.require_root()
    rec = ctx.find(a.id, "account")
    records, _ = ctx.scan()
    contacts, leads, elsewhere = _account_view(ctx, rec, records)
    if a.json:
        d = M.summary(rec)
        d["body"] = rec.body
        d["contacts"] = contacts
        d["leads"] = leads
        d["elsewhere"] = elsewhere
        R.emit_json(d)
        return 0
    fm = rec.fm
    print("%s — %s" % (rec.id, rec.h1 or ""))
    print("status: %s%s%s%s" % (fm.get("status", "?"),
                                (" since %s" % fm["since"]) if fm.get("since") else "",
                                ("   tier: %s" % fm["tier"]) if fm.get("tier") else "",
                                ("   owner: %s" % fm["owner"]) if fm.get("owner") else ""))
    print("\ncontacts:")
    for c in contacts:
        print("  %-10s %s%s%s" % (c["id"], c["name"] or "", (", " + c["role"]) if c["role"] else "",
                                  "  (primary)" if c["primary"] else ""))
    if not contacts:
        print("  (none)")
    print("\nleads:")
    for st, ls in leads.items():
        for l in ls:
            print("  %-10s %-10s %s%s" % (st, l["id"], l["title"] or "",
                                          ("  %s %s" % (l["value"], l["currency"] or ""))
                                          if l["value"] else ""))
    if not leads:
        print("  (none)")
    print("\nelsewhere in the family (read-only):")
    for module, v in elsewhere.items():
        print("  %-9s %s" % (module, "not mounted" if v is None else "%d %s" % (v["count"],
                                                                               v["what"])))
    return 0


def cmd_account_list(ctx, a):
    ctx.require_root()
    records, _ = ctx.scan()
    accts = [r for r in records if r.prefix == "acct" and r.parsed]
    if a.status:
        accts = [r for r in accts if r.fm.get("status") == a.status]
    counts = {}
    for c in records:
        if c.prefix == "CARD" and not c.archived:
            for it in M.items(c.fm, "accounts"):
                counts.setdefault(it.get("acct"), [0, 0])[0] += 1
    for l in records:
        if l.prefix == "LEAD" and M.Ctx.stage_of(l) in ctx.open_stages:
            counts.setdefault(l.fm.get("account"), [0, 0])[1] += 1
    order = {s: i for i, s in enumerate(ctx.statuses)}
    accts.sort(key=lambda r: (order.get(r.fm.get("status"), 99), (r.h1 or "").casefold()))
    if a.json:
        R.emit_json([M.summary(r) for r in accts])
        return 0
    if not accts:
        print("(no accounts)")
        return 0
    R.table([[r.id, r.h1 or "", r.fm.get("status", ""), r.fm.get("since", ""),
              r.fm.get("tier", ""), counts.get(r.id, [0, 0])[0], counts.get(r.id, [0, 0])[1]]
             for r in accts], ["id", "name", "status", "since", "tier", "contacts", "open leads"])
    return 0


# ---------------------------------------------------------------------------
# leads
# ---------------------------------------------------------------------------

def cmd_lead_new(ctx, a):
    ctx.require_root()
    cfg = ctx.usable_config()
    actor = R.resolve_actor(a.by, cfg)
    title = _title(a.title, "a title")
    schema = ctx.schemas["lead"]
    fields = OrderedDict([("account", a.account)])
    if a.contact:
        fields["contact"] = a.contact
    if a.source:
        fields["source"] = a.source.strip().lower()
    if a.owner:
        fields["owner"] = a.owner
    if a.value is not None:
        fields["value"] = _decimal(a.value)
        fields["currency"] = _currency(ctx, a.currency)
    elif a.currency:
        raise R.Refusal("--currency without --value says nothing")
    if a.expected_close:
        fields["expected_close"] = R.resolve_day(a.expected_close).isoformat()
    if a.next:
        fields["next_action"] = _title(a.next, "the next action")
    if a.due:
        if not a.next:
            raise R.Refusal("--due is when the --next action is due; give --next too")
        fields["next_action_due"] = R.resolve_day(a.due).isoformat()
    text = R.read_text_arg(a.body, a.body_file, a.stdin)
    stage = ctx.first_stage
    with ctx.lock():
        rows = ctx.history()
        records, _ = ctx.scan()
        _account(ctx, records, a.account)
        if a.contact:
            _live_card(ctx, records, a.contact)
        rid = R.format_id("LEAD", R.next_number("LEAD", _ids(records), rows))
        today = _today()
        fm = OrderedDict([("id", rid), ("created", today), ("created_by", actor),
                          ("updated", today)])
        fm.update(fields)
        rel = "%s/%s/%s-%s.md" % (M.LEADS_DIR, stage, rid, R.slugify(title))
        body = R.new_body(title, text)
        _guard(ctx, rel, fm, body, schema)
        if a.dry_run:
            _out(a, "would create %s\n%s" % (ctx.rel_root(rel), M.render(fm, body, schema)),
                 {"dry_run": True, "id": rid})
            return 0
        path = ctx.abs(rel)
        ctx.write(path, fm, body, schema)
        ctx.log([(rid, "new", "-", M.Ctx.stage_place(stage), actor, "")])
        ctx.refresh_digest(path, rel)
    _out(a, "%s  %s" % (rid, ctx.rel_root(rel)), {"id": rid, "path": ctx.rel_root(rel),
                                                  "stage": stage})
    return 0


def _qualify(ctx, rec, fm, target, met_text):
    """Apply the qualification law for a move to `target`. -> history note."""
    met = [m.strip().lower() for m in (met_text or "").split(",") if m.strip()]
    if ctx.needs_qualification(target) and "qualified_on" not in fm:
        crit = ctx.qualification
        if crit is None:
            raise R.Refusal(
                "HARD-STOP: this project has not declared what 'qualified' means. Declare the "
                "criteria as `qualification` in %s (what each one means goes in "
                ".claude/crm-gate.md). Guessing it is the one inference this module refuses to "
                "make." % ctx.rel_root(M.CONFIG_NAME))
        unknown = [m for m in met if m not in crit]
        if unknown:
            raise R.Refusal("not qualification criteria here: %s (declared: %s)" % (
                ", ".join(unknown), ", ".join(crit)))
        missing = [c for c in crit if c not in met]
        if missing:
            raise R.Refusal("%s is not qualified: assert every criterion with --met %s "
                            "(missing: %s)" % (rec.id, ",".join(crit), ", ".join(missing)))
        fm["qualified_on"] = _today()
        return "qualified: met %s" % ",".join(crit)
    if met:
        raise R.Refusal("--met is only for qualifying a lead as it enters '%s'%s" % (
            ctx.qualified_stage, (" (%s was qualified on %s)" % (rec.id, fm["qualified_on"]))
            if "qualified_on" in fm else ""))
    if ctx.before_qualified(target) and "qualified_on" in fm:
        fm.pop("qualified_on")
        return "qualification cleared (back before '%s')" % ctx.qualified_stage
    return ""


def _lead_move(ctx, a, rec, fm, target, verb, note, records, extra=None, extra_log=None):
    dst_rel = "%s/%s" % (M.Ctx.stage_place(target), rec.name)
    was = M.Ctx.stage_of(rec)
    if a.dry_run:
        _guard(ctx, dst_rel, fm, rec.body, ctx.schema_for(rec))
        if extra:
            _guard(ctx, extra[0].rel, extra[1], extra[0].body, ctx.schema_for(extra[0]))
        _out(a, "would %s %s: %s -> %s%s" % (verb, rec.id, was, target,
                                              ("  (" + note + ")") if note else ""),
             {"dry_run": True, "id": rec.id, "from": was, "to": target})
        return 0
    if extra:
        _guard(ctx, extra[0].rel, extra[1], extra[0].body, ctx.schema_for(extra[0]))
    _write(ctx, rec, fm, dst_rel=dst_rel, records=records)
    if extra:
        _write(ctx, extra[0], extra[1])
    ctx.log([(rec.id, verb, M.Ctx.stage_place(was), M.Ctx.stage_place(target),
              R.resolve_actor(a.by, ctx.usable_config()), note)] + (extra_log or []))
    return None


def cmd_lead_advance(ctx, a):
    ctx.require_root()
    R.resolve_actor(a.by, ctx.usable_config())
    target = (a.to or "").strip().lower()
    if target not in ctx.stages:
        raise R.Refusal("'%s' is not a stage (%s)" % (a.to, ", ".join(ctx.stages)))
    if target in ctx.terminal_stages:
        raise R.Refusal("a lead is closed with `%s lead %s`, not advanced into '%s'" % (
            M.CLI, "win" if target == ctx.won_stage else "lose --reason …", target))
    with ctx.lock():
        records, _ = ctx.scan()
        rec = ctx.find(a.id, "lead")
        stage = M.Ctx.stage_of(rec)
        if stage in ctx.terminal_stages:
            raise R.Refusal("%s is %s; `%s lead reopen %s --to <stage>` first" % (
                rec.id, stage, M.CLI, rec.id))
        if stage == target:
            raise R.Refusal("%s is already in '%s'" % (rec.id, target))
        fm = _bump(_copy(rec.fm))
        note = _qualify(ctx, rec, fm, target, a.met)
        done = _lead_move(ctx, a, rec, fm, target, "advance", note, records)
        if done is not None:
            return done
    _out(a, "%s  %s -> %s%s" % (rec.id, stage, target, ("  (%s)" % note) if note else ""),
         {"id": rec.id, "from": stage, "to": target, "note": note})
    return 0


def cmd_lead_win(ctx, a):
    ctx.require_root()
    actor = R.resolve_actor(a.by, ctx.usable_config())
    with ctx.lock():
        records, _ = ctx.scan()
        rec = ctx.find(a.id, "lead")
        stage = M.Ctx.stage_of(rec)
        if stage in ctx.terminal_stages:
            raise R.Refusal("%s is already %s" % (rec.id, stage))
        acct = _account(ctx, records, rec.fm.get("account"), "account")
        today = _today()
        fm = _bump(_copy(rec.fm))
        qnote = _qualify(ctx, rec, fm, ctx.won_stage, a.met)
        fm["closed"] = today
        extra, extra_log, flipped = None, [], None
        old = acct.fm.get("status")
        if old != ctx.active_status:
            afm = _bump(_copy(acct.fm))
            afm["status"] = ctx.active_status
            afm["since"] = today
            extra = (acct, afm)
            extra_log = [(acct.id, "status", "status=%s" % old, "status=%s" % ctx.active_status,
                          actor, "won %s" % rec.id)]
            flipped = "%s %s -> %s" % (acct.id, old, ctx.active_status)
        note = "; ".join(x for x in (qnote, a.note or "") if x)
        done = _lead_move(ctx, a, rec, fm, ctx.won_stage, "win", note, records, extra, extra_log)
        if done is not None:
            return done
    _out(a, "%s  won%s" % (rec.id, ("; " + flipped) if flipped else "; %s already %s" % (
        acct.id, ctx.active_status)), {"id": rec.id, "account": acct.id, "flipped": bool(flipped)})
    return 0


def cmd_lead_lose(ctx, a):
    ctx.require_root()
    R.resolve_actor(a.by, ctx.usable_config())
    reason = _title(a.reason, "a reason")
    with ctx.lock():
        records, _ = ctx.scan()
        rec = ctx.find(a.id, "lead")
        stage = M.Ctx.stage_of(rec)
        if stage in ctx.terminal_stages:
            raise R.Refusal("%s is already %s" % (rec.id, stage))
        fm = _bump(_copy(rec.fm))
        fm["closed"] = _today()
        fm["lost_reason"] = reason
        done = _lead_move(ctx, a, rec, fm, ctx.lost_stage, "lose", reason, records)
        if done is not None:
            return done
    _out(a, "%s  lost (%s)" % (rec.id, reason), {"id": rec.id, "reason": reason})
    return 0


def cmd_lead_reopen(ctx, a):
    ctx.require_root()
    R.resolve_actor(a.by, ctx.usable_config())
    target = (a.to or "").strip().lower()
    if target not in ctx.open_stages:
        raise R.Refusal("reopen into an open stage (%s)" % ", ".join(ctx.open_stages))
    with ctx.lock():
        records, _ = ctx.scan()
        rec = ctx.find(a.id, "lead")
        stage = M.Ctx.stage_of(rec)
        if stage not in ctx.terminal_stages:
            raise R.Refusal("%s is open (in '%s'); use advance" % (rec.id, stage))
        fm = _bump(_copy(rec.fm))
        fm.pop("closed", None)
        fm.pop("lost_reason", None)
        note = _qualify(ctx, rec, fm, target, a.met)
        note = ("was %s" % stage) + (("; " + note) if note else "")
        done = _lead_move(ctx, a, rec, fm, target, "reopen", note, records)
        if done is not None:
            return done
    _out(a, "%s  reopened: %s -> %s" % (rec.id, stage, target),
         {"id": rec.id, "from": stage, "to": target})
    return 0


def _lead_row(l):
    return [l.id, M.Ctx.stage_of(l) or "?", l.h1 or "", l.fm.get("account", ""),
            ("%s %s" % (l.fm["value"], l.fm.get("currency", ""))) if l.fm.get("value") else "",
            l.fm.get("next_action", ""), l.fm.get("next_action_due", "")]


def cmd_lead_list(ctx, a):
    ctx.require_root()
    records, _ = ctx.scan()
    leads = [r for r in records if r.prefix == "LEAD" and r.parsed]
    if a.stage:
        leads = [l for l in leads if M.Ctx.stage_of(l) == a.stage]
    elif a.open:
        leads = [l for l in leads if M.Ctx.stage_of(l) in ctx.open_stages]
    if a.account:
        leads = [l for l in leads if l.fm.get("account") == a.account]
    order = {s: i for i, s in enumerate(ctx.stages)}
    leads.sort(key=lambda l: (order.get(M.Ctx.stage_of(l), 99), l.id))
    if a.json:
        R.emit_json([M.summary(l) for l in leads])
        return 0
    if not leads:
        print("(no leads)")
        return 0
    R.table([_lead_row(l) for l in leads], ["id", "stage", "title", "account", "value", "next",
                                            "due"])
    return 0


def cmd_show(ctx, a, want):
    ctx.require_root()
    rec = ctx.find(a.id, want)
    if a.json:
        d = M.summary(rec)
        d["body"] = rec.body
        if want == "lead":
            d["stage"] = M.Ctx.stage_of(rec)
        R.emit_json(d)
        return 0
    sys.stdout.write("%s\n\n%s" % (ctx.rel_of(rec), rec.text))
    return 0


# ---------------------------------------------------------------------------
# views
# ---------------------------------------------------------------------------

def cmd_pipeline(ctx, a):
    ctx.require_root()
    records, _ = ctx.scan()
    leads = [r for r in records if r.prefix == "LEAD" and r.parsed]
    if a.account:
        leads = [l for l in leads if l.fm.get("account") == a.account]
    board = OrderedDict((s, {"leads": [], "totals": OrderedDict()}) for s in ctx.stages)
    for l in leads:
        st = M.Ctx.stage_of(l) or "?"
        col = board.setdefault(st, {"leads": [], "totals": OrderedDict()})
        col["leads"].append(l)
        if isinstance(l.fm.get("value"), str) and isinstance(l.fm.get("currency"), str):
            try:
                amt = Decimal(l.fm["value"])
            except InvalidOperation:
                continue
            col["totals"][l.fm["currency"]] = col["totals"].get(l.fm["currency"], Decimal(0)) + amt
    open_totals = OrderedDict()
    for st in ctx.open_stages:
        for cur, amt in board[st]["totals"].items():
            open_totals[cur] = open_totals.get(cur, Decimal(0)) + amt
    if a.json:
        R.emit_json(OrderedDict([
            ("stages", [OrderedDict([("stage", s), ("open", s in ctx.open_stages),
                                     ("count", len(c["leads"])),
                                     ("totals", OrderedDict((k, str(v)) for k, v in
                                                            c["totals"].items())),
                                     ("leads", [l.id for l in c["leads"]])])
                        for s, c in board.items()]),
            ("open_totals", OrderedDict((k, str(v)) for k, v in open_totals.items()))]))
        return 0

    def money(t):
        return " + ".join("%s %s" % (v, k) for k, v in t.items()) or "-"
    rows = [[s, len(c["leads"]), money(c["totals"])] for s, c in board.items()]
    rows.append(["(open)", sum(len(board[s]["leads"]) for s in ctx.open_stages), money(open_totals)])
    R.table(rows, ["stage", "leads", "value"])
    if a.leads:
        for s, c in board.items():
            for l in c["leads"]:
                print("  %-10s %s" % (s, "  ".join(str(x) for x in _lead_row(l)[2:5])))
    return 0


def _occurrence(month, day, today):
    for year in (today.year, today.year + 1):
        d = day
        if (month, day) == (2, 29) and not calendar.isleap(year):
            d = 28    # a Feb 29 birthday is kept on Feb 28 in common years
        occ = _dt.date(year, month, d)
        if occ >= today:
            return occ
    return None


def cmd_birthdays(ctx, a):
    ctx.require_root()
    if a.next < 0:
        raise R.Refusal("--next is a number of days")
    today = R.today()
    records, _ = ctx.scan()
    keys = ("birthday", "anniversary") if a.anniversaries else ("birthday",)
    rows = []
    for r in records:
        if r.prefix != "CARD" or not r.parsed or r.archived:
            continue
        for key in keys:
            v = r.fm.get(key)
            if not isinstance(v, str) or not R.parse_partial_date(v):
                continue
            year = None if v.startswith("--") else int(v[:4])
            month, day = int(v[-5:-3]), int(v[-2:])
            occ = _occurrence(month, day, today)
            days = (occ - today).days
            if days > a.next:
                continue
            years = (occ.year - year) if year else None
            rows.append((occ, days, key, r, years))
    rows.sort(key=lambda x: (x[0], x[3].id))
    if a.json:
        R.emit_json([OrderedDict([("date", o.isoformat()), ("in_days", d), ("what", k),
                                  ("id", r.id), ("name", r.h1), ("years", y)])
                     for o, d, k, r, y in rows])
        return 0
    if not rows:
        print("(no %s in the next %d days)" % (" or ".join(k + "s" for k in keys), a.next))
        return 0
    R.table([[o.isoformat(), "today" if d == 0 else "in %d day%s" % (d, "" if d == 1 else "s"),
              r.id, r.h1 or "", (("turns %d" % y) if k == "birthday" else ("%d years" % y))
              if y is not None else ("anniversary" if k == "anniversary" else "")]
             for o, d, k, r, y in rows], ["date", "when", "id", "name", ""])
    return 0


def cmd_groups(ctx, a):
    ctx.require_root()
    records, _ = ctx.scan()
    counts = OrderedDict((g, 0) for g in (ctx.declared("groups") or []))
    for r in records:
        if r.prefix == "CARD" and not r.archived:
            for g in M.strings(r.fm, "groups"):
                counts[g] = counts.get(g, 0) + 1
    rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if a.json:
        R.emit_json(OrderedDict(rows))
        return 0
    if not rows:
        print("(no groups)")
        return 0
    R.table([[k, v] for k, v in rows], ["group", "contacts"])
    return 0


# ---------------------------------------------------------------------------
# vCard files
# ---------------------------------------------------------------------------

def _uid_resolver(cards):
    by_id = {c.id: c for c in cards}

    def uid_of(cid):
        c, seen = by_id.get(cid), set()
        while c is not None and c.archived and isinstance(c.fm.get("merged_into"), str) \
                and c.id not in seen:
            seen.add(c.id)
            c = by_id.get(c.fm["merged_into"])
        return c.fm.get("uid") if c is not None and isinstance(c.fm.get("uid"), str) else None
    return uid_of


def cmd_export(ctx, a):
    ctx.require_root()
    records, _ = ctx.scan()
    cards = [r for r in records if r.prefix == "CARD" and r.parsed]
    chosen = [c for c in cards if a.archived or not c.archived]
    if a.ids:
        want = set(a.ids)
        missing = want - set(c.id for c in cards)
        if missing:
            raise R.Refusal("no such card: %s" % ", ".join(sorted(missing)))
        chosen = [c for c in cards if c.id in want]
    if a.group:
        chosen = [c for c in chosen if a.group in M.strings(c.fm, "groups")]
    if a.account:
        chosen = [c for c in chosen if any(i.get("acct") == a.account
                                           for i in M.items(c.fm, "accounts"))]
    chosen.sort(key=lambda c: R.parse_id(c.id)[1])
    text = VC.export(chosen, _uid_resolver(cards),
                     "-//RasaOS//%s %s//EN" % (M.ELEMENT, M.VERSION))
    if a.out:
        if os.path.exists(a.out) and not a.force:
            raise R.Refusal("%s exists; pass --force to replace it" % a.out)
        with open(a.out, "wb") as fh:
            fh.write(text.encode("utf-8"))
        sys.stderr.write("exported %d card(s) to %s\n" % (len(chosen), a.out))
        return 0
    stream = getattr(sys.stdout, "buffer", None)
    if stream is not None:
        sys.stdout.flush()
        stream.write(text.encode("utf-8"))
        stream.flush()
    else:
        sys.stdout.write(text)
    return 0


class _Target(object):
    """A card an import writes: one already on disk (rec) or one it is about to create."""

    def __init__(self, rid, fm, body, fn, rec=None):
        self.id, self.fm, self.body, self.fn, self.rec = rid, fm, body, fn, rec
        self.changes, self.conflicts = [], []
        self.touched = rec is None

    def emails(self):
        return set(F.identity("email", i) for i in M.items(self.fm, "email"))


def cmd_import(ctx, a):
    ctx.require_root()
    cfg = ctx.usable_config()
    actor = R.resolve_actor(a.by, cfg)
    try:
        with open(a.file, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise R.Refusal("cannot read %s: %s" % (a.file, exc))
    incoming = VC.parse(data)
    if not incoming:
        raise R.Refusal("%s holds no vCard (BEGIN:VCARD … END:VCARD)" % a.file)
    extra_group = None
    if a.group:
        extra_group = a.group.strip().lower()
        groups = ctx.declared("groups")
        if not R.RX_SLUG.match(extra_group) or (groups is not None and extra_group not in groups):
            raise R.Refusal("--group '%s' is not %s" % (a.group, "declared (%s)" % ", ".join(groups)
                                                         if groups else "a slug"))
    fname = os.path.basename(a.file)
    schema = ctx.schemas["card"]
    with ctx.lock():
        rows = ctx.history()
        records, _ = ctx.scan()
        cards = [r for r in records if r.prefix == "CARD" and r.parsed]
        by_id = {c.id: c for c in cards}
        uid_index = {}
        for c in cards:
            u = c.fm.get("uid")
            if not isinstance(u, str):
                continue
            t = c
            while t is not None and t.archived and isinstance(t.fm.get("merged_into"), str):
                t = by_id.get(t.fm["merged_into"])
            if t is not None and not t.archived:
                uid_index.setdefault(u, t)
        email_index = {}
        for c in cards:
            if not c.archived:
                for i in M.items(c.fm, "email"):
                    email_index.setdefault(F.identity("email", i), set()).add(c.id)
        targets = OrderedDict()
        created, skipped, pending_related = [], [], []
        number = R.next_number("CARD", _ids(records), rows)
        today = _today()

        def existing(card):
            if card.id not in targets:
                targets[card.id] = _Target(card.id, _copy(card.fm), card.body, card.h1, card)
            return targets[card.id]

        for inc in incoming:
            fn, fields, note = VC.to_fields(inc, ctx)
            label = fn or inc.label()
            if not fn:
                skipped.append((label, "no name (FN, N or ORG) to title it with"))
                continue
            if extra_group:
                gs = list(fields.get("groups") or [])
                if extra_group not in gs:
                    fields["groups"] = gs + [extra_group]
            match, how = None, None
            uid = fields.get("uid")
            if uid:
                match = next((t for t in targets.values() if t.fm.get("uid") == uid), None)
                if match is None and uid in uid_index:
                    match = existing(uid_index[uid])
                how = "uid" if match else None
            if match is None:
                mine = set(F.identity("email", i) for i in fields.get("email", []))
                in_file = [t for t in targets.values() if t.emails() & mine]
                on_disk = set()
                for e in mine:
                    on_disk |= email_index.get(e, set())
                on_disk -= set(t.id for t in in_file)
                owners = [t.id for t in in_file] + sorted(on_disk)
                if len(owners) > 1:
                    skipped.append((label, "its email is on several cards (%s); merge them first"
                                    % ", ".join(owners)))
                    continue
                if owners:
                    match = targets.get(owners[0]) or existing(by_id[owners[0]])
                    how = "email"
            if match is None:
                rid = R.format_id("CARD", number)
                number += 1
                fm = OrderedDict([("id", rid), ("created", today), ("created_by", actor),
                                  ("updated", today)])
                fm.update(fields)
                if "uid" not in fm:
                    fm["uid"] = "urn:uuid:%s" % uuid.uuid4()
                t = _Target(rid, fm, R.new_body(fn, note), fn)
                targets[rid] = t
                created.append(t)
                pending_related.append((t, inc))
                if inc.problems:
                    t.changes.extend(inc.problems)
                continue
            if not a.update:
                skipped.append((label, "already here as %s (same %s); --update folds it in"
                                % (match.id, how)))
                continue
            if match.fm.get("uid"):
                fields.pop("uid", None)
            changes, conflicts = _fold(schema, match.fm, fields, match.id)
            if note and note not in match.body:
                match.body = match.body.rstrip("\n") + "\n\n" + note + "\n"
                changes.append("+notes")
            if changes:
                match.touched = True
                match.changes.extend(changes)
            match.conflicts.extend(conflicts + inc.problems)
            pending_related.append((match, inc))
        # RELATED: resolved by UID, among the cards here and the cards in the file
        by_uid = dict((u, c.id) for u, c in uid_index.items())
        for t in targets.values():
            if isinstance(t.fm.get("uid"), str):
                by_uid[t.fm["uid"]] = t.id
        for t, inc in pending_related:
            for rel, value in inc.related:
                who = by_uid.get(value)
                if who is None or who == t.id:
                    (t.conflicts if t.rec else t.changes).append(
                        "skipped RELATED %s (no card here has that UID)" % value)
                    continue
                cur = [OrderedDict(i) for i in M.items(t.fm, "related")]
                if any(i.get("who") == who for i in cur):
                    continue
                item = OrderedDict()
                if rel in ((schema["properties"]["related"]["items"]["properties"]["rel"])
                           .get("enum") or []):
                    item["rel"] = rel
                item["who"] = who
                t.fm["related"] = cur + [item]
                t.touched = True
                if t.rec is not None:
                    t.changes.append("+related %s" % who)
        writes = [t for t in targets.values() if t.touched]
        for t in writes:
            if t.rec is not None:
                _bump(t.fm)
            rel = t.rec.rel if t.rec is not None else \
                "%s/%s-%s.md" % (M.CONTACTS_DIR, t.id, R.slugify(t.fn))
            _guard(ctx, rel, t.fm, t.body, schema)
        updated = [t for t in writes if t.rec is not None]
        result = OrderedDict([
            ("file", fname), ("dry_run", bool(a.dry_run)),
            ("created", [OrderedDict([("id", t.id), ("name", t.fn), ("notes", t.changes)])
                         for t in created]),
            ("updated", [OrderedDict([("id", t.id), ("changes", t.changes),
                                      ("kept", t.conflicts)]) for t in updated]),
            ("skipped", [OrderedDict([("name", n), ("why", w)]) for n, w in skipped]),
        ])
        if not a.dry_run:
            entries = []
            for t in writes:
                if t.rec is None:
                    rel = "%s/%s-%s.md" % (M.CONTACTS_DIR, t.id, R.slugify(t.fn))
                    path = ctx.abs(rel)
                    ctx.write(path, t.fm, t.body, schema)
                    ctx.refresh_digest(path, rel)
                    entries.append((t.id, "import", "-", M.CONTACTS_DIR, actor, "from %s" % fname))
                else:
                    ctx.write(t.rec.path, t.fm, t.body, schema, t.rec.info)
                    ctx.refresh_digest(t.rec)
                    entries.append((t.id, "update", "-", "-", actor, "from %s: %s" % (
                        fname, ", ".join(t.changes))))
            if entries:
                ctx.log(entries)
    if a.json:
        R.emit_json(result)
        return 0
    lines = ["%s %s: %d created, %d updated, %d skipped" % (
        "would import" if a.dry_run else "imported", fname, len(created), len(updated),
        len(skipped))]
    for t in created:
        lines.append("  + %s  %s" % (t.id, t.fn))
        lines += ["      %s" % c for c in t.changes]
    for t in updated:
        lines.append("  ~ %s  %s" % (t.id, ", ".join(t.changes)))
        lines += ["      %s" % c for c in t.conflicts]
    for n, w in skipped:
        lines.append("  - %s: %s" % (n, w))
    _out(a, "\n".join(lines), result)
    return 0


# ---------------------------------------------------------------------------
# touch · history · check
# ---------------------------------------------------------------------------

def cmd_touch(ctx, a):
    ctx.require_root()
    actor = R.resolve_actor(a.by, ctx.usable_config())
    with ctx.lock():
        rec = ctx.find(a.id)
        schema = ctx.schema_for(rec)
        errs = R.schema_errors(schema, rec.fm) if rec.parsed else [("F-05", "", "unparseable")]
        if errs:
            raise R.Refusal("%s does not validate (%s %s); fix it first, then touch" % (
                rec.id, errs[0][1], errs[0][2]))
        fm = _bump(OrderedDict(rec.fm))
        if a.dry_run:
            _out(a, "would stamp %s updated=%s" % (rec.id, fm["updated"]), {"dry_run": True})
            return 0
        # Touch keeps the hand edit byte-for-byte: only the updated line changes.
        lines = rec.text.split("\n")
        ln = rec.line_of("updated")
        lines[ln - 1] = "updated: %s" % fm["updated"]
        R.atomic_write(rec.path, "\n".join(lines))
        ctx.refresh_digest(rec)
        ctx.log([(rec.id, "touch", "-", "-", actor, a.note or "")])
    _out(a, "%s  updated %s" % (rec.id, fm["updated"]), {"id": rec.id, "updated": fm["updated"]})
    return 0


def cmd_history(ctx, a):
    ctx.require_root()
    rows, _problems, _exists = R.load_history(ctx.history_path)
    if a.id:
        rows = [r for r in rows if r.id == a.id]
    if a.json:
        R.emit_json([OrderedDict([("at", r.at), ("id", r.id), ("verb", r.verb), ("from", r.frm),
                                  ("to", r.to), ("actor", r.actor), ("note", r.note)])
                     for r in rows])
        return 0
    R.table([[r.at, r.id, r.verb, r.frm, r.to, r.actor, r.note] for r in rows],
            ["at", "id", "verb", "from", "to", "actor", "note"])
    return 0


def cmd_check(ctx, a):
    report = V.run(ctx, fix=a.fix)
    report.render(as_json=a.json, quiet=a.quiet)
    return report.exit_code()


# ---------------------------------------------------------------------------
# the parser
# ---------------------------------------------------------------------------

def make_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="project root (default: the project that owns this tool)")
    common.add_argument("--json", action="store_true", help="machine-readable output")
    writer = argparse.ArgumentParser(add_help=False)
    writer.add_argument("--by", help="who is doing this (else $RASA_ACTOR, else default_actor)")
    writer.add_argument("--dry-run", action="store_true", help="show what would happen; write nothing")

    ap = argparse.ArgumentParser(prog=M.CLI, description="rasa.module.crm %s — the address book, "
                                 "accounts and the sales funnel (records-family/1). The law: "
                                 ".claude/crm-rules.md" % M.VERSION)
    ap.add_argument("--version", action="version", version="%s %s (%s, core %s)" % (
        M.ELEMENT, M.VERSION, R.FAMILY, R.CORE_VERSION))
    sub = ap.add_subparsers(dest="record", metavar="<contact|account|lead|verb>")

    def body_args(p):
        p.add_argument("--body", help="free notes for the body")
        p.add_argument("--body-file", help="read the body from a file")
        p.add_argument("--stdin", action="store_true", help="read the body from stdin")

    def editors(sp, want, with_pref=True):
        verbs = [("set", "set a field: set ID FIELD VALUE"),
                 ("unset", "remove a field: unset ID FIELD"),
                 ("add", "add a list item: add ID FIELD ITEM [--pref]"),
                 ("remove", "remove a list item: remove ID FIELD MATCH (value, label or #n)")]
        if with_pref:
            verbs.append(("pref", "mark one item preferred: pref ID FIELD MATCH"))
        for verb, h in verbs:
            p = sp.add_parser(verb, parents=[common, writer], help=h)
            p.add_argument("id")
            p.add_argument("args", nargs=argparse.REMAINDER)
            if verb == "add":
                p.add_argument("--pref", action="store_true", help="make the new item preferred")
            p.set_defaults(fn=(lambda v: (lambda c, a: _edit(c, a, want, v)))(verb), pref=False)
        p = sp.add_parser("rename", parents=[common, writer], help="change the name (the H1)")
        p.add_argument("id")
        p.add_argument("title")
        p.set_defaults(fn=lambda c, a: cmd_rename(c, a, want))

    groups = {}
    ap.set_defaults(record_parsers=groups)

    # -- contact -------------------------------------------------------------
    c = groups["contact"] = sub.add_parser("contact",
                                           help="the address book: people and organizations")
    cs = c.add_subparsers(dest="verb", metavar="<verb>")
    p = cs.add_parser("new", parents=[common, writer], help="add a contact card")
    p.add_argument("name", help="the display name (vCard FN), e.g. \"Jane Doe\"")
    p.add_argument("--kind", help="individual (default) or org")
    for part in ("prefix", "given", "additional", "family", "suffix"):
        p.add_argument("--" + part, help="structured name: %s" % part)
    p.add_argument("--nickname", action="append")
    p.add_argument("--org")
    p.add_argument("--title", help="job title")
    p.add_argument("--email", action="append", metavar="LABEL:ADDR", help="repeatable")
    p.add_argument("--phone", action="append", metavar="LABEL:NUMBER", help="repeatable")
    p.add_argument("--address", action="append", metavar="K=V;…", help="repeatable")
    p.add_argument("--url", action="append", metavar="LABEL:URL", help="repeatable")
    p.add_argument("--handle", action="append", metavar="SERVICE:HANDLE", help="repeatable")
    p.add_argument("--account", action="append", metavar="ACCT[:ROLE[:primary]]",
                   help="attach to an account (repeatable)")
    p.add_argument("--related", action="append", metavar="REL:CARD", help="repeatable")
    p.add_argument("--group", action="append", help="repeatable")
    p.add_argument("--birthday", help="YYYY-MM-DD, --MM-DD or MM-DD")
    p.add_argument("--anniversary", help="YYYY-MM-DD, --MM-DD or MM-DD")
    p.add_argument("--tz", help="IANA timezone")
    p.add_argument("--lang", help="language tag")
    p.add_argument("--photo", help="a URI or a project-relative path")
    body_args(p)
    p.set_defaults(fn=cmd_contact_new)
    editors(cs, "card")
    p = cs.add_parser("merge", parents=[common, writer],
                      help="fold DROP into KEEP; DROP is archived with merged_into: KEEP")
    p.add_argument("keep")
    p.add_argument("drop")
    p.set_defaults(fn=cmd_contact_merge)
    for name, restore in (("archive", False), ("restore", True)):
        p = cs.add_parser(name, parents=[common, writer], help="%s a card" % name)
        p.add_argument("id")
        p.add_argument("--note", help="why (goes in the history line)")
        if restore:
            p.add_argument("--unmerge", action="store_true",
                           help="restore a card that was folded into another")
        p.set_defaults(fn=(lambda r: (lambda c, a: cmd_contact_archive(c, a, r)))(restore),
                       unmerge=False)
    p = cs.add_parser("show", parents=[common], help="print a card (and where a merged one went)")
    p.add_argument("id")
    p.set_defaults(fn=cmd_contact_show)
    p = cs.add_parser("list", parents=[common], help="list cards")
    p.add_argument("--group")
    p.add_argument("--account")
    p.add_argument("--org")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--archived", action="store_true", help="only archived cards")
    g.add_argument("--all", action="store_true", help="include archived cards")
    p.set_defaults(fn=cmd_contact_list)
    p = cs.add_parser("find", parents=[common], help="search names, orgs, emails, phones, handles")
    p.add_argument("text", nargs="+")
    p.add_argument("--all", action="store_true", help="include archived cards")
    p.set_defaults(fn=cmd_contact_find)

    # -- account -------------------------------------------------------------
    c = groups["account"] = sub.add_parser("account", help="accounts: the customer hub")
    cs = c.add_subparsers(dest="verb", metavar="<verb>")
    p = cs.add_parser("new", parents=[common, writer], help="add an account (id acct-<slug>)")
    p.add_argument("name", help="the display name")
    p.add_argument("--slug", help="the id is acct-<slug> (default: from the name)")
    p.add_argument("--status", help="default: the first account status (prospect)")
    p.add_argument("--since", help="when it entered that status (default today)")
    p.add_argument("--tier")
    p.add_argument("--owner", help="who owns the relationship (a handle)")
    p.add_argument("--website")
    p.add_argument("--email", action="append", metavar="LABEL:ADDR")
    p.add_argument("--phone", action="append", metavar="LABEL:NUMBER")
    p.add_argument("--address", action="append", metavar="K=V;…")
    p.add_argument("--tag", action="append")
    body_args(p)
    p.set_defaults(fn=cmd_account_new)
    p = cs.add_parser("status", parents=[common, writer], help="change an account's status")
    p.add_argument("id")
    p.add_argument("status")
    p.add_argument("--since", help="when it changed (default today)")
    p.add_argument("--note", help="why (goes in the history line)")
    p.set_defaults(fn=cmd_account_status)
    editors(cs, "account")
    p = cs.add_parser("show", parents=[common],
                      help="the account with its contacts, leads, and family links")
    p.add_argument("id")
    p.set_defaults(fn=cmd_account_show)
    p = cs.add_parser("list", parents=[common], help="list accounts")
    p.add_argument("--status")
    p.set_defaults(fn=cmd_account_list)

    # -- lead ----------------------------------------------------------------
    c = groups["lead"] = sub.add_parser("lead", help="leads: the sales funnel")
    cs = c.add_subparsers(dest="verb", metavar="<verb>")
    p = cs.add_parser("new", parents=[common, writer], help="capture a lead (first stage)")
    p.add_argument("title")
    p.add_argument("--account", required=True, metavar="ACCT")
    p.add_argument("--contact", metavar="CARD")
    p.add_argument("--source")
    p.add_argument("--owner")
    p.add_argument("--value", help="estimated value, e.g. 1200 or 1200.50")
    p.add_argument("--currency", help="ISO 4217 (default: default_currency)")
    p.add_argument("--expected-close", dest="expected_close")
    p.add_argument("--next", help="the next action")
    p.add_argument("--due", help="when the next action is due")
    body_args(p)
    p.set_defaults(fn=cmd_lead_new)
    p = cs.add_parser("advance", parents=[common, writer], help="move a lead to another open stage")
    p.add_argument("id")
    p.add_argument("--to", required=True, metavar="STAGE")
    p.add_argument("--met", metavar="C1,C2", help="qualification criteria met (when qualifying)")
    p.set_defaults(fn=cmd_lead_advance)
    p = cs.add_parser("win", parents=[common, writer],
                      help="close as won; the account becomes a current customer")
    p.add_argument("id")
    p.add_argument("--note")
    p.add_argument("--met", help="an unqualified lead is qualified as it is won: assert every declared criterion (a,b,c)")
    p.set_defaults(fn=cmd_lead_win)
    p = cs.add_parser("lose", parents=[common, writer], help="close as lost, with the reason")
    p.add_argument("id")
    p.add_argument("--reason", required=True)
    p.set_defaults(fn=cmd_lead_lose)
    p = cs.add_parser("reopen", parents=[common, writer], help="reopen a won or lost lead")
    p.add_argument("id")
    p.add_argument("--to", required=True, metavar="STAGE")
    p.add_argument("--met", metavar="C1,C2")
    p.set_defaults(fn=cmd_lead_reopen)
    editors(cs, "lead", with_pref=False)
    p = cs.add_parser("show", parents=[common], help="print a lead")
    p.add_argument("id")
    p.set_defaults(fn=lambda c, a: cmd_show(c, a, "lead"))
    p = cs.add_parser("list", parents=[common], help="list leads")
    p.add_argument("--stage")
    p.add_argument("--open", action="store_true", help="only open stages")
    p.add_argument("--account")
    p.set_defaults(fn=cmd_lead_list)

    # -- top level -----------------------------------------------------------
    p = sub.add_parser("pipeline", parents=[common],
                       help="the funnel: leads and value per stage, per currency")
    p.add_argument("--account")
    p.add_argument("--leads", action="store_true", help="list the leads under the board")
    p.set_defaults(fn=cmd_pipeline)
    p = sub.add_parser("birthdays", parents=[common], help="upcoming birthdays")
    p.add_argument("--next", type=int, default=30, metavar="DAYS")
    p.add_argument("--anniversaries", action="store_true", help="include anniversaries")
    p.set_defaults(fn=cmd_birthdays)
    p = sub.add_parser("groups", parents=[common], help="address-book groups with counts")
    p.set_defaults(fn=cmd_groups)
    p = sub.add_parser("import", parents=[common, writer], help="read a .vcf file (vCard 3.0/4.0)")
    p.add_argument("file")
    p.add_argument("--update", action="store_true",
                   help="fold cards that are already here (same UID or email) into them")
    p.add_argument("--group", help="add every imported card to this group")
    p.set_defaults(fn=cmd_import)
    p = sub.add_parser("export", parents=[common], help="write vCard 4.0 (stdout or --out)")
    p.add_argument("ids", nargs="*", metavar="CARD")
    p.add_argument("--group")
    p.add_argument("--account")
    p.add_argument("--archived", action="store_true", help="include archived cards")
    p.add_argument("--out", metavar="FILE")
    p.add_argument("--force", action="store_true", help="replace --out if it exists")
    p.set_defaults(fn=cmd_export)
    p = sub.add_parser("touch", parents=[common, writer], help="record a hand edit (stamps updated)")
    p.add_argument("id")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_touch)
    p = sub.add_parser("history", parents=[common], help="the history log")
    p.add_argument("id", nargs="?")
    p.set_defaults(fn=cmd_history)
    p = sub.add_parser("check", parents=[common], help="run the validator (same as check-crm)")
    p.add_argument("--fix", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(fn=cmd_check)
    return ap


def main(argv=None, bin_dir=None):
    def _main(argv):
        ap = make_parser()
        a = ap.parse_args(argv)
        if not getattr(a, "fn", None):
            (a.record_parsers.get(getattr(a, "record", None)) or ap).print_help()
            return R.EXIT_REFUSED
        ctx = M.Ctx(getattr(a, "root", None), bin_dir)
        return a.fn(ctx, a)
    return R.run_main(_main, argv)
