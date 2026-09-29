# -*- coding: utf-8 -*-
"""End-to-end checks for the crm tool and check-crm.

Every scenario runs the real programs in a scratch project, with the clock
and the actor pinned through $RASA_TODAY / $RASA_NOW / $RASA_ACTOR.
Run:  python3 -B -m unittest discover -s tests
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ELEMENT = os.path.dirname(HERE)
BIN = os.path.join(ELEMENT, "content", "bin")
CRM = os.path.join(BIN, "crm")
CHECK = os.path.join(BIN, "check-crm")
TODAY = "2026-09-28"
STAGES = ("new", "contacted", "qualified", "proposal", "won", "lost")

VCARD3 = (
    "BEGIN:VCARD\r\n"
    "VERSION:3.0\r\n"
    "N:Müller;Jürgen;;Dr.;\r\n"
    "FN;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:Dr. J=C3=BCrgen M=C3=BCller\r\n"
    "ORG:Globex;Research\r\n"
    "TITLE:Chief Scientist\r\n"
    "item1.EMAIL;type=INTERNET;type=pref:juergen@globex.example\r\n"
    "item1.X-ABLabel:_$!<Other>!$_\r\n"
    "EMAIL;TYPE=INTERNET,WORK:j.mueller@globex.example\r\n"
    "TEL;TYPE=CELL,VOICE:+49 170 1234567\r\n"
    "item2.TEL:+49 30 555 0101\r\n"
    "item2.X-ABLabel:Assistant\r\n"
    "ADR;TYPE=WORK:;;Hauptstr. 5;Berlin;;10115;Germany\r\n"
    "NOTE;ENCODING=QUOTED-PRINTABLE:Line one=0ALine two with a long soft =\r\n"
    "break continued\r\n"
    "BDAY;X-APPLE-OMIT-YEAR=1604:1604-05-20\r\n"
    "PHOTO;ENCODING=b;TYPE=JPEG:/9j/4AAQSkZJRgABAQAAAQABAAD\r\n"
    " /2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQ\r\n"
    "CATEGORIES:Work,Science Friends\r\n"
    "X-AIM:jurgen42\r\n"
    "TZ:-05:00\r\n"
    "UID:abc-123\r\n"
    "END:VCARD\r\n"
    "BEGIN:VCARD\r\n"
    "VERSION:3.0\r\n"
    "FN:Ann Lee\r\n"
    "N:Lee;Ann;;;\r\n"
    "EMAIL;TYPE=HOME:ann@example.org\r\n"
    "TEL;TYPE=HOME;TYPE=VOICE:(555) 010-2000\r\n"
    "URL:https://ann.example.org/a\\,b\r\n"
    "END:VCARD\r\n")


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        for d in (".claude", "crm/contacts", "crm/accounts") + tuple("crm/leads/" + s for s in STAGES):
            os.makedirs(os.path.join(self.proj, d))
        with open(os.path.join(self.proj, "crm", "history.tsv"), "w") as fh:
            fh.write("at\tid\tverb\tfrom\tto\tactor\tnote\n")
        self.env = dict(os.environ)
        self.env.update({"RASA_PROJECT_ROOT": self.proj, "RASA_ACTOR": "chazz",
                         "RASA_TODAY": TODAY, "RASA_NOW": TODAY + "T12:00:00Z",
                         "PYTHONDONTWRITEBYTECODE": "1"})

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_(self, prog, *args, expect=0, env=None):
        e = dict(self.env)
        e.update(env or {})
        p = subprocess.run([sys.executable, "-B", prog] + list(args), capture_output=True,
                           text=True, env=e)
        if expect is not None:
            self.assertEqual(p.returncode, expect, "%s %s\nstdout:%s\nstderr:%s" % (
                os.path.basename(prog), " ".join(args), p.stdout, p.stderr))
        return p

    def crm(self, *args, **kw):
        return self.run_(CRM, *args, **kw)

    def jcrm(self, *args, **kw):
        return json.loads(self.crm(*(args + ("--json",)), **kw).stdout)

    def check(self, *args, **kw):
        return self.run_(CHECK, *args, **kw)

    def check_json(self, expect=None, env=None):
        return json.loads(self.run_(CHECK, "--json", expect=expect, env=env).stdout)

    def invariants(self, env=None, severity=("ERROR", "WARN")):
        d = self.check_json(env=env)
        return sorted(set(f["invariant"] for f in d["findings"] if f["severity"] in severity))

    def errors(self, env=None):
        return self.invariants(env=env, severity=("ERROR",))

    def warnings(self, env=None):
        return self.invariants(env=env, severity=("WARN",))

    def path(self, *parts):
        return os.path.join(self.proj, "crm", *parts)

    def read(self, rel):
        with open(self.path(*rel.split("/")), encoding="utf-8") as fh:
            return fh.read()

    def write(self, rel, text):
        p = self.path(*rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def edit(self, rel, old, new):
        text = self.read(rel)
        self.assertIn(old, text, "%s does not contain %r" % (rel, old))
        self.write(rel, text.replace(old, new, 1))

    def config(self, text):
        self.write("crm.config.yml", "schema: rasa.module.crm/1\n" + text)

    def history(self):
        with open(self.path("history.tsv"), encoding="utf-8") as fh:
            return [l.split("\t") for l in fh.read().strip().split("\n")[1:]]

    def find(self, rid):
        for d, _, fs in os.walk(self.path()):
            for f in fs:
                if f == rid + ".md" or f.startswith(rid + "-"):
                    return os.path.relpath(os.path.join(d, f), self.path()).replace(os.sep, "/")
        return None

    def seed_acme(self):
        self.crm("account", "new", "Acme Inc.", "--slug", "acme")
        self.crm("contact", "new", "Jane Doe", "--given", "Jane", "--family", "Doe",
                 "--email", "work:jane@acme.example", "--account", "acct-acme:billing:primary")


# ---------------------------------------------------------------------------
# walkthroughs — every verb, used the way a person would use it
# ---------------------------------------------------------------------------

class AddressBookTests(Base):

    def test_card_with_multi_valued_fields(self):
        self.crm("account", "new", "Acme Inc.", "--slug", "acme")
        out = self.crm(
            "contact", "new", "Jane Doe", "--given", "Jane", "--family", "Doe",
            "--prefix", "Dr.", "--nickname", "JD", "--org", "Acme Inc.", "--title", "Head of Ops",
            "--email", "work:jane@acme.example", "--email", "home:jane@example.org",
            "--phone", "mobile:+1 555 0100", "--phone", "work:+1 555 0199 x12",
            "--address", "label=work;street=1 Main St;locality=Springfield;region=IL;"
                         "code=62701;country=US",
            "--url", "home:https://jane.example.org", "--handle", "signal:+15550100",
            "--account", "acct-acme:billing:primary", "--group", "clients",
            "--birthday", "04-12", "--tz", "America/Chicago", "--lang", "en",
            "--body", "Prefers email.").stdout
        self.assertIn("CARD-0001  crm/contacts/CARD-0001-jane-doe.md", out)
        text = self.read("contacts/CARD-0001-jane-doe.md")
        for line in ("name: {prefix: Dr., given: Jane, family: Doe}",
                     "nickname: [JD]",
                     "email:\n  - {label: work, value: jane@acme.example}\n"
                     "  - {label: home, value: jane@example.org}",
                     "phone:\n  - {label: mobile, value: +1 555 0100}",
                     "  - {label: work, street: 1 Main St, locality: Springfield, region: IL, "
                     "code: \"62701\", country: US}",
                     "url:\n  - {label: home, value: https://jane.example.org}",
                     "handle:\n  - {service: signal, value: \"+15550100\"}",
                     "birthday: --04-12", "groups: [clients]",
                     "accounts:\n  - {acct: acct-acme, role: billing, primary: true}",
                     "tz: America/Chicago", "lang: en", "\n# Jane Doe\n\nPrefers email.\n"):
            self.assertIn(line, text)
        self.assertRegex(text, r"uid: urn:uuid:[0-9a-f-]{36}\n")
        self.assertNotIn("pref:", text)     # nothing is preferred until someone says so
        self.assertEqual(self.errors(), [])

    def test_set_unset_add_remove_pref(self):
        self.crm("contact", "new", "Jane Doe", "--email", "work:jane@acme.example",
                 "--email", "home:jane@example.org")
        rel = "contacts/CARD-0001-jane-doe.md"
        self.crm("contact", "set", "CARD-0001", "title", "Head of Ops")
        self.crm("contact", "set", "CARD-0001", "name.given", "Jane")
        self.crm("contact", "set", "CARD-0001", "name", "given=Jane;family=Doe")
        self.crm("contact", "set", "CARD-0001", "birthday", "--04-12")      # a --MM-DD value, not a flag
        self.crm("contact", "set", "CARD-0001", "kind", "org")
        self.crm("contact", "set", "CARD-0001", "kind", "individual")       # the default: key removed
        self.crm("contact", "add", "CARD-0001", "email", "other:jd@acme.example", "--pref")
        self.crm("contact", "add", "CARD-0001", "phone", "mobile:+1 555 0100")
        self.crm("contact", "add", "CARD-0001", "address",
                 "label=home;street=1 Elm St\\; Apt 2;locality=Springfield")
        self.crm("contact", "add", "CARD-0001", "nickname", "JD")
        self.crm("contact", "add", "CARD-0001", "groups", "Family")         # stored lower-case
        text = self.read(rel)
        self.assertIn("title: Head of Ops", text)
        self.assertIn("name: {given: Jane, family: Doe}", text)
        self.assertIn("birthday: --04-12", text)
        self.assertNotIn("kind:", text)
        self.assertIn("  - {label: other, value: jd@acme.example, pref: true}", text)
        self.assertIn("street: 1 Elm St; Apt 2", text)
        self.assertIn("groups: [family]", text)
        # the preference moves; there is only ever one (C-07)
        self.crm("contact", "pref", "CARD-0001", "email", "home")
        text = self.read(rel)
        self.assertEqual(text.count("pref: true"), 1)
        self.assertIn("{label: home, value: jane@example.org, pref: true}", text)
        self.crm("contact", "add", "CARD-0001", "email", "x@acme.example", "--pref")
        self.assertEqual(self.read(rel).count("pref: true"), 1)
        # remove by value, by label, by position
        self.crm("contact", "remove", "CARD-0001", "email", "x@acme.example")
        self.crm("contact", "remove", "CARD-0001", "email", "other")
        self.crm("contact", "remove", "CARD-0001", "phone", "#1")
        self.crm("contact", "remove", "CARD-0001", "nickname", "JD")
        self.crm("contact", "unset", "CARD-0001", "title")
        self.crm("contact", "unset", "CARD-0001", "name.given")
        text = self.read(rel)
        self.assertNotIn("x@acme.example", text)
        self.assertNotIn("jd@acme.example", text)
        self.assertNotIn("phone:", text)
        self.assertNotIn("nickname", text)
        self.assertNotIn("title:", text)
        self.assertIn("name: {family: Doe}", text)
        # ambiguous and missing matches are refused, not guessed
        self.crm("contact", "add", "CARD-0001", "email", "work:second@acme.example")
        p = self.crm("contact", "remove", "CARD-0001", "email", "work", expect=1)
        self.assertIn("matches 2", p.stderr)
        self.crm("contact", "remove", "CARD-0001", "email", "nobody@x.example", expect=1)
        # rename moves the slug with the H1
        self.crm("contact", "rename", "CARD-0001", "Jane Q. Doe")
        self.assertEqual(self.find("CARD-0001"), "contacts/CARD-0001-jane-q-doe.md")
        hist = [h[2] for h in self.history() if h[1] == "CARD-0001"]
        self.assertEqual(hist[0], "new")
        self.assertIn("pref", hist)
        self.assertIn("rename", hist)
        self.assertEqual(self.errors(), [])

    def test_flow_characters_inside_map_values_read_back(self):
        """Core 1.0.1: a quoted map value holding , [ ] { } is written plainly and reads back
        exactly (found by this module's build; fixed in records.py for the whole family)."""
        self.crm("contact", "new", "Odd Values",
                 "--address", "label=work;street=Suite 5, Floor 2 [rear];locality=Washington, D.C.",
                 "--url", "work:https://x.example/p?a=1,2&b={c}")
        d = self.jcrm("contact", "show", "CARD-0001")["frontmatter"]
        self.assertEqual(d["address"][0]["street"], "Suite 5, Floor 2 [rear]")
        self.assertEqual(d["address"][0]["locality"], "Washington, D.C.")
        self.assertEqual(d["url"][0]["value"], "https://x.example/p?a=1,2&b={c}")
        self.crm("contact", "set", "CARD-0001", "name", "given=A, B;family=C")
        self.assertEqual(self.jcrm("contact", "show", "CARD-0001")["frontmatter"]["name"],
                         {"given": "A, B", "family": "C"})
        self.assertEqual(self.errors(), [])
        try:
            import yaml  # optional: any YAML reader sees the same values
        except ImportError:
            return
        text = self.read("contacts/CARD-0001-odd-values.md").split("---")[1]
        self.assertEqual(yaml.safe_load(text)["address"][0]["street"], "Suite 5, Floor 2 [rear]")

    def test_find_list_show_groups(self):
        self.seed_acme()
        self.crm("contact", "new", "Bob Smith", "--phone", "work:(555) 010-2000", "--group", "vendors",
                 "--org", "Initech")
        self.crm("contact", "new", "Carla Diaz", "--group", "vendors", "--handle", "matrix:@carla:ex.org")
        self.assertEqual([c["id"] for c in self.jcrm("contact", "find", "jane")], ["CARD-0001"])
        self.assertEqual([c["id"] for c in self.jcrm("contact", "find", "5550102")], ["CARD-0002"])
        self.assertEqual([c["id"] for c in self.jcrm("contact", "find", "@carla")], ["CARD-0003"])
        self.assertEqual([c["id"] for c in self.jcrm("contact", "list", "--group", "vendors")],
                         ["CARD-0002", "CARD-0003"])        # sorted by name
        self.assertEqual([c["id"] for c in self.jcrm("contact", "list", "--account", "acct-acme")],
                         ["CARD-0001"])
        self.assertEqual([c["id"] for c in self.jcrm("contact", "list", "--org", "initech")],
                         ["CARD-0002"])
        self.assertEqual(self.jcrm("groups"), {"vendors": 2})
        self.crm("lead", "new", "Renewal", "--account", "acct-acme", "--contact", "CARD-0001")
        show = self.jcrm("contact", "show", "CARD-0001")
        self.assertEqual(show["leads"], [{"id": "LEAD-0001", "stage": "new", "title": "Renewal"}])
        human = self.crm("contact", "show", "CARD-0001").stdout
        self.assertIn("account: acct-acme — Acme Inc., billing (primary)", human)

    def test_merge_folds_a_duplicate(self):
        self.seed_acme()
        self.crm("account", "new", "Globex", "--slug", "globex")
        self.crm("contact", "new", "J. Doe", "--email", "work:jane@acme.example",
                 "--email", "home:jane@example.org", "--title", "COO", "--group", "family",
                 "--account", "acct-globex:advisor", "--body", "Met at the fair.")
        self.crm("contact", "set", "CARD-0001", "title", "Head of Ops")
        self.assertEqual(self.warnings(), ["C-13"])         # the same email on two live cards
        self.crm("lead", "new", "Globex advisory", "--account", "acct-globex", "--contact", "CARD-0002")
        self.crm("contact", "new", "Sam Doe", "--related", "spouse:CARD-0002")
        out = self.crm("contact", "merge", "CARD-0001", "CARD-0002").stdout
        self.assertIn("kept title 'Head of Ops' (the other says 'COO')", out)
        keep = self.read("contacts/CARD-0001-jane-doe.md")
        self.assertIn("  - {label: home, value: jane@example.org}", keep)
        self.assertEqual(keep.count("jane@acme.example"), 1)
        self.assertIn("groups: [family]", keep)
        self.assertIn("{acct: acct-globex, role: advisor}", keep)
        self.assertIn("title: Head of Ops", keep)
        self.assertIn("From [[CARD-0002]] (J. Doe):\n\nMet at the fair.", keep)
        drop = self.read("contacts/_archive/CARD-0002-j-doe.md")
        self.assertIn("merged_into: CARD-0001", drop)
        self.assertEqual([h[2:5] for h in self.history()[-2:]],
                         [["merge", "-", "-"], ["merge", "contacts", "contacts/_archive"]])
        # references to DROP still resolve; show DROP says where it went
        self.assertEqual(self.errors(), [])
        self.assertEqual(self.warnings(), [])
        self.assertIn("CARD-0002 was merged into CARD-0001 — Jane Doe",
                      self.crm("contact", "show", "CARD-0002").stdout)
        self.assertEqual(self.jcrm("contact", "show", "CARD-0002")["now"], "CARD-0001")
        # a merged card is not a place to write, and restores only deliberately
        self.crm("contact", "set", "CARD-0002", "title", "x", expect=1)
        self.crm("contact", "merge", "CARD-0001", "CARD-0002", expect=1)
        self.crm("lead", "new", "x", "--account", "acct-acme", "--contact", "CARD-0002", expect=1)
        self.assertIn("--unmerge", self.crm("contact", "restore", "CARD-0002", expect=1).stderr)
        self.crm("contact", "restore", "CARD-0002", "--unmerge")
        self.assertNotIn("merged_into", self.read("contacts/CARD-0002-j-doe.md"))
        self.assertEqual(self.errors(), [])

    def test_archive_and_restore(self):
        self.seed_acme()
        self.crm("contact", "archive", "CARD-0001", "--note", "left the company")
        self.assertEqual(self.find("CARD-0001"), "contacts/_archive/CARD-0001-jane-doe.md")
        self.assertEqual(self.jcrm("contact", "list"), [])
        self.assertEqual(len(self.jcrm("contact", "list", "--archived")), 1)
        self.crm("contact", "archive", "CARD-0001", expect=1)
        self.crm("contact", "add", "CARD-0001", "email", "x@y.example", expect=1)
        self.assertEqual(self.errors(), [])
        self.crm("contact", "restore", "CARD-0001")
        self.assertEqual(self.find("CARD-0001"), "contacts/CARD-0001-jane-doe.md")
        self.assertEqual([h[2:5] for h in self.history() if h[1] == "CARD-0001"][-2:],
                         [["archive", "contacts", "contacts/_archive"],
                          ["restore", "contacts/_archive", "contacts"]])
        self.assertEqual(self.errors(), [])


class AccountTests(Base):

    def test_accounts_walkthrough(self):
        out = self.crm("account", "new", "Acme Inc.", "--slug", "acme", "--tier", "smb",
                       "--owner", "chazz", "--website", "https://acme.example",
                       "--email", "billing:billing@acme.example").stdout
        self.assertIn("acct-acme  crm/accounts/acct-acme.md", out)
        text = self.read("accounts/acct-acme.md")
        self.assertIn("status: prospect\nsince: 2026-09-28\ntier: smb\nowner: chazz", text)
        self.assertIn("\n# Acme Inc.\n", text)
        self.crm("account", "new", "Acme Holdings", "--slug", "acme", expect=1)   # taken
        self.crm("account", "new", "Globex Corporation")                           # slug from the name
        self.assertTrue(os.path.exists(self.path("accounts", "acct-globex-corporation.md")))
        self.crm("account", "status", "acct-acme", "active", "--since", "2026-09-01")
        self.crm("account", "status", "acct-acme", "active", expect=1)            # already
        self.crm("account", "status", "acct-acme", "vip", expect=1)               # not a status
        self.crm("account", "status", "acct-acme", "churned", "--since", "+1d", expect=1)  # future
        self.assertIn("status: active\nsince: 2026-09-01", self.read("accounts/acct-acme.md"))
        self.assertEqual(self.history()[-1][2:5], ["status", "status=prospect", "status=active"])
        self.crm("account", "set", "acct-acme", "status", "churned", expect=1)    # only via status
        self.crm("account", "set", "acct-acme", "tier", "enterprise")
        self.crm("account", "add", "acct-acme", "tags", "renewal-2027")
        self.crm("account", "add", "acct-acme", "phone", "main:+1 555 0000", "--pref")
        self.crm("account", "rename", "acct-acme", "Acme Holdings")
        self.assertTrue(os.path.exists(self.path("accounts", "acct-acme.md")))    # the id never moves
        self.assertIn("\n# Acme Holdings\n", self.read("accounts/acct-acme.md"))
        lst = self.jcrm("account", "list")
        self.assertEqual([a["id"] for a in lst], ["acct-globex-corporation", "acct-acme"])
        self.assertEqual([a["id"] for a in self.jcrm("account", "list", "--status", "active")],
                         ["acct-acme"])
        self.assertEqual(self.errors(), [])

    def test_account_show_joins_people_leads_and_the_family(self):
        self.seed_acme()
        self.crm("contact", "new", "Bob Smith", "--account", "acct-acme:technical")
        self.crm("contact", "new", "Old Contact", "--account", "acct-acme")
        self.crm("contact", "archive", "CARD-0003")
        self.crm("lead", "new", "Renewal", "--account", "acct-acme", "--value", "100", "--currency", "USD")
        self.crm("lead", "new", "Expansion", "--account", "acct-acme")
        self.crm("lead", "lose", "LEAD-0002", "--reason", "no budget")
        # other family modules, mounted, naming the account
        os.makedirs(os.path.join(self.proj, "schedule", "work"))
        with open(os.path.join(self.proj, "schedule", "work", "EVT-0001-kickoff.md"), "w") as fh:
            fh.write("---\nid: EVT-0001\naccount: acct-acme\n---\n\n# Kickoff\n")
        os.makedirs(os.path.join(self.proj, "messages", "email", "THR-0001-renewal"))
        for name, text in (("THR-0001.md", "---\nid: THR-0001\naccount: acct-acme\n---\n\n# Renewal\n"),
                           ("MSG-0001.md", "---\nid: MSG-0001\n---\n\nAbout @acct-acme.\n")):
            with open(os.path.join(self.proj, "messages", "email", "THR-0001-renewal", name), "w") as fh:
                fh.write(text)
        d = self.jcrm("account", "show", "acct-acme")
        self.assertEqual([(c["id"], c["role"], c["primary"]) for c in d["contacts"]],
                         [("CARD-0001", "billing", True), ("CARD-0002", "technical", False)])
        self.assertEqual({k: [l["id"] for l in v] for k, v in d["leads"].items()},
                         {"new": ["LEAD-0001"], "lost": ["LEAD-0002"]})
        self.assertEqual(d["elsewhere"]["schedule"]["count"], 1)
        self.assertEqual(d["elsewhere"]["messages"]["count"], 1)     # one thread, two files
        self.assertIsNone(d["elsewhere"]["notes"])                   # not mounted
        human = self.crm("account", "show", "acct-acme").stdout
        self.assertIn("CARD-0001  Jane Doe, billing  (primary)", human)
        self.assertIn("notes     not mounted", human)


class FunnelTests(Base):

    def test_capture_qualify_win(self):
        self.seed_acme()
        self.crm("lead", "new", "Renewal", "--account", "acct-acme", "--value", "1200", expect=1)
        self.config("default_currency: USD\n")
        out = self.crm("lead", "new", "Renewal", "--account", "acct-acme", "--contact", "CARD-0001",
                       "--value", "1200", "--source", "referral", "--next", "Send the quote",
                       "--due", "fri", "--expected-close", "2026-11-15").stdout
        self.assertIn("LEAD-0001  crm/leads/new/LEAD-0001-renewal.md", out)
        text = self.read("leads/new/LEAD-0001-renewal.md")
        self.assertIn("value: \"1200\"\ncurrency: USD", text)
        self.assertIn("next_action: Send the quote\nnext_action_due: 2026-10-02", text)
        self.crm("lead", "advance", "LEAD-0001", "--to", "contacted")
        # THE HARD-STOP: nothing declares what "qualified" means
        p = self.crm("lead", "advance", "LEAD-0001", "--to", "qualified", "--met", "need", expect=1)
        self.assertIn("HARD-STOP", p.stderr)
        self.assertEqual(self.find("LEAD-0001"), "leads/contacted/LEAD-0001-renewal.md")
        self.config("default_currency: USD\nqualification: [need, budget, decision-maker]\n")
        p = self.crm("lead", "advance", "LEAD-0001", "--to", "qualified", expect=1)
        self.assertIn("missing: need, budget, decision-maker", p.stderr)
        p = self.crm("lead", "advance", "LEAD-0001", "--to", "qualified", "--met", "need,budget",
                     expect=1)
        self.assertIn("missing: decision-maker", p.stderr)
        p = self.crm("lead", "advance", "LEAD-0001", "--to", "qualified", "--met",
                     "need,budget,decision-maker,vibes", expect=1)
        self.assertIn("vibes", p.stderr)
        # skipping the qualified stage does not skip qualifying
        self.crm("lead", "advance", "LEAD-0001", "--to", "proposal", expect=1)
        self.crm("lead", "advance", "LEAD-0001", "--to", "qualified", "--met",
                 "need,budget,decision-maker")
        text = self.read("leads/qualified/LEAD-0001-renewal.md")
        self.assertIn("qualified_on: 2026-09-28", text)
        self.assertEqual(self.history()[-1][2:7], ["advance", "leads/contacted", "leads/qualified",
                                                   "chazz", "qualified: met need,budget,decision-maker"])
        self.crm("lead", "advance", "LEAD-0001", "--to", "proposal", "--met", "need", expect=1)  # already
        self.crm("lead", "advance", "LEAD-0001", "--to", "proposal")
        self.crm("lead", "advance", "LEAD-0001", "--to", "won", expect=1)        # win is its own verb
        # WIN: two records, two history lines, one act
        out = self.crm("lead", "win", "LEAD-0001").stdout
        self.assertIn("acct-acme prospect -> active", out)
        text = self.read("leads/won/LEAD-0001-renewal.md")
        self.assertIn("closed: 2026-09-28", text)
        self.assertIn("status: active\nsince: 2026-09-28", self.read("accounts/acct-acme.md"))
        last = self.history()[-2:]
        self.assertEqual([h[1:5] for h in last],
                         [["LEAD-0001", "win", "leads/proposal", "leads/won"],
                          ["acct-acme", "status", "status=prospect", "status=active"]])
        self.assertEqual(last[0][0], last[1][0])       # one stamp: one act
        self.crm("lead", "win", "LEAD-0001", expect=1)
        self.crm("lead", "advance", "LEAD-0001", "--to", "new", expect=1)       # closed: reopen first
        # a second win for a live customer changes nothing on the account
        self.crm("lead", "new", "Add-on", "--account", "acct-acme")
        n = len(self.history())
        # a deal is never won unqualified: the win itself must assert the criteria
        self.assertIn("missing", self.crm("lead", "win", "LEAD-0002", expect=1).stderr)
        self.assertIn("already active", self.crm("lead", "win", "LEAD-0002", "--met",
                                                 "need,budget,decision-maker").stdout)
        self.assertEqual(len(self.history()), n + 1)
        self.assertEqual(self.errors(), [])
        self.assertEqual(self.warnings(), [])

    def test_lose_reopen_and_the_qualification_mark(self):
        self.seed_acme()
        self.config("qualification: [need]\n")
        self.crm("lead", "new", "Renewal", "--account", "acct-acme")
        self.crm("lead", "lose", "LEAD-0001", expect=2)                         # --reason is required
        self.crm("lead", "lose", "LEAD-0001", "--reason", "   ", expect=1)
        self.crm("lead", "lose", "LEAD-0001", "--reason", "Chose a local supplier")
        text = self.read("leads/lost/LEAD-0001-renewal.md")
        self.assertIn("closed: 2026-09-28\nlost_reason: Chose a local supplier", text)
        self.assertIn("status: prospect", self.read("accounts/acct-acme.md"))  # nothing on the account
        self.crm("lead", "lose", "LEAD-0001", "--reason", "again", expect=1)
        self.crm("lead", "reopen", "LEAD-0001", "--to", "proposal", expect=1)   # not qualified
        self.crm("lead", "reopen", "LEAD-0001", "--to", "proposal", "--met", "need")
        text = self.read("leads/proposal/LEAD-0001-renewal.md")
        self.assertNotIn("closed", text)
        self.assertNotIn("lost_reason", text)
        self.assertIn("qualified_on: 2026-09-28", text)
        self.crm("lead", "reopen", "LEAD-0001", "--to", "new", expect=1)        # it is open
        self.crm("lead", "advance", "LEAD-0001", "--to", "contacted")           # back before qualified
        self.assertNotIn("qualified_on", self.read("leads/contacted/LEAD-0001-renewal.md"))
        self.crm("lead", "win", "LEAD-0001", expect=1)                          # not qualified
        self.crm("lead", "win", "LEAD-0001", "--met", "need")
        self.assertIn("qualified_on: 2026-09-28", self.read("leads/won/LEAD-0001-renewal.md"))
        self.crm("lead", "reopen", "LEAD-0001", "--to", "new")
        self.assertIn("status: active", self.read("accounts/acct-acme.md"))    # reopen never touches it
        self.assertEqual([h[2] for h in self.history() if h[1] == "LEAD-0001"],
                         ["new", "lose", "reopen", "advance", "win", "reopen"])
        self.assertEqual(self.errors(), [])

    def test_lead_fields_and_the_pipeline(self):
        self.seed_acme()
        self.crm("account", "new", "Globex", "--slug", "globex")
        self.config("qualification: [need]\n")
        self.crm("lead", "new", "A", "--account", "acct-acme", "--value", "1200", "--currency", "usd")
        self.crm("lead", "new", "B", "--account", "acct-acme", "--value", "300.50", "--currency", "USD")
        self.crm("lead", "new", "C", "--account", "acct-globex", "--value", "500", "--currency", "EUR")
        self.crm("lead", "new", "D", "--account", "acct-globex")
        self.crm("lead", "new", "E", "--account", "acct-acme", "--value", "99", "--currency", "USD")
        for lid in ("LEAD-0001", "LEAD-0002", "LEAD-0003"):
            self.crm("lead", "advance", lid, "--to", "proposal", "--met", "need")
        self.crm("lead", "win", "LEAD-0005", "--met", "need")
        board = self.jcrm("pipeline")
        by = {s["stage"]: s for s in board["stages"]}
        self.assertEqual(by["proposal"]["count"], 3)
        self.assertEqual(by["proposal"]["totals"], {"USD": "1500.50", "EUR": "500"})
        self.assertEqual(by["new"]["count"], 1)
        self.assertEqual(by["new"]["totals"], {})
        self.assertEqual(by["won"]["totals"], {"USD": "99"})
        self.assertEqual(board["open_totals"], {"USD": "1500.50", "EUR": "500"})
        self.assertEqual(self.jcrm("pipeline", "--account", "acct-globex")["open_totals"],
                         {"EUR": "500"})
        human = self.crm("pipeline").stdout
        self.assertIn("1500.50 USD + 500 EUR", human)
        # editing a lead: value and currency travel together (C-14)
        self.crm("lead", "set", "LEAD-0004", "value", "250", expect=1)          # no currency known
        self.crm("lead", "set", "LEAD-0004", "currency", "USD", expect=1)       # no value
        self.config("qualification: [need]\ndefault_currency: GBP\n")
        self.crm("lead", "set", "LEAD-0004", "value", "250")
        self.assertIn("value: \"250\"\ncurrency: GBP", self.read("leads/new/LEAD-0004-d.md"))
        self.crm("lead", "unset", "LEAD-0004", "currency", expect=1)
        self.crm("lead", "unset", "LEAD-0004", "value")
        self.assertNotIn("currency", self.read("leads/new/LEAD-0004-d.md"))
        self.crm("lead", "set", "LEAD-0004", "next_action_due", "+1w", expect=1)  # needs an action
        self.crm("lead", "set", "LEAD-0004", "next_action", "Call Dana")
        self.crm("lead", "set", "LEAD-0004", "next_action_due", "+1w")
        self.assertIn("next_action_due: 2026-10-05", self.read("leads/new/LEAD-0004-d.md"))
        self.crm("lead", "set", "LEAD-0004", "contact", "CARD-0001")
        self.crm("lead", "set", "LEAD-0004", "contact", "CARD-0099", expect=1)
        for protected in ("closed", "lost_reason", "qualified_on"):
            self.crm("lead", "set", "LEAD-0004", protected, "2026-09-28", expect=1)
        self.crm("lead", "rename", "LEAD-0004", "Globex pilot")
        self.assertEqual(self.find("LEAD-0004"), "leads/new/LEAD-0004-globex-pilot.md")
        self.assertEqual([l["id"] for l in self.jcrm("lead", "list", "--open")],
                         ["LEAD-0004", "LEAD-0001", "LEAD-0002", "LEAD-0003"])
        self.assertEqual([l["id"] for l in self.jcrm("lead", "list", "--stage", "won")], ["LEAD-0005"])
        self.assertEqual(self.jcrm("lead", "show", "LEAD-0001")["stage"], "proposal")
        self.assertEqual(self.errors(), [])

    def test_declared_stages_replace_the_default_funnel(self):
        self.config("stages: [enquiry, qualified, quote, won, lost]\nqualification: [fit]\n")
        self.crm("account", "new", "Acme", "--slug", "acme")
        self.assertIn("crm/leads/enquiry/", self.crm("lead", "new", "X", "--account", "acct-acme").stdout)
        self.crm("lead", "advance", "LEAD-0001", "--to", "proposal", expect=1)   # not a stage here
        self.crm("lead", "advance", "LEAD-0001", "--to", "quote", "--met", "fit")
        self.assertEqual(self.errors(), [])
        self.config("stages: [enquiry, quote, won, lost]\n")        # qualified_stage not declared
        self.assertIn("F-20", self.errors())
        self.crm("lead", "new", "Y", "--account", "acct-acme", expect=2)
        self.config("stages: [qualified, enquiry, won, lost]\n")    # the first stage cannot be it
        self.assertIn("F-20", self.errors())
        self.config("account_statuses: [lead, customer]\n")         # active_status must be one
        self.assertIn("F-20", self.errors())
        self.config("account_statuses: [lead, customer, former]\nactive_status: customer\n")
        self.crm("account", "new", "Globex", "--slug", "globex")
        self.assertIn("status: lead", self.read("accounts/acct-globex.md"))


class BirthdayTests(Base):

    def test_birthdays_next_n(self):
        self.crm("contact", "new", "Today Person", "--birthday", "1990-09-28")
        self.crm("contact", "new", "Soon Person", "--birthday", "1985-10-05")
        self.crm("contact", "new", "No Year", "--birthday", "10-01")
        self.crm("contact", "new", "Far Person", "--birthday", "1970-12-25")
        self.crm("contact", "new", "Leap Person", "--birthday", "2000-02-29")
        self.crm("contact", "new", "Wed Person", "--anniversary", "2010-09-30")
        rows = self.jcrm("birthdays", "--next", "7")          # today through 7 days out
        self.assertEqual([(r["id"], r["date"], r["in_days"], r["years"]) for r in rows],
                         [("CARD-0001", "2026-09-28", 0, 36), ("CARD-0003", "2026-10-01", 3, None),
                          ("CARD-0002", "2026-10-05", 7, 41)])
        self.assertEqual([r["id"] for r in self.jcrm("birthdays", "--next", "6")],
                         ["CARD-0001", "CARD-0003"])
        rows = self.jcrm("birthdays", "--next", "7", "--anniversaries")
        self.assertIn(("CARD-0006", "anniversary", 16), [(r["id"], r["what"], r["years"]) for r in rows])
        self.assertEqual(len(self.jcrm("birthdays")), 3)               # default: the next 30 days
        # 29 February: on 28 February in a common year, on the day in a leap year
        rows = self.jcrm("birthdays", "--next", "10",
                         env={"RASA_TODAY": "2027-02-20", "RASA_NOW": "2027-02-20T12:00:00Z"})
        self.assertEqual([(r["id"], r["date"], r["years"]) for r in rows],
                         [("CARD-0005", "2027-02-28", 27)])
        rows = self.jcrm("birthdays", "--next", "10",
                         env={"RASA_TODAY": "2028-02-20", "RASA_NOW": "2028-02-20T12:00:00Z"})
        self.assertEqual([(r["id"], r["date"]) for r in rows], [("CARD-0005", "2028-02-29")])
        self.assertIn("turns 36", self.crm("birthdays", "--next", "0").stdout)
        self.crm("contact", "archive", "CARD-0001")
        self.assertEqual([r["id"] for r in self.jcrm("birthdays", "--next", "7")],
                         ["CARD-0003", "CARD-0002"])


# ---------------------------------------------------------------------------
# vCard files
# ---------------------------------------------------------------------------

class VCardTests(Base):

    def other_project(self):
        proj = os.path.join(self.tmp, "other")
        os.makedirs(os.path.join(proj, ".claude"))
        os.makedirs(os.path.join(proj, "crm"))
        return proj

    def rich_book(self):
        self.crm("contact", "new", "Jane Doe", "--given", "Jane", "--family", "Doe",
                 "--additional", "Q.", "--prefix", "Dr.", "--nickname", "JD", "--nickname", "J, D",
                 "--org", "Acme; Inc.", "--title", "Head of Ops",
                 "--email", "work:jane@acme.example", "--email", "assistant:ea@acme.example",
                 "--phone", "mobile:+1 555 0100", "--phone", "fax:+1 555 0101",
                 "--address", "label=home;street=1 Main St;locality=Springfield;region=IL;"
                              "code=62701;country=US;pref=true",
                 "--url", "work:https://acme.example/jane?a=1,2", "--handle", "signal:+15550100",
                 "--group", "clients", "--group", "friends", "--birthday", "04-12",
                 "--anniversary", "2011-06-18", "--tz", "America/Chicago", "--lang", "en",
                 "--photo", "https://acme.example/jane.jpg",
                 "--body", "Line one, with a comma; and a semicolon.\n\nA second paragraph that is "
                           "long enough to be folded: éèêë 中文 "
                           "üöä and more text to pass seventy-five octets.")
        self.crm("contact", "pref", "CARD-0001", "email", "work")
        self.crm("contact", "new", "Globex", "--kind", "org", "--url", "https://globex.example")
        self.crm("contact", "new", "Sam Doe", "--related", "spouse:CARD-0001",
                 "--email", "sam@example.org")

    def test_export_is_vcard_4(self):
        self.rich_book()
        out = os.path.join(self.tmp, "book.vcf")
        self.crm("export", "--out", out)
        with open(out, "rb") as fh:
            raw = fh.read()
        self.assertTrue(raw.endswith(b"\r\n"))
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))           # CRLF only
        lines = raw.split(b"\r\n")[:-1]
        self.assertTrue(all(len(l) <= 75 for l in lines))           # folded at 75 octets
        self.assertTrue(any(l.startswith(b" ") for l in lines))      # and something was folded
        text = raw.decode("utf-8").replace("\r\n ", "")              # unfold
        for want in ("BEGIN:VCARD\r\nVERSION:4.0\r\n", "FN:Jane Doe", "N:Doe;Jane;Q.;Dr.;",
                     "NICKNAME:JD,J\\, D", "ORG:Acme\\; Inc.", "TITLE:Head of Ops",
                     "EMAIL;TYPE=work;PREF=1:jane@acme.example",
                     "item1.EMAIL:ea@acme.example", "item1.X-ABLabel:assistant",
                     "TEL;TYPE=cell:+1 555 0100", "TEL;TYPE=fax:+1 555 0101",
                     "ADR;TYPE=home;PREF=1:;;1 Main St;Springfield;IL;62701;US",
                     "URL;TYPE=work:https://acme.example/jane?a=1,2", "IMPP:signal:+15550100",
                     "BDAY:--0412", "ANNIVERSARY:20110618", "CATEGORIES:clients,friends",
                     "TZ:America/Chicago", "LANG:en", "PHOTO:https://acme.example/jane.jpg",
                     "NOTE:Line one\\, with a comma\\; and a semicolon.\\n\\nA second",
                     "KIND:org", "REV:20260928T000000Z", "END:VCARD"):
            self.assertIn(want, text)
        uid = re.search(r"uid: (\S+)", self.read("contacts/CARD-0001-jane-doe.md")).group(1)
        self.assertIn("UID:" + uid, text)
        self.assertIn("RELATED;TYPE=spouse:" + uid, text)
        # filters, and --out never replaces silently
        self.crm("export", "--out", out, expect=1)
        self.crm("export", "--group", "friends", "--out", out, "--force")
        with open(out, "rb") as fh:
            self.assertEqual(fh.read().count(b"BEGIN:VCARD"), 1)
        p = subprocess.run([sys.executable, "-B", CRM, "export", "CARD-0002"], capture_output=True,
                           env=self.env)
        self.assertIn(b"FN:Globex\r\n", p.stdout)

    def test_round_trip(self):
        self.rich_book()
        out = os.path.join(self.tmp, "book.vcf")
        self.crm("export", "--out", out)
        other = self.other_project()
        self.crm("import", out, env={"RASA_PROJECT_ROOT": other})
        for rel in ("CARD-0001-jane-doe.md", "CARD-0002-globex.md", "CARD-0003-sam-doe.md"):
            with open(os.path.join(other, "crm", "contacts", rel), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), self.read("contacts/" + rel), rel)
        again = os.path.join(self.tmp, "again.vcf")
        self.crm("export", "--out", again, env={"RASA_PROJECT_ROOT": other})
        with open(out, "rb") as a, open(again, "rb") as b:
            self.assertEqual(a.read(), b.read())
        self.assertEqual(self.run_(CHECK, "--json", env={"RASA_PROJECT_ROOT": other},
                                   expect=0).returncode, 0)
        # importing the same file again changes nothing: every card is already here
        d = json.loads(self.crm("import", out, "--json", env={"RASA_PROJECT_ROOT": other}).stdout)
        self.assertEqual((len(d["created"]), len(d["updated"]), len(d["skipped"])), (0, 0, 3))
        self.assertIn("same uid", d["skipped"][0]["why"])

    def test_vcard_3_with_quoted_printable_and_groups(self):
        src = os.path.join(self.tmp, "v3.vcf")
        with open(src, "w", encoding="utf-8", newline="") as fh:
            fh.write(VCARD3)
        out = self.crm("import", src).stdout
        self.assertIn("2 created, 0 updated, 0 skipped", out)
        self.assertIn("skipped embedded PHOTO data", out)
        self.assertIn("dropped its units (Research)", out)
        self.assertIn("skipped TZ '-05:00'", out)
        text = self.read("contacts/CARD-0001-dr-jurgen-muller.md")
        for want in ("name: {prefix: Dr., given: Jürgen, family: Müller}",
                     "org: Globex", "title: Chief Scientist",
                     "  - {label: other, value: juergen@globex.example, pref: true}",
                     "  - {label: work, value: j.mueller@globex.example}",
                     "  - {label: mobile, value: +49 170 1234567}",
                     "  - {label: assistant, value: +49 30 555 0101}",
                     "  - {label: work, street: Hauptstr. 5, locality: Berlin, code: \"10115\", "
                     "country: Germany}",
                     "handle:\n  - {service: aim, value: jurgen42}",
                     "birthday: --05-20", "groups: [work, science-friends]", "uid: abc-123",
                     "\n# Dr. Jürgen Müller\n\nLine one\nLine two with a long soft "
                     "break continued\n"):
            self.assertIn(want, text)
        ann = self.read("contacts/CARD-0002-ann-lee.md")
        self.assertIn("{label: home, value: (555) 010-2000}", ann)
        # a ',' inside a quoted map value is written as itself (core 1.0.1)
        self.assertIn("value: \"https://ann.example.org/a,b\"", ann)
        self.assertEqual(self.jcrm("contact", "show", "CARD-0002")["frontmatter"]["url"][0]["value"],
                         "https://ann.example.org/a,b")
        self.assertEqual([h[2] for h in self.history()], ["import", "import"])
        self.assertEqual(self.errors(), [])
        # a UID that is not a URI travels as text
        p = subprocess.run([sys.executable, "-B", CRM, "export", "CARD-0001"], capture_output=True,
                           env=self.env)
        self.assertIn(b"UID;VALUE=text:abc-123\r\n", p.stdout)
        # the same people again: deduped by UID, then by email
        out = self.crm("import", src).stdout
        self.assertIn("0 created, 0 updated, 2 skipped", out)
        self.assertIn("same uid", out)
        self.assertIn("same email", out)

    def test_vcard_4_parameters(self):
        src = os.path.join(self.tmp, "v4.vcf")
        with open(src, "w", newline="") as fh:
            fh.write("BEGIN:VCARD\r\nVERSION:4.0\r\nFN:Tom Kay\r\nKIND:org\r\n"
                     "TEL;VALUE=uri;TYPE=\"voice,home\";PREF=2:tel:+1-555-555-5555;ext=5555\r\n"
                     "TEL;VALUE=uri;TYPE=work;PREF=1:tel:+1-555-555-0000\r\n"
                     "EMAIL:mailto:tom@kay.example\r\n"
                     "IMPP;PREF=1:xmpp:tom@kay.example\r\n"
                     "BDAY:--0229\r\nANNIVERSARY:19991231T000000Z\r\n"
                     "TZ:Europe/Lisbon\r\nLANG;PREF=1:pt-PT\r\n"
                     "RELATED;TYPE=friend:urn:uuid:not-here\r\n"
                     "X-CUSTOM:ignored\r\nEND:VCARD\r\n")
        d = json.loads(self.crm("import", src, "--json").stdout)
        self.assertTrue(any("RELATED urn:uuid:not-here" in n for n in d["created"][0]["notes"]))
        fm = self.jcrm("contact", "show", "CARD-0001")["frontmatter"]
        self.assertEqual(fm["kind"], "org")
        self.assertEqual(fm["phone"], [{"label": "home", "value": "+1-555-555-5555 x5555"},
                                       {"label": "work", "value": "+1-555-555-0000", "pref": "true"}])
        self.assertEqual(fm["email"], [{"value": "tom@kay.example"}])
        self.assertEqual(fm["handle"], [{"service": "xmpp", "value": "tom@kay.example"}])
        self.assertEqual((fm["birthday"], fm["anniversary"], fm["tz"], fm["lang"]),
                         ("--02-29", "1999-12-31", "Europe/Lisbon", "pt-PT"))
        self.assertEqual(self.errors(), [])

    def test_update_folds_in_and_never_overwrites(self):
        self.crm("contact", "new", "Ann Lee", "--email", "home:ann@example.org", "--title", "Editor")
        src = os.path.join(self.tmp, "ann.vcf")
        with open(src, "w", newline="") as fh:
            fh.write("BEGIN:VCARD\r\nVERSION:4.0\r\nFN:Ann Lee\r\nEMAIL;TYPE=home:ann@example.org\r\n"
                     "EMAIL;TYPE=work:ann@paper.example\r\nTITLE:Publisher\r\nBDAY:19800101\r\n"
                     "NOTE:From the old phone.\r\nEND:VCARD\r\n")
        before = self.read("contacts/CARD-0001-ann-lee.md")
        self.crm("import", src, "--update", "--dry-run")
        self.assertEqual(self.read("contacts/CARD-0001-ann-lee.md"), before)
        d = json.loads(self.crm("import", src, "--update", "--json").stdout)
        self.assertEqual(d["updated"][0]["id"], "CARD-0001")
        self.assertIn("kept title 'Editor' (the other says 'Publisher')", d["updated"][0]["kept"])
        text = self.read("contacts/CARD-0001-ann-lee.md")
        self.assertIn("title: Editor", text)
        self.assertIn("{label: work, value: ann@paper.example}", text)
        self.assertIn("birthday: 1980-01-01", text)
        self.assertIn("From the old phone.", text)
        self.assertEqual(self.history()[-1][2], "update")
        self.assertEqual(self.errors(), [])

    def test_import_resolves_a_merged_card_and_respects_vocabularies(self):
        self.crm("contact", "new", "Jane Doe", "--email", "work:jane@acme.example")
        self.crm("contact", "new", "J. Doe", "--email", "home:jd@example.org")
        uid2 = re.search(r"uid: (\S+)", self.read("contacts/CARD-0002-j-doe.md")).group(1)
        self.crm("contact", "merge", "CARD-0001", "CARD-0002")
        src = os.path.join(self.tmp, "x.vcf")
        with open(src, "w", newline="") as fh:
            fh.write("BEGIN:VCARD\r\nVERSION:4.0\r\nFN:J. Doe\r\nUID:%s\r\nEND:VCARD\r\n"
                     "BEGIN:VCARD\r\nVERSION:4.0\r\nFN:New Person\r\nEMAIL;TYPE=pager:np@x.example\r\n"
                     "CATEGORIES:VIP\r\nEND:VCARD\r\n" % uid2)
        self.config("labels: [work, home]\ngroups: [clients]\n")
        d = json.loads(self.crm("import", src, "--json").stdout)
        self.assertIn("already here as CARD-0001", d["skipped"][0]["why"])
        notes = d["created"][0]["notes"]
        self.assertTrue(any("dropped the label 'pager'" in n for n in notes), notes)
        self.assertTrue(any("dropped the group 'vip'" in n for n in notes), notes)
        self.assertEqual(self.errors(), [])
        self.crm("import", src, "--group", "nope", expect=1)
        self.crm("import", os.path.join(self.tmp, "missing.vcf"), expect=1)
        empty = os.path.join(self.tmp, "empty.vcf")
        with open(empty, "w") as fh:
            fh.write("nothing here\n")
        self.crm("import", empty, expect=1)


# ---------------------------------------------------------------------------
# refusals — each writes nothing
# ---------------------------------------------------------------------------

class RefusalTests(Base):

    def test_actor_is_never_invented(self):
        p = self.crm("contact", "new", "x", expect=1, env={"RASA_ACTOR": ""})
        self.assertIn("who is doing this", p.stderr)
        self.config("default_actor: claude\nactors: [chazz, claude]\n")
        self.crm("contact", "new", "x", env={"RASA_ACTOR": ""})
        self.crm("contact", "new", "y", "--by", "zed", expect=1)

    def test_declared_vocabularies_are_closed(self):
        self.config("labels: [work, home, mobile]\ngroups: [clients]\ncontact_roles: [billing]\n"
                    "sources: [referral]\ntiers: [smb]\ntags: [vip]\n")
        self.crm("account", "new", "Acme", "--slug", "acme", "--tier", "smb", "--tag", "vip")
        self.crm("account", "new", "Globex", "--tier", "huge", expect=1)
        self.crm("account", "add", "acct-acme", "tags", "other", expect=1)
        self.crm("contact", "new", "A", "--email", "school:a@x.example", expect=1)
        self.crm("contact", "new", "A", "--group", "family", expect=1)
        self.crm("contact", "new", "A", "--account", "acct-acme:champion", expect=1)
        self.crm("contact", "new", "A", "--email", "work:a@x.example", "--group", "clients",
                 "--account", "acct-acme:billing")
        self.crm("contact", "add", "CARD-0001", "phone", "pager:+1 555 0100", expect=1)
        self.crm("lead", "new", "L", "--account", "acct-acme", "--source", "cold", expect=1)
        self.crm("lead", "new", "L", "--account", "acct-acme", "--source", "referral")
        self.assertEqual(self.errors(), [])
        # an undeclared value that got in by hand is caught (F-21)
        self.edit("contacts/CARD-0001-a.md", "groups: [clients]", "groups: [family]")
        self.assertIn("F-21", self.errors())

    def test_items_are_checked_before_writing(self):
        self.seed_acme()
        self.crm("contact", "new", "B", "--email", "not-an-email", expect=1)
        self.crm("contact", "new", "B", "--phone", "work:call me", expect=1)
        self.crm("contact", "new", "B", "--handle", "nohandle", expect=1)
        self.crm("contact", "new", "B", "--address", "1 Main St", expect=1)
        self.crm("contact", "new", "B", "--address", "label=home", expect=1)       # no part at all
        self.crm("contact", "new", "B", "--account", "acct-nope", expect=1)
        self.crm("contact", "new", "B", "--account", "acme", expect=1)
        self.crm("contact", "new", "B", "--related", "spouse:CARD-0099", expect=1)
        self.crm("contact", "new", "B", "--related", "cousin:CARD-0001", expect=1)  # not a vCard type
        self.crm("contact", "new", "B", "--birthday", "13-45", expect=1)
        self.crm("contact", "new", "B", "--tz", "Mars/Olympus", expect=1)
        self.crm("contact", "new", "B", "--email", "a@x.example", "--email", "A@x.example", expect=1)
        self.crm("contact", "new", "B", "--kind", "robot", expect=1)
        # one primary per account (C-08)
        p = self.crm("contact", "new", "B", "--account", "acct-acme:billing:primary", expect=1)
        self.assertIn("already has a primary contact (CARD-0001)", p.stderr)
        self.crm("contact", "add", "CARD-0001", "email", "work:jane@acme.example", expect=1)  # dup
        self.crm("contact", "add", "CARD-0001", "url", "https://x.example", "--pref", expect=1)
        self.crm("contact", "add", "CARD-0001", "related", "CARD-0001", expect=1)    # C-09
        self.crm("contact", "add", "CARD-0001", "accounts", "acct-acme", expect=1)   # C-08, twice
        self.crm("contact", "set", "CARD-0001", "email", "x@y.example", expect=1)    # a list
        self.crm("contact", "set", "CARD-0001", "merged_into", "CARD-0001", expect=1)
        self.crm("contact", "set", "CARD-0001", "bogus", "1", expect=1)
        self.crm("contact", "set", "CARD-0001", "name.middle", "Q", expect=1)
        self.crm("contact", "unset", "CARD-0001", "title", expect=1)                  # not set
        self.crm("contact", "set", "CARD-0001", "title", expect=1)                    # no value
        self.crm("contact", "pref", "CARD-0001", "url", "x", expect=1)
        self.crm("contact", "set", "CARD-0001", "title", "x", "--pref", expect=1)
        self.assertEqual(len(self.history()), 2)            # every refusal wrote nothing
        self.assertEqual(self.errors(), [])
        self.crm("contact", "add", "CARD-0001", "--pref", "email", "x@y.example")  # flags anywhere
        self.assertIn("{value: x@y.example, pref: true}", self.read("contacts/CARD-0001-jane-doe.md"))

    def test_unknown_ids_and_wrong_kinds(self):
        self.seed_acme()
        self.crm("contact", "show", "CARD-0404", expect=1)
        self.crm("contact", "show", "LEAD-0001", expect=1)
        self.crm("account", "show", "CARD-0001", expect=1)
        self.crm("lead", "win", "CARD-0001", expect=1)
        self.crm("lead", "new", "x", "--account", "acct-nope", expect=1)
        self.crm("lead", "new", "x", "--account", "acct-acme", "--currency", "USD", expect=1)
        self.crm("lead", "new", "x", "--account", "acct-acme", "--value", "12k", "--currency", "USD",
                 expect=1)
        self.crm("lead", "new", "x", "--account", "acct-acme", "--due", "fri", expect=1)
        self.crm("touch", "NOTE-0001", expect=1)
        self.crm("contact", "merge", "CARD-0001", "CARD-0001", expect=1)
        self.crm("contact", "restore", "CARD-0001", expect=1)
        self.crm("account", "new", "Bad", "--slug", "Bad Slug", expect=1)
        self.assertEqual(self.crm("contact", expect=1).returncode, 1)          # no verb: help

    def test_a_broken_config_stops_the_writers(self):
        self.config("bogus: 1\n")
        self.crm("contact", "new", "x", expect=2)
        self.assertIn("F-20", self.errors())
        self.config("labels: [a b\n")
        self.assertIn("F-20", self.errors())


class DryRunAndIdTests(Base):

    def test_dry_run_writes_nothing(self):
        self.seed_acme()
        self.config("qualification: [need]\n")
        self.crm("lead", "new", "L", "--account", "acct-acme")
        snapshot = {}
        for d, _, fs in os.walk(self.path()):
            if "/.state" in d:
                continue
            for f in fs:
                p = os.path.join(d, f)
                with open(p, "rb") as fh:
                    snapshot[p] = fh.read()
        src = os.path.join(self.tmp, "a.vcf")
        with open(src, "w", newline="") as fh:
            fh.write("BEGIN:VCARD\r\nVERSION:4.0\r\nFN:Z\r\nEND:VCARD\r\n")
        for args in (("contact", "new", "Ghost"), ("account", "new", "Ghost Co"),
                     ("lead", "new", "Ghost", "--account", "acct-acme"),
                     ("lead", "advance", "LEAD-0001", "--to", "qualified", "--met", "need"),
                     ("lead", "win", "LEAD-0001", "--met", "need"),
                     ("lead", "lose", "LEAD-0001", "--reason", "r"),
                     ("contact", "set", "CARD-0001", "title", "X"),
                     ("contact", "add", "CARD-0001", "email", "b@x.example", "--pref"),
                     ("contact", "archive", "CARD-0001"),
                     ("account", "status", "acct-acme", "active"), ("import", src),
                     ("touch", "CARD-0001")):
            self.crm(*(args + ("--dry-run",)))
        after = {}
        for d, _, fs in os.walk(self.path()):
            if "/.state" in d:
                continue
            for f in fs:
                p = os.path.join(d, f)
                with open(p, "rb") as fh:
                    after[p] = fh.read()
        self.assertEqual(after, snapshot)

    def test_ids_are_never_reissued(self):
        self.seed_acme()
        os.remove(self.path("contacts", "CARD-0001-jane-doe.md"))
        self.assertIn("CARD-0002", self.crm("contact", "new", "Next").stdout)
        self.assertEqual(self.errors(), [])
        self.assertEqual(self.warnings(), ["F-17"])            # the gone card is reported
        os.remove(self.path("accounts", "acct-acme.md"))
        p = self.crm("account", "new", "Acme again", "--slug", "acme", expect=1)
        self.assertIn("never reissued", p.stderr)
        self.crm("lead", "new", "L", "--account", "acct-acme", expect=1)


# ---------------------------------------------------------------------------
# the validator — every hand-made break, caught under the right id
# ---------------------------------------------------------------------------

LEAD = ("---\nid: LEAD-00%s\ncreated: 2026-09-28\ncreated_by: chazz\nupdated: 2026-09-28\n"
        "account: acct-acme\n%s---\n\n# L\n")
CARD = ("---\nid: CARD-00%s\ncreated: 2026-09-28\ncreated_by: chazz\nupdated: 2026-09-28\n"
        "%s---\n\n# C\n")


class InvariantTests(Base):

    def setUp(self):
        Base.setUp(self)
        self.seed_acme()
        self.config("qualification: [need]\n")
        self.check()      # seeds the content cache

    def later(self):
        return {"RASA_TODAY": "2026-10-02", "RASA_NOW": "2026-10-02T12:00:00Z"}

    def caught(self, rel, text, inv, warn=False):
        self.write(rel, text)
        found = self.warnings() if warn else self.errors()
        self.assertIn(inv, found, "%s should raise %s, got %s" % (rel, inv, found))
        os.remove(self.path(*rel.split("/")))

    def test_c01_location(self):
        self.caught("accounts/CARD-0050-c.md", CARD % ("50", ""), "C-01")
        self.caught("leads/LEAD-0050-l.md", LEAD % ("50", ""), "C-01")
        self.caught("leads/new/deep/LEAD-0051-l.md", LEAD % ("51", ""), "C-01")
        os.makedirs(self.path("accounts", "_archive"))
        self.caught("accounts/_archive/acct-old.md",
                    "---\nid: acct-old\ncreated: 2026-09-28\ncreated_by: chazz\nupdated: 2026-09-28\n"
                    "status: churned\n---\n\n# Old\n", "C-01")

    def test_c02_account_file_is_its_id(self):
        self.caught("accounts/acct-globex-corp.md",
                    "---\nid: acct-globex\ncreated: 2026-09-28\ncreated_by: chazz\n"
                    "updated: 2026-09-28\nstatus: prospect\n---\n\n# Globex\n", "C-02")

    def test_c03_stage_is_declared(self):
        self.caught("leads/negotiation/LEAD-0052-l.md", LEAD % ("52", ""), "C-03")

    def test_c04_closed_only_when_closed(self):
        self.caught("leads/won/LEAD-0053-l.md", LEAD % ("53", ""), "C-04")
        self.caught("leads/new/LEAD-0054-l.md", LEAD % ("54", "closed: 2026-09-28\n"), "C-04")
        self.caught("leads/won/LEAD-0055-l.md", LEAD % ("55", "closed: 2026-09-01\n"), "C-04")

    def test_c05_lost_reason_only_when_lost(self):
        self.caught("leads/lost/LEAD-0056-l.md", LEAD % ("56", "closed: 2026-09-28\n"), "C-05")
        self.caught("leads/won/LEAD-0057-l.md",
                    LEAD % ("57", "closed: 2026-09-28\nlost_reason: price\n"), "C-05")

    def test_c06_qualified_on(self):
        self.caught("leads/proposal/LEAD-0058-l.md", LEAD % ("58", ""), "C-06")
        self.caught("leads/new/LEAD-0059-l.md", LEAD % ("59", "qualified_on: 2026-09-28\n"), "C-06")
        self.caught("leads/qualified/LEAD-0060-l.md",
                    LEAD % ("60", "qualified_on: 2026-09-01\n"), "C-06")
        # a won lead was qualified, always; a lost one need not have been
        self.caught("leads/won/LEAD-0061-l.md", LEAD % ("61", "closed: 2026-09-28\n"), "C-06")

    def test_c07_one_preferred_item(self):
        self.crm("contact", "add", "CARD-0001", "email", "home:j@example.org")
        rel = "contacts/CARD-0001-jane-doe.md"
        self.edit(rel, "{label: work, value: jane@acme.example}",
                  "{label: work, value: jane@acme.example, pref: true}")
        self.edit(rel, "{label: home, value: j@example.org}",
                  "{label: home, value: j@example.org, pref: true}")
        self.assertIn("C-07", self.errors())

    def test_c08_one_primary_per_account(self):
        self.caught("contacts/CARD-0061-c.md",
                    CARD % ("61", "accounts:\n  - {acct: acct-acme, primary: true}\n"), "C-08")
        self.caught("contacts/CARD-0062-c.md",
                    CARD % ("62", "accounts:\n  - {acct: acct-acme}\n  - {acct: acct-acme, role: x}\n"),
                    "C-08")
        os.makedirs(self.path("contacts", "_archive"), exist_ok=True)
        self.write("contacts/_archive/CARD-0063-c.md",
                   CARD % ("63", "accounts:\n  - {acct: acct-acme, primary: true}\n"))
        self.assertNotIn("C-08", self.errors())          # archived cards do not count

    def test_c09_not_related_to_itself(self):
        self.caught("contacts/CARD-0064-c.md", CARD % ("64", "related:\n  - {who: CARD-0064}\n"),
                    "C-09")

    def test_c10_merged_into(self):
        self.caught("contacts/CARD-0065-c.md", CARD % ("65", "merged_into: CARD-0001\n"), "C-10")
        os.makedirs(self.path("contacts", "_archive"), exist_ok=True)
        self.write("contacts/_archive/CARD-0066-c.md", CARD % ("66", ""))
        self.caught("contacts/_archive/CARD-0067-c.md", CARD % ("67", "merged_into: CARD-0066\n"),
                    "C-10")
        self.caught("contacts/_archive/CARD-0068-c.md", CARD % ("68", "merged_into: CARD-0068\n"),
                    "C-10")

    def test_c11_status_is_an_account_status(self):
        self.edit("accounts/acct-acme.md", "status: prospect", "status: vip")
        self.assertIn("C-11", self.errors())

    def test_c12_won_lead_account_still_prospect(self):
        self.caught("leads/won/LEAD-0069-l.md", LEAD % ("69", "closed: 2026-09-28\n"), "C-12",
                    warn=True)

    def test_c13_same_email_on_two_live_cards(self):
        self.caught("contacts/CARD-0070-c.md",
                    CARD % ("70", "email:\n  - {value: JANE@acme.example}\n"), "C-13", warn=True)

    def test_c14_value_and_currency(self):
        self.caught("leads/new/LEAD-0071-l.md", LEAD % ("71", "value: \"10\"\n"), "C-14")
        self.caught("leads/new/LEAD-0072-l.md", LEAD % ("72", "currency: USD\n"), "C-14")

    def test_c15_status_changed_by_hand_and_fix(self):
        self.edit("accounts/acct-acme.md", "status: prospect", "status: active")
        self.assertEqual(self.errors(), ["C-15"])
        self.check("--fix")
        self.assertEqual(self.errors(), [])
        self.assertEqual(self.history()[-1][1:7],
                         ["acct-acme", "reconcile", "status=prospect", "status=active", "unknown",
                          "reconciled"])

    def test_c16_since_not_in_the_future(self):
        self.edit("accounts/acct-acme.md", "since: 2026-09-28", "since: 2027-01-01")
        self.assertIn("C-16", self.errors())

    def test_hand_move_and_fix(self):
        os.rename(self.path("contacts", "CARD-0001-jane-doe.md"),
                  self.path("accounts", "CARD-0001-jane-doe.md"))
        self.assertIn("F-16", self.errors())
        self.crm("lead", "new", "L", "--account", "acct-acme")
        os.rename(self.path("leads", "new", "LEAD-0001-l.md"),
                  self.path("leads", "contacted", "LEAD-0001-l.md"))
        os.rename(self.path("accounts", "CARD-0001-jane-doe.md"),
                  self.path("contacts", "CARD-0001-jane-doe.md"))
        self.assertEqual(self.errors(), ["F-16"])
        self.check("--fix")
        self.assertEqual(self.errors(), [])
        self.assertEqual(self.history()[-1][1:6],
                         ["LEAD-0001", "reconcile", "-", "leads/contacted", "unknown"])

    def test_unfiled_record_and_fix(self):
        self.write("contacts/CARD-0010-stray.md", CARD % ("10", ""))
        self.assertEqual(self.errors(), ["F-15"])
        self.check("--fix")
        self.assertEqual(self.errors(), [])
        self.assertIn("CARD-0011", self.crm("contact", "new", "Next").stdout)

    def test_hand_edit_without_touch(self):
        with open(self.path("contacts", "CARD-0001-jane-doe.md"), "a") as fh:
            fh.write("\nPrefers mornings.\n")
        self.assertEqual(self.errors(env=self.later()), ["F-18"])
        self.crm("touch", "CARD-0001", env=self.later())
        self.assertEqual(self.errors(env=self.later()), [])
        self.assertIn("updated: 2026-10-02", self.read("contacts/CARD-0001-jane-doe.md"))

    def test_same_day_edit_is_already_true(self):
        with open(self.path("contacts", "CARD-0001-jane-doe.md"), "a") as fh:
            fh.write("\nPrefers mornings.\n")
        self.assertEqual(self.errors(), [])

    def test_grammar_keys_refs_and_titles(self):
        cases = {
            "contacts/CARD-0020-a.md": ("---\nid: CARD-0020\ngroups: [a b\n---\n# A\n", "F-05"),
            "contacts/CARD-0021-b.md": (CARD % ("21", "bogus: 1\n"), "F-06"),
            "contacts/CARD-0022-c.md": (CARD % ("22", "related:\n  - {who: CARD-0099}\n"), "F-10"),
            "contacts/CARD-0023-d.md": ((CARD % ("23", "")).replace("# C\n", "no title\n"), "F-04"),
            "contacts/CARD-0024-e.md": (CARD % ("24", "email:\n  - {value: nope}\n"), "F-26"),
            "contacts/CARD-0025-f.md": (CARD % ("25", "birthday: --02-30\n"), "F-26"),
            "leads/new/LEAD-0026-g.md": ((LEAD % ("26", "")).replace("acct-acme", "acct-nope"), "F-10"),
            "contacts/CARD-0027-h.md": (CARD % ("27", "email:\n  - {value: a@x.example, pref: false}\n"),
                                        "F-26"),
        }
        for rel, (text, inv) in cases.items():
            self.caught(rel, text, inv)


class InstallSmokeTests(unittest.TestCase):
    """bin/init into a scratch project, then drive the INSTALLED tools with no env help."""

    def test_install_and_use(self):
        tmp = tempfile.mkdtemp()
        try:
            proj = os.path.join(tmp, "shop")
            os.makedirs(proj)
            env = {k: v for k, v in os.environ.items() if not k.startswith("RASA_")}
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            p = subprocess.run([os.path.join(ELEMENT, "bin", "init"), proj], capture_output=True,
                               text=True, env=env)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            for rel in (".claude/crm-rules.md", ".claude/crm-gate.md",
                        ".claude/schemas/crm/card.schema.json", ".claude/schemas/crm/account.schema.json",
                        ".claude/schemas/crm/lead.schema.json", ".claude/schemas/crm/config.schema.json",
                        ".claude/skills/contact/SKILL.md", ".claude/skills/account/SKILL.md",
                        ".claude/skills/lead/SKILL.md", ".claude/bin/crm", ".claude/bin/check-crm",
                        ".claude/bin/rasa_crm/records.py", ".claude/bin/rasa_crm/vcard.py",
                        ".claude/bin/rasa_crm/FAMILY", "crm/crm.config.yml", "crm/history.tsv",
                        "crm/contacts/.keep", "crm/accounts/.keep", "crm/leads/new/.keep",
                        "crm/leads/won/.keep", "crm/leads/lost/.keep", ".claude/rasa.lock.json"):
                self.assertTrue(os.path.exists(os.path.join(proj, rel)), rel)
            for gone in (".claude/skills/sync", ".claude/skills/promote", ".claude/skills/whoami",
                         ".claude/rasa-identity.md", ".claude/rasa-deployment.md", "kit",
                         "crm/ACCOUNTS.md", "crm/CONTACTS.md", "crm/LEADS.md"):
                self.assertFalse(os.path.exists(os.path.join(proj, gone)), gone)
            with open(os.path.join(proj, ".claude", "rasa.lock.json")) as fh:
                json.load(fh)
            tool = os.path.join(proj, ".claude", "bin", "crm")
            chk = os.path.join(proj, ".claude", "bin", "check-crm")

            def run(*args):
                r = subprocess.run([tool] + list(args), capture_output=True, text=True, cwd=tmp,
                                   env=env)
                self.assertEqual(r.returncode, 0, "%s\n%s" % (" ".join(args), r.stderr))
                return r.stdout
            # run from somewhere else entirely: the tool finds its own project
            self.assertIn("crm/accounts/acct-corner-bakery.md",
                          run("account", "new", "Corner Bakery", "--by", "owner1"))
            self.assertIn("crm/contacts/CARD-0001-maria-rossi.md",
                          run("contact", "new", "Maria Rossi", "--email", "work:maria@bakery.example",
                              "--account", "acct-corner-bakery:buyer:primary", "--by", "owner1"))
            run("lead", "new", "Weekly bread order", "--account", "acct-corner-bakery",
                "--value", "400", "--currency", "EUR", "--by", "owner1")
            cfgp = os.path.join(proj, "crm", "crm.config.yml")
            with open(cfgp) as fh:
                cfg = fh.read()
            with open(cfgp, "w") as fh:
                fh.write(cfg.replace("# qualification: []", "qualification: [order-confirmed]"))
            run("lead", "win", "LEAD-0001", "--met", "order-confirmed", "--by", "owner1")
            vcf = os.path.join(tmp, "out.vcf")
            run("export", "--out", vcf)
            self.assertTrue(os.path.exists(vcf))
            r = subprocess.run([chk], capture_output=True, text=True, cwd=tmp, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse(any("__pycache__" in d for d, _, _ in
                                 os.walk(os.path.join(proj, ".claude"))))
            # re-init is non-destructive for everything the project owns
            with open(os.path.join(proj, "crm", "crm.config.yml"), "a") as fh:
                fh.write("default_actor: owner1\n")
            p = subprocess.run([os.path.join(ELEMENT, "bin", "init"), proj], capture_output=True,
                               text=True, env=env)
            self.assertEqual(p.returncode, 0)
            with open(os.path.join(proj, "crm", "crm.config.yml")) as fh:
                self.assertIn("default_actor: owner1", fh.read())
            with open(os.path.join(proj, "crm", "history.tsv")) as fh:
                self.assertEqual(len(fh.read().strip().split("\n")), 6)
            self.assertTrue(os.path.exists(os.path.join(proj, "crm", "leads", "won",
                                                        "LEAD-0001-weekly-bread-order.md")))
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
