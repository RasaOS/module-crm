# -*- coding: utf-8 -*-
"""vcard.py — contact cards in and out as vCard files (.vcf).

Out: vCard 4.0 (RFC 6350) — FN, N, NICKNAME, ORG, TITLE, EMAIL / TEL / ADR /
URL with TYPE and PREF=1, IMPP (handles), BDAY and ANNIVERSARY (including
--MMDD), CATEGORIES (groups), NOTE (the card's body text), UID, KIND, TZ,
LANG, PHOTO (a URI only), RELATED (by the related card's UID) and REV.
Content lines are escaped, folded at 75 octets and end in CRLF. A label that
is not a standard TYPE is carried the way the common address books carry it:
a property group plus an X-ABLabel line.

In: vCard 3.0 (RFC 2426) and 4.0, and the everyday vCard 2.1 habits —
folded lines, escapes, TYPE parameters in both syntaxes (TYPE=work,voice and
TYPE=work;TYPE=voice, and bare 2.1 parameters), QUOTED-PRINTABLE with
CHARSET, grouped properties (item1.EMAIL + item1.X-ABLabel), the vCard 3.0
TYPE=pref and the 4.0 PREF=n. Embedded photo data is never stored; the
import says it skipped it.

Pure standard library. This module reads and writes text; the tool decides
what becomes a record.
"""

import quopri
import re
from collections import OrderedDict

from . import fields as F
from . import model as M
from . import records as R

CRLF = "\r\n"
PROPERTY_OF = OrderedDict([("email", "EMAIL"), ("phone", "TEL"), ("address", "ADR"), ("url", "URL")])
#: labels that travel as a standard TYPE; any other label travels as an X-ABLabel
STANDARD_TYPES = {
    "email": ("work", "home"),
    "phone": ("work", "home", "cell", "fax", "pager", "text", "video", "textphone"),
    "address": ("work", "home"),
    "url": ("work", "home"),
}
LABEL_TO_TYPE = {"mobile": "cell"}
TYPE_TO_LABEL = {"cell": "mobile", "iphone": "mobile"}
#: TYPE values that say nothing a label should carry
IGNORED_TYPES = ("pref", "internet", "x400", "dom", "intl", "postal", "parcel", "voice",
                 "msg", "bbs", "modem", "car", "isdn", "pcs")
LEGACY_IM = OrderedDict([("X-AIM", "aim"), ("X-JABBER", "xmpp"), ("X-SKYPE", "skype"),
                         ("X-SKYPE-USERNAME", "skype"), ("X-ICQ", "icq"), ("X-MSN", "msn"),
                         ("X-YAHOO", "yahoo"), ("X-TWITTER", "twitter"), ("X-GTALK", "gtalk")])
QUIET = ("VERSION", "PRODID", "REV", "X-ABLABEL", "X-ABUID", "SOURCE", "CLIENTPIDMAP",
         "X-ABSHOWAS", "X-ADDRESSBOOKSERVER-KIND", "LABEL", "MAILER", "SORT-STRING",
         "X-PHONETIC-FIRST-NAME", "X-PHONETIC-LAST-NAME")


# ---------------------------------------------------------------------------
# out
# ---------------------------------------------------------------------------

def escape(text):
    """vCard TEXT escaping: backslash, newline, comma, semicolon."""
    return (text.replace("\\", "\\\\").replace("\r\n", "\n").replace("\n", "\\n")
            .replace(",", "\\,").replace(";", "\\;"))


def param(value):
    value = value.replace('"', "")
    return '"%s"' % value if re.search(r'[:;,]', value) else value


def fold(line):
    """Fold one content line at 75 octets (UTF-8), never splitting a character."""
    if len(line.encode("utf-8")) <= 75:
        return line
    out, cur = [], bytearray()
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > 75:
            out.append(cur.decode("utf-8"))
            cur = bytearray(b" ")
        cur.extend(b)
    out.append(cur.decode("utf-8"))
    return CRLF.join(out)


def date_out(value):
    """YYYY-MM-DD -> YYYYMMDD; --MM-DD -> --MMDD (RFC 6350 basic format)."""
    if value.startswith("--"):
        return "--" + value[2:].replace("-", "")
    return value.replace("-", "")


def body_text(rec):
    """The card's notes: its body minus the H1, blank edges trimmed."""
    lines = rec.body.split("\n")
    if rec.h1_lineno is not None:
        idx = rec.h1_lineno - rec.body_lineno
        if 0 <= idx < len(lines):
            lines = lines[:idx] + lines[idx + 1:]
    return "\n".join(lines).strip()


def card_lines(rec, uid_of, prodid):
    fm = rec.fm
    lines = ["BEGIN:VCARD", "VERSION:4.0", "PRODID:" + prodid]
    if isinstance(fm.get("uid"), str):
        uri = R.FORMATS["uri"](fm["uid"])
        lines.append("UID%s:%s" % ("" if uri else ";VALUE=text", fm["uid"] if uri
                                   else escape(fm["uid"])))
    if fm.get("kind") == "org":
        lines.append("KIND:org")
    lines.append("FN:" + escape(rec.h1 or rec.id))
    name = fm.get("name")
    if isinstance(name, dict):
        lines.append("N:" + ";".join(escape(name.get(k, "")) for k in
                                     ("family", "given", "additional", "prefix", "suffix")))
    nick = M.strings(fm, "nickname")
    if nick:
        lines.append("NICKNAME:" + ",".join(escape(n) for n in nick))
    if isinstance(fm.get("org"), str):
        lines.append("ORG:" + escape(fm["org"]))
    if isinstance(fm.get("title"), str):
        lines.append("TITLE:" + escape(fm["title"]))
    group = 0
    for field, prop in PROPERTY_OF.items():
        for it in M.items(fm, field):
            params, grp = [], None
            label = it.get("label")
            if isinstance(label, str):
                t = LABEL_TO_TYPE.get(label, label)
                if t in STANDARD_TYPES[field]:
                    params.append("TYPE=" + t)
                else:
                    group += 1
                    grp = "item%d" % group
            if M.truthy(it.get("pref")):
                params.append("PREF=1")
            if field == "address":
                value = ";".join(["", ""] + [escape(it.get(k, "")) for k in F.ADDRESS_PARTS])
            elif field == "url":
                value = it.get("value", "")
            else:
                value = escape(it.get("value", ""))
            lines.append("%s%s%s:%s" % (grp + "." if grp else "", prop,
                                        "".join(";" + p for p in params), value))
            if grp:
                lines.append("%s.X-ABLabel:%s" % (grp, escape(label)))
    for it in M.items(fm, "handle"):
        lines.append("IMPP:%s:%s" % (it.get("service", ""), it.get("value", "")))
    for key, prop in (("birthday", "BDAY"), ("anniversary", "ANNIVERSARY")):
        if isinstance(fm.get(key), str):
            lines.append("%s:%s" % (prop, date_out(fm[key])))
    groups = M.strings(fm, "groups")
    if groups:
        lines.append("CATEGORIES:" + ",".join(escape(g) for g in groups))
    if isinstance(fm.get("tz"), str):
        lines.append("TZ:" + escape(fm["tz"]))
    if isinstance(fm.get("lang"), str):
        lines.append("LANG:" + fm["lang"])
    photo = fm.get("photo")
    if isinstance(photo, str) and R.FORMATS["uri"](photo):
        lines.append("PHOTO:" + photo)
    for it in M.items(fm, "related"):
        target = uid_of(it.get("who"))
        if target:
            uri = R.FORMATS["uri"](target)
            lines.append("RELATED%s%s:%s" % ("" if uri else ";VALUE=text",
                                             (";TYPE=" + it["rel"]) if it.get("rel") else "",
                                             target if uri else escape(target)))
    note = body_text(rec)
    if note:
        lines.append("NOTE:" + escape(note))
    if isinstance(fm.get("updated"), str):
        lines.append("REV:%sT000000Z" % fm["updated"].replace("-", ""))
    lines.append("END:VCARD")
    return lines


def export(cards, uid_of, prodid):
    """Cards -> one vCard 4.0 text (CRLF, folded)."""
    out = []
    for rec in cards:
        for line in card_lines(rec, uid_of, prodid):
            out.append(fold(line) + CRLF)
    return "".join(out)


# ---------------------------------------------------------------------------
# in
# ---------------------------------------------------------------------------

class Prop(object):
    __slots__ = ("group", "name", "params", "value")

    def __init__(self, group, name, params, value):
        self.group, self.name, self.params, self.value = group, name, params, value

    def types(self):
        return [t.lower() for t in self.params.get("TYPE", []) if t]

    def first(self, key, default=None):
        vals = self.params.get(key)
        return vals[0] if vals else default


class Incoming(object):
    """One vCard as read, before it becomes (part of) a card."""

    def __init__(self):
        self.fn = None
        self.name = OrderedDict()
        self.nickname = []
        self.org = None
        self.title = None
        self.lists = OrderedDict((f, []) for f in ("email", "phone", "address", "url", "handle"))
        self.prefs = {}            # field -> (rank, index) of the preferred item
        self.birthday = None
        self.anniversary = None
        self.groups = []
        self.note = None
        self.uid = None
        self.kind = None
        self.tz = None
        self.lang = None
        self.photo = None
        self.related = []          # [(rel or None, target text)]
        self.problems = []         # what was dropped, in words
        self.skipped = OrderedDict()

    def label(self):
        return self.fn or (self.lists["email"][0]["value"] if self.lists["email"] else "(no name)")


def decode_bytes(data):
    """-> (text, the charset the file was read in)."""
    if isinstance(data, str):
        return data, "utf-8"
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def _param_section(line):
    """-> index of the ':' that ends the name+parameters, or -1."""
    inq = False
    for idx, c in enumerate(line):
        if c == '"':
            inq = not inq
        elif c == ":" and not inq:
            return idx
    return -1


def _is_qp(line):
    cut = _param_section(line)
    return cut > 0 and "QUOTED-PRINTABLE" in line[:cut].upper()


def logical_lines(text):
    """Unfold: a line starting with a space or tab continues the one before; a
    QUOTED-PRINTABLE value ending in '=' continues on the next line (vCard 2.1/3.0)."""
    out = []
    for line in re.split(r"\r\n|\n|\r", text):
        if out and out[-1].endswith("=") and _is_qp(out[-1]):
            out[-1] = out[-1][:-1] + line.lstrip(" \t")
            continue
        if out and line[:1] in (" ", "\t"):
            out[-1] += line[1:]
            continue
        out.append(line)
    return [line for line in out if line.strip()]


def _split_outside_quotes(text, sep):
    parts, buf, inq = [], [], False
    for c in text:
        if c == '"':
            inq = not inq
            continue
        if c == sep and not inq:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(c)
    parts.append("".join(buf))
    return parts


def parse_line(line):
    m = re.match(r"^(?:([A-Za-z0-9-]+)\.)?([A-Za-z0-9-]+)", line)
    if not m:
        return None
    group, name = m.group(1), m.group(2).upper()
    rest = line[m.end():]
    cut = _param_section(rest)
    if cut < 0 or (cut > 0 and not rest.startswith(";")):
        return None
    params = OrderedDict()
    for p in _split_outside_quotes(rest[:cut], ";")[1:]:
        p = p.strip()
        if not p:
            continue
        if "=" in p:
            k, v = p.split("=", 1)
            k = k.strip().upper()
            vals = [x.strip() for x in _split_outside_quotes(v, ",")]
            if k == "TYPE":   # vCard 4.0 also allows TYPE="work,voice"
                vals = [t.strip() for x in vals for t in x.split(",")]
        else:  # vCard 2.1: a bare parameter is a TYPE, or an ENCODING
            k = "ENCODING" if p.upper() in ("QUOTED-PRINTABLE", "BASE64", "B", "8BIT", "7BIT") \
                else "TYPE"
            vals = [p]
        params.setdefault(k, []).extend(vals)
    return Prop(group.lower() if group else None, name, params, rest[cut + 1:])


def decode(prop, file_charset):
    """The property value as text (QUOTED-PRINTABLE and CHARSET applied), or None for
    binary data."""
    enc = [e.upper() for e in prop.params.get("ENCODING", [])]
    charset = prop.first("CHARSET") or "utf-8"
    if "B" in enc or "BASE64" in enc:
        return None
    if "QUOTED-PRINTABLE" in enc:
        raw = quopri.decodestring(prop.value.encode("latin-1", "replace"))
        try:
            return raw.decode(charset, "replace")
        except LookupError:
            return raw.decode("utf-8", "replace")
    if file_charset == "latin-1" and prop.first("CHARSET"):
        try:
            return prop.value.encode("latin-1").decode(charset)
        except (LookupError, UnicodeError):
            return prop.value
    return prop.value


def split_value(text, sep):
    """Split on `sep` that is not escaped; escapes are kept for unescape()."""
    parts, buf, i = [], [], 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            buf.append(text[i:i + 2])
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


def unescape(text):
    out, i = [], 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            n = text[i + 1]
            out.append("\n" if n in "nN" else n)
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _one_line(text):
    return re.sub(r"\s*\n\s*", ", ", (text or "").strip())


def date_in(value, prop):
    """BDAY/ANNIVERSARY -> YYYY-MM-DD or --MM-DD, or None."""
    if (prop.first("VALUE") or "").lower() == "text":
        return None
    v = unescape(value).strip().split("T")[0]
    omit = prop.first("X-APPLE-OMIT-YEAR")
    m = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})$", v)
    if m:
        y, mo, d = m.groups()
        if omit and y == omit:
            s = "--%s-%s" % (mo, d)
            return s if R.parse_partial_date(s) else None
        s = "%s-%s-%s" % (y, mo, d)
        return s if R.parse_date(s) else None
    m = re.match(r"^--(\d{2})-?(\d{2})$", v)
    if m:
        s = "--%s-%s" % m.groups()
        return s if R.parse_partial_date(s) else None
    return None


def _label(prop, ablabels):
    if prop.group and prop.group in ablabels:
        raw = ablabels[prop.group]
        raw = re.sub(r"^_\$!<(.*)>!\$_$", r"\1", raw.strip())
        slug = R.slugify(raw)
        return None if slug == "untitled" else slug
    types = [t for t in prop.types() if t not in IGNORED_TYPES]
    for t in types:
        if t.startswith("x-"):
            continue
        return TYPE_TO_LABEL.get(t, t) if R.RX_SLUG.match(TYPE_TO_LABEL.get(t, t)) else None
    for t in types:
        if t.startswith("x-") and R.RX_SLUG.match(t[2:]):
            return t[2:]
    return None


def _pref_rank(prop):
    """Lower is more preferred; None when the property is not marked preferred."""
    p = prop.first("PREF")
    if p is not None:
        try:
            return int(p)
        except ValueError:
            return 1
    if "pref" in prop.types():
        return 1
    return None


def _add(inc, field, item, prop):
    idx = len(inc.lists[field])
    inc.lists[field].append(item)
    rank = _pref_rank(prop) if field in M.PREF_FIELDS else None   # a card prefers only these
    if rank is not None and (field not in inc.prefs or rank < inc.prefs[field][0]):
        inc.prefs[field] = (rank, idx)


def interpret(props, file_charset):
    inc = Incoming()
    ablabels = {}
    for p in props:
        if p.name == "X-ABLABEL" and p.group:
            v = decode(p, file_charset)
            if v:
                ablabels[p.group] = unescape(v)
    for p in props:
        raw = decode(p, file_charset)
        name = p.name
        if raw is None:
            if name == "PHOTO" or name == "LOGO":
                inc.problems.append("skipped embedded %s data (never stored in a card)" % name)
            else:
                inc.skipped[name] = inc.skipped.get(name, 0) + 1
            continue
        if name == "FN":
            inc.fn = _one_line(unescape(raw)) or None
        elif name == "N":
            comps = [_one_line(unescape(c)) for c in split_value(raw, ";")]
            for key, val in zip(("family", "given", "additional", "prefix", "suffix"), comps):
                if val:
                    inc.name[key] = val
        elif name == "NICKNAME":
            inc.nickname += [n for n in (_one_line(unescape(c)) for c in split_value(raw, ","))
                             if n and n not in inc.nickname]
        elif name == "ORG":
            comps = [_one_line(unescape(c)) for c in split_value(raw, ";")]
            comps = [c for c in comps if c]
            if comps:
                inc.org = comps[0]
                if len(comps) > 1:
                    inc.problems.append("kept ORG '%s', dropped its units (%s)" % (
                        comps[0], ", ".join(comps[1:])))
        elif name == "TITLE":
            inc.title = _one_line(unescape(raw)) or None
        elif name == "EMAIL":
            v = unescape(raw).strip()
            if v.lower().startswith("mailto:"):
                v = v[7:]
            _add(inc, "email", OrderedDict([("label", _label(p, ablabels)), ("value", v)]), p)
        elif name == "TEL":
            v = unescape(raw).strip()
            if v.lower().startswith("tel:"):
                v = v[4:]
            v = re.sub(r";ext=", " x", v)
            _add(inc, "phone", OrderedDict([("label", _label(p, ablabels)), ("value", v)]), p)
        elif name == "ADR":
            comps = [_one_line(unescape(c)) for c in split_value(raw, ";")] + [""] * 7
            pobox, ext, street, locality, region, code, country = comps[:7]
            street = ", ".join(x for x in (street, ext, pobox) if x)
            item = OrderedDict([("label", _label(p, ablabels)), ("street", street),
                                ("locality", locality), ("region", region), ("code", code),
                                ("country", country)])
            _add(inc, "address", item, p)
        elif name == "URL":
            _add(inc, "url", OrderedDict([("label", _label(p, ablabels)),
                                          ("value", unescape(raw).strip())]), p)
        elif name == "IMPP":
            v = unescape(raw).strip()
            if ":" in v:
                service, handle = v.split(":", 1)
                _add(inc, "handle", OrderedDict([("service", service.lower()),
                                                 ("value", handle.strip())]), p)
            else:
                inc.problems.append("skipped IMPP '%s' (no service:)" % v)
        elif name == "X-SOCIALPROFILE":
            types = [t for t in p.types() if t not in IGNORED_TYPES]
            service = types[0] if types else "social"
            v = p.first("X-USER") or unescape(raw).strip()
            _add(inc, "handle", OrderedDict([("service", service.lower()), ("value", v)]), p)
        elif name in LEGACY_IM:
            _add(inc, "handle", OrderedDict([("service", LEGACY_IM[name]),
                                             ("value", unescape(raw).strip())]), p)
        elif name in ("BDAY", "ANNIVERSARY", "X-ANNIVERSARY"):
            d = date_in(raw, p)
            key = "birthday" if name == "BDAY" else "anniversary"
            if d:
                setattr(inc, key, d)
            else:
                inc.problems.append("skipped %s '%s' (not a date)" % (name, raw.strip()))
        elif name == "CATEGORIES":
            for c in split_value(raw, ","):
                g = R.slugify(unescape(c))
                if unescape(c).strip() and g not in inc.groups:
                    inc.groups.append(g)
        elif name == "NOTE":
            text = unescape(raw).strip()
            if text:
                inc.note = (inc.note + "\n\n" + text) if inc.note else text
        elif name == "UID":
            inc.uid = unescape(raw).strip() or None
        elif name == "KIND":
            k = unescape(raw).strip().lower()
            if k in ("individual", "org"):
                inc.kind = k
            else:
                inc.problems.append("KIND:%s is not kept (a card is an individual or an org)" % k)
        elif name == "X-ABSHOWAS" and unescape(raw).strip().upper() == "COMPANY":
            inc.kind = "org"
        elif name == "TZ":
            tz = unescape(raw).strip()
            if R.is_iana_tz(tz):
                inc.tz = tz
            else:
                inc.problems.append("skipped TZ '%s' (not an IANA zone name)" % tz)
        elif name == "LANG":
            inc.lang = unescape(raw).strip() or None
        elif name == "PHOTO" or name == "LOGO":
            v = unescape(raw).strip()
            if name == "PHOTO" and re.match(r"^https?://\S+$", v):
                inc.photo = v
            else:
                inc.problems.append("skipped embedded %s data (never stored in a card)" % name)
        elif name == "RELATED":
            types = [t for t in p.types() if t not in IGNORED_TYPES]
            inc.related.append((types[0] if types else None, unescape(raw).strip()))
        elif name in QUIET or name in ("BEGIN", "END"):
            continue
        else:
            inc.skipped[name] = inc.skipped.get(name, 0) + 1
    for field, (_rank, idx) in inc.prefs.items():
        inc.lists[field][idx]["pref"] = "true"
    if not inc.fn:
        fallback = " ".join(inc.name.get(k, "") for k in ("prefix", "given", "additional",
                                                           "family", "suffix")).strip()
        inc.fn = re.sub(r"\s+", " ", fallback) or inc.org or None
    return inc


def parse(data):
    """A .vcf file (bytes or text) -> [Incoming]. Nested cards (2.1 AGENT) are skipped."""
    text, charset = decode_bytes(data)
    cards, cur, depth = [], None, 0
    for line in logical_lines(text):
        prop = parse_line(line)
        if prop is None:
            continue
        if prop.name == "BEGIN" and prop.value.strip().upper() == "VCARD":
            if cur is not None:
                depth += 1
                continue
            cur = []
            continue
        if prop.name == "END" and prop.value.strip().upper() == "VCARD":
            if depth:
                depth -= 1
                continue
            if cur is not None:
                cards.append(interpret(cur, charset))
            cur = None
            continue
        if cur is not None and depth == 0:
            cur.append(prop)
    return cards


def to_fields(inc, ctx):
    """An Incoming -> (fn, OrderedDict of card fields, note text). Every item is held to
    the card schema and the declared vocabularies; what fails is dropped and said in
    inc.problems — nothing invalid is ever written."""
    schema = ctx.schemas["card"]
    labels = ctx.declared("labels")
    groups_ok = ctx.declared("groups")
    out = OrderedDict()
    if inc.kind == "org":
        out["kind"] = "org"
    if inc.name:
        out["name"] = OrderedDict((k, inc.name[k]) for k in
                                  ("prefix", "given", "additional", "family", "suffix")
                                  if k in inc.name)
    if inc.nickname:
        out["nickname"] = list(inc.nickname)
    for key in ("org", "title"):
        if getattr(inc, key):
            out[key] = getattr(inc, key)
    for field, items in inc.lists.items():
        kept = []
        for it in items:
            it = OrderedDict((k, v) for k, v in it.items() if v)
            if isinstance(it.get("label"), str) and labels is not None and it["label"] not in labels:
                inc.problems.append("dropped the label '%s' on %s %s (not a declared label)" % (
                    it["label"], field, F.shorthand(field, it)))
                it.pop("label")
            if R.schema_errors(F.item_schema(schema, field), it, field):
                inc.problems.append("skipped %s %s (not valid)" % (field, F.shorthand(field, it)))
                continue
            if any(F.identity(field, k) == F.identity(field, it) for k in kept):
                continue
            kept.append(it)
        if kept:
            out[field] = kept
    for key in ("birthday", "anniversary"):
        if getattr(inc, key):
            out[key] = getattr(inc, key)
    gs = []
    for g in inc.groups:
        if groups_ok is not None and g not in groups_ok:
            inc.problems.append("dropped the group '%s' (not a declared group)" % g)
        elif g not in gs:
            gs.append(g)
    if gs:
        out["groups"] = gs
    for key in ("tz", "lang", "photo", "uid"):
        val = getattr(inc, key)
        if val and not R.schema_errors((schema["properties"] or {}).get(key) or {}, val):
            out[key] = val
        elif val:
            inc.problems.append("skipped %s '%s' (not valid)" % (key, val))
    return inc.fn, out, inc.note
