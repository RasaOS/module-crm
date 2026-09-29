# -*- coding: utf-8 -*-
"""fields.py — generic field editing for crm records.

`crm <record> set|unset|add|remove ID FIELD …` and the multi-valued options of
`crm contact new` all read one item grammar:

    label:value            email / phone / url       work:jane@acme.com
                                                    mobile:+1 555 0100
                                                    home:https://jane.example.org
    service:value          handle                    signal:+15550100
    acct-x[:role[:primary]] accounts                 acct-acme:billing:primary
    rel:CARD-nnnn          related                   spouse:CARD-0002
    key=value;key=value    any list-of-maps field    label=home;street=1 Main St;
                           (the only form for         locality=Springfield;region=IL;
                            address)                  code=62701;country=US

A ';' inside a key=value value is written '\\;'. Every item is checked against
the record type's JSON Schema before anything is written.
"""

import re
from collections import OrderedDict

from . import model as M
from . import records as R

#: list-of-map fields -> (identity key, shorthand form)
ITEM_FIELDS = OrderedDict([
    ("email", ("value", "label")),
    ("phone", ("value", "label")),
    ("url", ("value", "label")),
    ("handle", ("value", "service")),
    ("address", (None, "kv")),
    ("accounts", ("acct", "account")),
    ("related", ("who", "related")),
])
ADDRESS_PARTS = ("street", "locality", "region", "code", "country")

#: keys no generic editor may touch: bookkeeping, and facts only a lifecycle verb writes
PROTECTED = {
    "card": ("id", "created", "created_by", "updated", "merged_into"),
    "account": ("id", "created", "created_by", "updated", "status"),
    "lead": ("id", "created", "created_by", "updated", "closed", "lost_reason", "qualified_on"),
}
PROTECTED_WHY = {
    "id": "an id never changes",
    "created": "bookkeeping; the tools write it",
    "created_by": "bookkeeping; the tools write it",
    "updated": "bookkeeping; every edit stamps it (`crm touch` after a hand edit)",
    "merged_into": "only `crm contact merge` sets it",
    "status": "use `crm account status ACCT STATUS`",
    "closed": "use `crm lead win`, `crm lead lose` or `crm lead reopen`",
    "lost_reason": "use `crm lead lose --reason` or `crm lead reopen`",
    "qualified_on": "stamped by `crm lead advance --to <qualified stage> --met …`",
}

RX_KEYVAL = re.compile(r"^[a-z_]+=")
RX_URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
TRUE_WORDS = ("true", "yes", "1")
FALSE_WORDS = ("false", "no", "0")


def field_kind(schema, field):
    """-> 'scalar' | 'map' | 'list' | 'items' | None (not a key of this record type)."""
    node = (schema.get("properties") or {}).get(field)
    if node is None:
        return None
    t = node.get("type")
    if t == "array":
        return "items" if (node.get("items") or {}).get("type") == "object" else "list"
    if t == "object":
        return "map"
    return "scalar"


def item_schema(schema, field):
    return ((schema.get("properties") or {}).get(field) or {}).get("items") or {}


def split_unescaped(text, sep):
    """Split on `sep` not preceded by a backslash; '\\<sep>' becomes <sep>."""
    parts, buf, i = [], [], 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text) and text[i + 1] == sep:
            buf.append(sep)
            i += 2
            continue
        if c == sep:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts


def parse_kv(text):
    """'k=v;k=v' -> OrderedDict. Values are stripped; empty pairs are ignored."""
    out = OrderedDict()
    for part in split_unescaped(text, ";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise R.Refusal("'%s' is not key=value (write k=v;k=v)" % part)
        k, v = part.split("=", 1)
        k, v = k.strip(), v.strip()
        if not re.match(r"^[a-z][a-z0-9_]*$", k):
            raise R.Refusal("'%s' is not a key" % k)
        if k in out:
            raise R.Refusal("'%s' is given twice" % k)
        if v == "":
            raise R.Refusal("'%s=' is empty; to say nothing, leave the key out" % k)
        out[k] = v
    if not out:
        raise R.Refusal("nothing given")
    return out


def _split_label(field, text):
    """label:value -> (label or None, value)."""
    if field == "url" and (RX_URL_SCHEME.match(text) or ":" not in text):
        return None, text
    if ":" not in text:
        return None, text
    label, value = text.split(":", 1)
    label = label.strip().lower()
    if field == "url" and not R.RX_SLUG.match(label):
        return None, text
    return label, value.strip()


def _bool(item, key):
    if key not in item:
        return
    v = str(item[key]).strip().lower()
    if v in TRUE_WORDS:
        item[key] = "true"
    elif v in FALSE_WORDS:
        item.pop(key)
    else:
        raise R.Refusal("%s=%s: write %s=true, or leave it out" % (key, item[key], key))


def parse_item(field, text, pref=False):
    """One item of a list-of-maps field, from its shorthand. -> OrderedDict (unvalidated)."""
    if field not in ITEM_FIELDS:
        raise R.Refusal("'%s' is not a list of items" % field)
    text = (text or "").strip()
    if not text:
        raise R.Refusal("an empty %s item" % field)
    _ident, form = ITEM_FIELDS[field]
    if RX_KEYVAL.match(text):
        item = parse_kv(text)
    elif form == "label":
        label, value = _split_label(field, text)
        item = OrderedDict()
        if label:
            item["label"] = label
        item["value"] = value
    elif form == "service":
        if ":" not in text:
            raise R.Refusal("a handle is service:value (signal:+15550100, matrix:@jane:example.org)")
        service, value = text.split(":", 1)
        item = OrderedDict([("service", service.strip().lower()), ("value", value.strip())])
    elif form == "account":
        parts = [p.strip() for p in text.split(":")]
        if len(parts) > 3:
            raise R.Refusal("an account link is acct-<slug>[:role[:primary]]")
        item = OrderedDict([("acct", parts[0])])
        if len(parts) > 1 and parts[1]:
            item["role"] = parts[1]
        if len(parts) > 2 and parts[2]:
            if parts[2].lower() not in ("primary",) + TRUE_WORDS:
                raise R.Refusal("the third part of an account link is 'primary' (acct-acme:billing:primary)")
            item["primary"] = "true"
    elif form == "related":
        if ":" in text:
            rel, who = text.split(":", 1)
            item = OrderedDict([("rel", rel.strip().lower()), ("who", who.strip())])
        else:
            item = OrderedDict([("who", text)])
    else:
        raise R.Refusal("give an address as key=value pairs, e.g. "
                        "'label=home;street=1 Main St;locality=Springfield;region=IL;"
                        "code=62701;country=US'")
    _bool(item, "pref")
    _bool(item, "primary")
    if pref:
        if field not in M.PREF_FIELDS:
            raise R.Refusal("--pref applies to %s, not %s" % (", ".join(M.PREF_FIELDS), field))
        item["pref"] = "true"
    return item


def identity(field, item):
    """What makes two items the same entry (for duplicates and matching)."""
    if field == "email":
        return (item.get("value") or "").strip().lower()
    if field == "phone":
        return re.sub(r"[^\dx+]", "", (item.get("value") or "").lower())
    if field == "handle":
        return ((item.get("service") or "").lower(), (item.get("value") or "").lower())
    if field == "address":
        return tuple((item.get(p) or "").strip().lower() for p in ADDRESS_PARTS)
    if field == "accounts":
        return item.get("acct")
    if field == "related":
        return item.get("who")
    return item.get("value")


def shorthand(field, item):
    """The item back in the grammar it was given in (for history notes and tables)."""
    if not isinstance(item, dict):
        return str(item)
    if field in ("email", "phone", "url"):
        v = item.get("value", "")
        return ("%s:%s" % (item["label"], v)) if item.get("label") else v
    if field == "handle":
        return "%s:%s" % (item.get("service", ""), item.get("value", ""))
    if field == "accounts":
        out = item.get("acct", "")
        if item.get("role") or M.truthy(item.get("primary")):
            out += ":" + (item.get("role") or "")
        if M.truthy(item.get("primary")):
            out += ":primary"
        return out
    if field == "related":
        return ("%s:%s" % (item["rel"], item.get("who", ""))) if item.get("rel") else \
            item.get("who", "")
    return ";".join("%s=%s" % (k, str(v).replace(";", "\\;")) for k, v in item.items()
                    if k != "pref")


def one_line_address(item):
    parts = [item.get("street"), item.get("locality"),
             " ".join(p for p in (item.get("region"), item.get("code")) if p),
             item.get("country")]
    return ", ".join(p for p in parts if p)


def match(field, current, token):
    """Indexes of the items in `current` that `token` names: '#n', the item itself (any
    form), its value/acct/who, or its label/service/rel when that alone is unique."""
    token = (token or "").strip()
    m = re.match(r"^#(\d+)$", token)
    if m:
        n = int(m.group(1))
        if not 1 <= n <= len(current):
            raise R.Refusal("#%d: there are %d %s item(s)" % (n, len(current), field))
        return [n - 1]
    wanted = set()
    try:
        wanted.add(identity(field, parse_item(field, token)))
    except R.Refusal:
        pass
    ident_key = ITEM_FIELDS[field][0]
    hits = [i for i, it in enumerate(current)
            if identity(field, it) in wanted or
            (ident_key and str(it.get(ident_key, "")).lower() == token.lower()) or
            shorthand(field, it) == token]
    if hits:
        return hits
    label_key = {"handle": "service", "related": "rel"}.get(field, "label")
    return [i for i, it in enumerate(current) if str(it.get(label_key, "")) == token.lower()]


def normalize_scalar(rtype, field, value):
    """A scalar as the tool stores it (relative days resolved at capture). -> str or None
    (None = remove the key)."""
    v = (value or "").strip()
    if v == "":
        raise R.Refusal("an empty value; to say nothing, use unset")
    if "\n" in v:
        raise R.Refusal("values are one line")
    if field in ("birthday", "anniversary"):
        if re.match(r"^\d{2}-\d{2}$", v):
            v = "--" + v
        if not R.parse_partial_date(v):
            raise R.Refusal("%s: '%s' is not YYYY-MM-DD, --MM-DD or MM-DD" % (field, value))
        return v
    if field in ("since", "expected_close", "next_action_due"):
        return R.resolve_day(v).isoformat()
    if field == "kind":
        if v.lower() not in ("individual", "org"):
            raise R.Refusal("kind is individual or org")
        return None if v.lower() == "individual" else "org"
    if field == "currency":
        return v.upper()
    if field in ("source", "tier", "service"):
        return v.lower()
    return v


def check_item(schema, field, item):
    """Schema law for one item -> Refusal on the first problem."""
    errs = R.schema_errors(item_schema(schema, field), item, field)
    if errs:
        inv, path, msg = errs[0]
        raise R.Refusal("%s: %s %s (%s)" % (shorthand(field, item), path, msg, inv))
    return item
