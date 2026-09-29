# -*- coding: utf-8 -*-
"""model.py — what a crm ledger is: its paths, its record types, its config.

Everything the CLI and the validator share about rasa.module.crm lives here,
so neither re-derives it. The family conventions live in records.py.

Three record types, one root (crm/):

    CARD-nnnn     a contact card (vCard 4.0 aligned)   crm/contacts/  (+ contacts/_archive/)
    acct-<slug>   an account, the customer hub          crm/accounts/<id>.md
    LEAD-nnnn     a lead in the sales funnel            crm/leads/<stage>/
"""

import os
import re
from collections import OrderedDict

from . import records as R

MODULE = "crm"
ELEMENT = "rasa.module.crm"
VERSION = "0.2.0"
ROOT = "crm"
CLI = "crm"
CHECK = "check-crm"
CONFIG_NAME = "crm.config.yml"
CONFIG_SCHEMA_VALUE = "rasa.module.crm/1"

CONTACTS_DIR = "contacts"
CARD_ARCHIVE_DIR = CONTACTS_DIR + "/" + R.ARCHIVE_DIR
ACCOUNTS_DIR = "accounts"
LEADS_DIR = "leads"

DEFAULT_STAGES = ("new", "contacted", "qualified", "proposal", "won", "lost")
DEFAULT_WON = "won"
DEFAULT_LOST = "lost"
DEFAULT_QUALIFIED = "qualified"
DEFAULT_STATUSES = ("prospect", "active", "churned")
DEFAULT_ACTIVE = "active"

RX_CARD_STEM = re.compile(r"^CARD-[0-9]{4,}(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?$")
RX_LEAD_STEM = re.compile(r"^LEAD-[0-9]{4,}(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?$")

PREFIX_TYPE = OrderedDict([("CARD", "card"), ("acct", "account"), ("LEAD", "lead")])
TYPE_WORD = {"card": "contact", "account": "account", "lead": "lead"}

#: list-of-map fields that carry at most one `pref: true` (C-07)
PREF_FIELDS = ("email", "phone", "address")
#: list-of-map fields whose `label` is a declared-labels vocabulary item (F-21)
LABELLED_FIELDS = ("email", "phone", "address", "url")

HERE = os.path.dirname(os.path.abspath(__file__))


def schema_dir():
    """Installed: .claude/schemas/crm/. Element source: content/schemas/."""
    for cand in (os.path.join(HERE, "..", "..", "schemas", MODULE),
                 os.path.join(HERE, "..", "..", "schemas")):
        if os.path.exists(os.path.join(cand, "card.schema.json")):
            return os.path.normpath(cand)
    raise R.EnvError("cannot find the crm schemas next to %s (expected "
                     ".claude/schemas/crm/card.schema.json)" % HERE)


def config_semantics(cfg):
    """Cross-key config law the schema cannot say. -> [("F-20", line, message)]."""
    out = []
    stages = cfg.get("stages") if isinstance(cfg.get("stages"), list) and cfg.get("stages") \
        else list(DEFAULT_STAGES)
    names = OrderedDict([("won_stage", cfg.get("won_stage") or DEFAULT_WON),
                         ("lost_stage", cfg.get("lost_stage") or DEFAULT_LOST),
                         ("qualified_stage", cfg.get("qualified_stage") or DEFAULT_QUALIFIED)])
    for key, value in names.items():
        if value not in stages:
            out.append(("F-20", None, "%s '%s' is not one of the stages (%s); declare it or "
                                      "rename it" % (key, value, ", ".join(stages))))
    if len(set(names.values())) != len(names):
        out.append(("F-20", None, "won_stage, lost_stage and qualified_stage must be three "
                                  "different stages"))
    if not out:
        terminal = (names["won_stage"], names["lost_stage"])
        if stages[0] in terminal:
            out.append(("F-20", None, "the first stage '%s' is where new leads are filed; it "
                                      "cannot be terminal" % stages[0]))
        elif stages.index(names["qualified_stage"]) == 0:
            out.append(("F-20", None, "qualified_stage '%s' cannot be the first stage: new leads "
                                      "are filed there, and qualifying is a step a lead takes"
                                      % names["qualified_stage"]))
    statuses = cfg.get("account_statuses") if isinstance(cfg.get("account_statuses"), list) \
        and cfg.get("account_statuses") else list(DEFAULT_STATUSES)
    active = cfg.get("active_status") or DEFAULT_ACTIVE
    if active not in statuses:
        out.append(("F-20", None, "active_status '%s' is not one of account_statuses (%s)"
                    % (active, ", ".join(statuses))))
    return out


class Ctx(object):
    """One project's crm ledger."""

    def __init__(self, project_root=None, bin_dir=None):
        self.project = R.find_project_root(project_root, bin_dir)
        self.root = os.path.join(self.project, ROOT)
        self.history_path = os.path.join(self.root, "history.tsv")
        self.config_path = os.path.join(self.root, CONFIG_NAME)
        sd = schema_dir()
        self.schemas = {
            "card": R.load_json(os.path.join(sd, "card.schema.json")),
            "account": R.load_json(os.path.join(sd, "account.schema.json")),
            "lead": R.load_json(os.path.join(sd, "lead.schema.json")),
            "config": R.load_json(os.path.join(sd, "config.schema.json")),
        }
        self.config, self.config_problems, self.config_exists = R.load_config(
            self.config_path, self.schemas["config"], self.rel_root(CONFIG_NAME))
        if not self.config_problems:
            self.config_problems.extend(config_semantics(self.config))
        # what every derived setting reads: the config when it is sound, else the defaults
        self.settings = self.config if not self.config_problems else OrderedDict()

    # -- paths -------------------------------------------------------------

    def rel_root(self, rel):
        return ROOT + "/" + rel if rel else ROOT

    def rel_of(self, rec):
        return self.rel_root(rec.rel)

    def abs(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def require_root(self):
        if not os.path.isdir(self.root):
            raise R.EnvError("no crm ledger at %s — install rasa.module.crm (bin/init) "
                             "or pass --root" % self.root)

    # -- config ------------------------------------------------------------

    def usable_config(self):
        if self.config_problems:
            first = self.config_problems[0]
            raise R.EnvError("%s is not valid (line %s: %s); run %s" % (
                self.rel_root(CONFIG_NAME), first[1], first[2], CHECK))
        return self.config

    def declared(self, key):
        return R.declared(self.settings, key)

    @property
    def stages(self):
        v = self.settings.get("stages")
        return list(v) if isinstance(v, list) and v else list(DEFAULT_STAGES)

    @property
    def won_stage(self):
        return self.settings.get("won_stage") or DEFAULT_WON

    @property
    def lost_stage(self):
        return self.settings.get("lost_stage") or DEFAULT_LOST

    @property
    def qualified_stage(self):
        return self.settings.get("qualified_stage") or DEFAULT_QUALIFIED

    @property
    def terminal_stages(self):
        return (self.won_stage, self.lost_stage)

    @property
    def open_stages(self):
        return [s for s in self.stages if s not in self.terminal_stages]

    @property
    def first_stage(self):
        return self.open_stages[0]

    def needs_qualification(self, stage):
        """True for the won stage, and for an open stage at or after the qualified stage.

        A deal is never won unqualified: winning skips no gate. A lost lead
        may have been lost at any point, so the lost stage needs nothing.
        """
        if stage == self.won_stage:
            return True
        if stage in self.terminal_stages or stage not in self.stages:
            return False
        return self.stages.index(stage) >= self.stages.index(self.qualified_stage)

    def before_qualified(self, stage):
        return stage in self.stages and stage not in self.terminal_stages and \
            self.stages.index(stage) < self.stages.index(self.qualified_stage)

    @property
    def qualification(self):
        return self.declared("qualification")

    @property
    def statuses(self):
        v = self.settings.get("account_statuses")
        return list(v) if isinstance(v, list) and v else list(DEFAULT_STATUSES)

    @property
    def initial_status(self):
        return self.statuses[0]

    @property
    def active_status(self):
        return self.settings.get("active_status") or DEFAULT_ACTIVE

    # -- records -----------------------------------------------------------

    @staticmethod
    def is_record_name(stem, rel):
        return bool(RX_CARD_STEM.match(stem) or RX_LEAD_STEM.match(stem) or
                    R.RX_ACCT_ID.match(stem))

    def scan(self):
        found, strays = R.scan_root(self.root, self.is_record_name)
        return [R.read_record(p, rel) for p, rel in found], strays

    @staticmethod
    def type_of(rec):
        t = PREFIX_TYPE.get(rec.prefix or "")
        if t is None:
            if RX_CARD_STEM.match(rec.stem):
                t = "card"
            elif RX_LEAD_STEM.match(rec.stem):
                t = "lead"
            elif R.RX_ACCT_ID.match(rec.stem):
                t = "account"
        return t

    def schema_for(self, rec):
        t = self.type_of(rec)
        return self.schemas.get(t) if t else None

    def find(self, rid, want=None):
        """-> the Record for an id (archived ones included), or Refusal."""
        p = R.parse_id(rid or "")
        if p is None or p[0] not in PREFIX_TYPE:
            raise R.Refusal("'%s' is not a crm id (CARD-0001, acct-<slug>, LEAD-0001)" % rid)
        if want and PREFIX_TYPE[p[0]] != want:
            raise R.Refusal("%s is not a %s (%s)" % (rid, TYPE_WORD[want], {
                "card": "CARD-0001", "account": "acct-<slug>", "lead": "LEAD-0001"}[want]))
        records, _ = self.scan()
        hits = [r for r in records if r.id == rid]
        if not hits:
            raise R.Refusal("no %s %s in %s/" % (TYPE_WORD[PREFIX_TYPE[p[0]]], rid, ROOT))
        if len(hits) > 1:
            raise R.Refusal("%s is used by %d files; run %s" % (rid, len(hits), CHECK))
        return hits[0]

    # -- places ------------------------------------------------------------

    @staticmethod
    def place_of(rec):
        return R.place_token(rec.dir)

    @staticmethod
    def stage_of(rec):
        d = rec.dir
        if d.startswith(LEADS_DIR + "/") and "/" not in d[len(LEADS_DIR) + 1:]:
            return d[len(LEADS_DIR) + 1:]
        return None

    @staticmethod
    def stage_place(stage):
        return LEADS_DIR + "/" + stage

    def card_path(self, rid, fn, archived=False):
        d = CARD_ARCHIVE_DIR if archived else CONTACTS_DIR
        return self.abs("%s/%s-%s.md" % (d, rid, R.slugify(fn)))

    def account_path(self, aid):
        return self.abs("%s/%s.md" % (ACCOUNTS_DIR, aid))

    def lead_path(self, stage, rid, title):
        return self.abs("%s/%s/%s-%s.md" % (LEADS_DIR, stage, rid, R.slugify(title)))

    # -- writing -----------------------------------------------------------

    def lock(self):
        return R.Lock(self.root)

    def history(self):
        rows, _, _ = R.load_history(self.history_path)
        return rows

    def write(self, abs_path, fm, body, schema, info=None):
        """Render, self-validate, prove it reads back, and atomically write one record."""
        text = render(fm, body, schema, info)
        problems = R.schema_errors(schema, fm)
        if problems:
            inv, path, msg = problems[0]
            raise R.Refusal("refusing to write an invalid record: %s %s (%s)" % (path, msg, inv))
        bad = reads_back(text, fm)
        if bad:
            raise R.Refusal("refusing to write %s: it would not read back as written (%s)"
                            % (fm.get("id"), bad))
        R.atomic_write(abs_path, text)
        return text

    def refresh_digest(self, rec_or_path, rel=None):
        """Re-read a record just written and store its digest."""
        if isinstance(rec_or_path, R.Record):
            rec = R.read_record(rec_or_path.path, rec_or_path.rel)
        else:
            rec = R.read_record(rec_or_path, rel)
        table, _ = R.load_digests(self.root)
        table[rec.id] = R.digest_entry(rec, False, (), table.get(rec.id))
        R.save_digests(self.root, table)
        return rec

    def log(self, entries):
        return R.append_history(self.history_path, entries)


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def render(fm, body, schema=None, info=None):
    """The record's text, exactly as the tool writes it."""
    return R.render_record(fm, body, schema, info)


def plain(v):
    """A frontmatter value as the parser will give it back: all text."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return [plain(x) for x in v]
    if isinstance(v, dict):
        return dict((k, plain(x)) for k, x in v.items())
    return v


def reads_back(text, fm):
    """None when `text` parses back to exactly `fm`; else what went wrong."""
    lines, first, _body, _bl, err = R.split_frontmatter(text)
    if err:
        return err[1]
    values, _info, errors = R.parse_mapping(lines, first)
    if errors:
        return "line %d: %s" % errors[0]
    want, got = plain(fm), plain(values)
    for key in list(want) + [k for k in got if k not in want]:
        if want.get(key) != got.get(key):
            return "'%s' would read back as %r, not %r" % (key, got.get(key), want.get(key))
    return None


# ---------------------------------------------------------------------------
# small shared helpers
# ---------------------------------------------------------------------------

def is_frozen(rec, schema):
    """No crm record is frozen: a card, an account and a lead are all living records."""
    return False


def truthy(v):
    return v is True or (isinstance(v, str) and v == "true")


def items(fm, key):
    """A list-of-maps field as a list of dicts (anything else -> [])."""
    v = fm.get(key)
    return [i for i in v if isinstance(i, dict)] if isinstance(v, list) else []


def strings(fm, key):
    v = fm.get(key)
    return [i for i in v if isinstance(i, str)] if isinstance(v, list) else []


def recorded_status(rows):
    """The account status the history log last recorded: the last `status=` token, else the
    `status=` note of the filing line. None when the log never said."""
    val = R.last_status(rows, "status")
    if val is not None:
        return val
    for r in rows:
        if r.verb in R.FILING_VERBS and (r.note or "").startswith("status="):
            words = r.note[len("status="):].split()
            return words[0] if words else None
    return None


def summary(rec):
    """A JSON-ready view of a record."""
    return OrderedDict([("id", rec.id), ("type", Ctx.type_of(rec) or "?"),
                        ("path", ROOT + "/" + rec.rel), ("name", rec.h1),
                        ("archived", rec.archived), ("frontmatter", rec.fm)])
