# content/ — what `rasa.module.crm` installs

Everything under `content/` is Element-owned: refreshed on every upgrade,
never project state. `bin/init` reads `rasa.json` and applies each entry by
its policy; this table mirrors the manifest and must change with it.

| from | to | policy | what |
|---|---|---|---|
| `content/crm-rules.md` | `.claude/crm-rules.md` | file-replace | the law: the records-family/1 conventions + the crm law |
| `content/schemas/` | `.claude/schemas/crm/` | directory-mirror | JSON Schemas: card, account, lead, config |
| `content/skills/` | `.claude/skills/` | directory-mirror | `/contact`, `/account`, `/lead` |
| `content/bin/` | `.claude/bin/` | directory-mirror | `crm`, `check-crm`, and the `rasa_crm/` package |
| `content/README.md` | — | opt-in | this file (not installed) |
| `content/BUILD_PLAN.md` | — | opt-in | the design record (not installed) |

Project-owned, copied once (`seed/`, never overwritten):

| from | to | policy |
|---|---|---|
| `seed/crm-gate.md.template` | `.claude/crm-gate.md` | skip-if-exists |
| `seed/crm/crm.config.yml.template` | `crm/crm.config.yml` | skip-if-exists |
| `seed/crm/history.tsv.template` | `crm/history.tsv` | skip-if-exists |
| `seed/crm/contacts/.keep` | `crm/contacts/.keep` | skip-if-exists |
| `seed/crm/accounts/.keep` | `crm/accounts/.keep` | skip-if-exists |
| `seed/crm/leads/new/.keep` | `crm/leads/new/.keep` | skip-if-exists |
| `seed/crm/leads/contacted/.keep` | `crm/leads/contacted/.keep` | skip-if-exists |
| `seed/crm/leads/qualified/.keep` | `crm/leads/qualified/.keep` | skip-if-exists |
| `seed/crm/leads/proposal/.keep` | `crm/leads/proposal/.keep` | skip-if-exists |
| `seed/crm/leads/won/.keep` | `crm/leads/won/.keep` | skip-if-exists |
| `seed/crm/leads/lost/.keep` | `crm/leads/lost/.keep` | skip-if-exists |
| `seed/rasa.lock.json.template` | `.claude/rasa.lock.json` | init-only-with-sha |

The package: `records.py` is the records-family/1 core, byte-identical in
notes, schedule, crm and messages; `FAMILY` records its hash and the hash of
the family block in `crm-rules.md`. `model.py` holds the paths, record types
and config defaults; `fields.py` the field-editing grammar
(`label:value`, `k=v;k=v`); `vcard.py` vCard 4.0 export and 3.0/4.0 import;
`validate.py` the C-invariants (also run by the tool before every write);
`cli.py` the verbs.
