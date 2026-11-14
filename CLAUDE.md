# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Working on Project Kustos

Notes for Claude Code sessions on this repository, on any of the owner's machines.

## What this is

`_kustos.py` is the whole program: Python 3.10+ standard library only, a Tk
interface, a single file. The data lives in `_kustos.json` (the source of
truth) beside per-machine append-only logs `_kustos.log.<host>.jsonl`, a lock
file and a markdown mirror. See `README.md` for the features.

## Commands

There is no build, linter or test suite; the checks are:

```
python -m py_compile _kustos.py     # syntax (tools/update-instance.cmd runs it too)
python _kustos.py doctor            # structure of the base: must report 0 errors
python _kustos.py                   # open the window (needs Tk and a display)
python _kustos.py help              # any unknown command prints the full usage (__doc__)
```

The other subcommands (`mirror`, `search`, `history <id>`, `replay`, `merge`,
`cite`, `export`, `import`, `health`, `corpus`...) are listed in the module
docstring and dispatched in `main()` near the end of the file.

The program works on the folder **it sits in** (`BASE = Path(__file__).parent`),
not the current directory. To test on a temporary copy, copy `_kustos.py` into
that copy and run it from there; running the repository's file against an
empty repository folder gives an empty base (and `doctor` passes on it).

## Architecture

`_kustos.py` is split into sections marked `# ==== <name>`, in this order:
language (`tr`), common, the collections (**people** `p_`, **verba**
`c_`/`f_` concepts and forms, **sources** `s_`, **corpus** `h_` health
records, **notes** `n_` — shown as "drafts", **res** `r_` things), geo, observator,
observations, then file, register, conflicts, lock, doctor, mirror, search,
history, migration, upgrade, citation, health report, peritia, web, themes, motion,
the Tk `*Card` editors, `App` (the main window), `BookView` (the logbook), the
`cmd_*` functions and `main()`, and finally the `PT` dict.

Ideas that span several sections:

- **Saving is per record.** `save_record`/`delete_record` reread the JSON,
  replace only that record, write atomically through `write_json`, then append
  to this machine's log. `write_json` is the single choke point: it also numbers
  new records (`register_new`). Never write the JSON another way.
- **`load_json` is cached** as a `marshal` blob keyed by the file's
  (mtime, size), so callers get a fresh copy cheaply; a change on disk
  (another save, Syncthing) invalidates it.
- **`fix_*` functions** (`fix_vault`, `fix_person`, `fix_entry`, `fix_source`,
  `fix_metric`) fill defaults on every read; new fields get their default there.
  Changes to the stored shape bump `SCHEMA` and get a step in `upgrade_vault`,
  which runs on open.
- **Sync conflicts** (`*.sync-conflict-*`) are merged record by record on open,
  newest `updated_at` wins, deletions are kept as tombstones in `deleted`.
- **The register**: every record has a `reg` stamp and a `reg_n` number that
  never changes and is never reused (see the comment at `# ==== register`).
- **Links** live in a top-level `edges` list (`from`, `to`, `rel`), not inside
  records; `RELS` defines the types. `write_link` adds, changes or removes one
  link as a save of the record it comes from (the web page and the window's
  graph both write through it; it refuses a RELS type that does not fit the two
  records, as the doctor would). What a line shows -- family colour, age from
  the logs (`edge_times`, cached), stroke by evidence, taper by direction -- is
  `link_facts`, shared by both graphs. The path finder's chains come from
  `link_paths` (breadth-first over `graph_adjacency`, `PATH_LIMIT` shortest,
  `PATH_MAX` links at most), also shared: the web asks `web_path`, the window
  calls it in `GraphView.show_path` (`f` opens `PathDialog`, Ctrl+click a
  record).
- **Contacts** are lines of a record's `links` (URLS), kept as typed and read
  by `contact_line` (label, kind, `href`, WhatsApp `chat`) for the window's
  buttons (`PersonCard.show_contacts`), the page (`contacts` in `web_record`)
  and the mirror (`contact_md`). Only https, mailto, tel and sms are ever
  opened (`open_address`). **Organizations** are people with `org: true`:
  `kind_of` still says person, so every older link type fits them, and
  `kind_fits` checks the `org` end of RELS (`works_at`, `member_of`) for the
  doctor, `typical_rels` and `write_link`; `graph_kind` makes them hexagons.
  A person's card has its own LINKS (`PersonCard.t_edges`, saved by
  `_save_person` with `edges=`), as every other card; on the page, a form
  without `edges` (a tab opened before) keeps the person's links.
- **A link's circle** (`circle` on an edge, `@influence` in its line, one of
  `CIRCLES`): where the target sits in the circles of the record the link
  starts from. `parse_edges`/`format_edges` read and write it, `write_link`
  checks it, `link_rel_text` shows it in every list, `search_base` answers
  `circle:` (a person's own circles, or either end of such a link).
  **Inverse lines** (`INVERSE_RELS`: `cited_by`, `influenced_by`) are read by
  `take_links`, which every save path uses (the window's `_save_*` and the
  page's `web_links`), and saved after the record by `write_inverse_links`
  through `write_link`, as a save of the record they start from, so the log,
  replay and conflict merges stay right; one that does not fit stays a draft.
  RELS ends may list alternatives (`"source|person"`, read by `kind_fits`).
- **Res** (`# ==== res`): the things of the house, wired as the corpus is --
  an internal type `rtype` (`RES_TYPES`: `item`, `account`; `kind_of` gives
  it, `graph_kind` gives `item` for both, a pentagon on the graphs),
  `fix_res`, `new_res_id`, `haystack_res`, the page's fields with their
  `only`, and `ResCard` in the window, one block per type (`App.new_item`,
  `App.new_account`, Ctrl+6, the rail's THINGS). The type is chosen when a
  record is made and never changes (no TYPE choice on the card; the page's
  *New* has one entry per type). A new type adds itself to
  `RES_TYPES`/`RES_TYPE_LABEL`, its defaults in `fix_res`, its block on the
  card, its `gather` branch and its fields with their `only`.
  Items: CATEGORY is free text whose suggestions (`RES_CATEGORIES`) are stored
  by their English key (`res_category_key`/`res_category_label`); STATUS is a
  key of `RES_STATUSES`. `save_record` stamps `status_since` when the status
  changes (`res_stamp_status`) unless the date was typed; `res_reminders`
  (`RES_WARRANTY_DAYS`, `RES_LENT_DAYS`) feeds the list's `(!)`, the page's
  `warn`, the rail's *need attention* and a notice when the window opens.
  Links: `lent_to`, `bought_from` (an `org`), `manual_in`, `kept_in`,
  `paid_from` (item -> account).
- **Accounts** (`# ---- accounts`, inside res): money is `decimal.Decimal`,
  never float. ENTRIES are stored inside the account as `{date, amount,
  text}` (amount a canonical decimal string, text as typed with its marks),
  as readings are; a line that does not read is kept as `{"raw": line}`.
  `parse_entries`/`entry_line` read and write the card's lines,
  `parse_amount` holds the rule for values (sign required; with `.` and `,`
  the last is the decimal mark; a lone mark before exactly three digits is
  refused; `AMOUNT_WHOLE`/`AMOUNT_DECIMALS` digits at most), `amount_typed`
  writes values back so they read the same, `money` shows them. OPENING
  BALANCE is stored canonical by `account_opening`, or as typed when it does
  not read, so it is always read by `opening_of` (the same rule), never by
  `amount_of`: a kept `1.500` must not become 1.5. `entry_marks`: `#category`, `→`/`->` refs, `> r_…` transfers.
  `ledger_index` reads every account once (cached while the records and
  their `entries` lists are the same objects) and computes the other half of
  each transfer (`in`); `account_summary` gives balance, months, categories,
  largest outflows and a card's statement (current calendar month), from the
  stored entries or from the lines being edited; `account_report` turns it
  into lines for the card, mirror and logbook, `web_ledger` for the page.
  LAST 4 (`last4_ok`) is refused on every save path and an error for the
  doctor (`check_account`): a full number must never be stored. Accounts stay
  out of `MONAD_COLLS` and out of `geojson` unless `--all` (`geo_features`).
  `cmd_ledger` writes hledger or beancount (`ledger_transactions`,
  `ledger_journal`, names made ASCII by `ledger_component`); check a change
  to it with a script that sums each transaction per commodity.
- **Monads** (`# ==== monads`): read-only view; `MonadIndex` weighs shared words
  and links, `MonadView` draws them with no lines. `MONAD_COLLS` keeps health,
  drafts and res out, also as bridges between records; keep it that way. To measure its
  frames, time the moves themselves: `update()` does not return while two tweens run.
- **Practice** (`# ==== practice`, the web app's `#practice`): `drill_items`
  makes an item of a concept in one language (its forms that `express` it) or
  of a gloss (forms linked to no concept, same language and gloss);
  `drill_grade`, five boxes (`DRILL_BOXES`), `DRILL_NEW_PER_DAY`. Answers go
  to `DRILL_LOG` per machine (`_kustos.drill.<host>.jsonl`, ignored by git),
  never into records. `DRILL_LANGS` maps a base's language codes to names,
  browser speech tags and Piper locales -- not to be confused with `LANGS`,
  the interface's languages. Piper (`cmd_voices`) is optional and imported
  only in `voices_make`; voices and recordings are under `LOCAL_DIR`
  (`VOICE_DIR`, `AUDIO_DIR`, `VOICE_CONF`), served by `/api/drill/audio`
  with the page's token; `voices_soon` starts `voices make` in its own
  process when a practice begins. The page plays a recording, else the
  device's own voice (`localService` only, never one that sends text out).
  `parse_bulk_concepts`/`save_bulk_concepts` read the bulk entry's
  `name | gloss: form (lang); …` lines. Test with Piper stood in for (no
  voice can be downloaded in the cloud session) and in a headless browser.
- **Peritia** (`# ==== peritia`): the skills panel is a page of the web app
  (`cmd_web`): `/skills`, from the template `PERITIA_HTML` (strings as
  `@@English@@`, translated by `tr` when the page is built; `@@NONCE@@` gives
  its one script the page's nonce), with the same token, Host check and
  content policy as the base's page; its calls go to `/api/skills/…`, which
  the server hands to `peritia_api`. `cmd_peritia` only opens the web app on
  that page. Skills are the top-level list `skills` (`k_`), the panel's
  parameters are in `peritia`; they save, log, merge and replay like records
  but stay out of `COLLS` and the register. A record's page lists its skills
  (`record_skills`). Test it on invented data with `peritia_api(...)`, or in a
  headless browser against `web --stay`.
- **Web** (`# ==== web`): `cmd_web` serves the whole base the same way, from
  `WEB_HTML` (its strings come in the boot data as `T`, from `WEB_STRINGS`,
  translated by `tr`). The page edits the text the window's cards hold and
  `web_gather` reads it back with the same parsers (`parse_log`,
  `parse_tasks`, `parse_edges`...), then `save_record`: a change to a card's
  fields or to how it saves belongs in both places. Search and list rows are
  shared with the window (`parse_search`, `search_base`, `list_row_text`).
  Test it on invented data with `web_api(...)`, or run it with `--stay` and
  drive the page in a headless browser. The page's link graph gets its records
  from `web_graph` (`graph_adjacency`, `graph_ego`, as the window) and draws
  them itself; its life, glow and still rules, its springs and the way changes
  are drawn are the window's `GraphView` ones rewritten in JavaScript, so a
  change to one belongs in the other. Both: life's generations last 1.2 s and
  the run rests when the pattern settles; changes grow, wither and flow (light
  along the links into a birth) instead of jumping; every brightness eases;
  the springs take damped steps that keep half of the last one, and dragging
  holds the view still -- full-temperature steps made every record shake
  around its place, which read as flicker. The window's graph also has the
  page's controls (`GraphView.segment`/`button`, kept in step with the state by
  `sync_buttons`, called from `update_status`), its labels on the focus's
  links and its curve of how many are lit. Tk draws no soft edges: its solid
  lines are smooth polygons with a lighter rim (`RIM`) and a core never under
  2 px (`MIN_HALF`), or Tk's fill comes and goes along them and they read as
  dashed. Check a change to them on a big invented base (frame time) and by
  eye, enlarged.
- **The login** (`web --serve`, under `# ---- the login` before `cmd_web`):
  the long-running web app for the owner's devices through Tailscale. Every
  page and call needs a session (`Handler.session`; `/login` and
  `/api/login` are the only ways in), and every call still carries the
  session's own token (`csrf`) in `X-Kustos-Token`. Password hash (scrypt)
  and TOTP secret live in `AUTH_FILE` under `%LOCALAPPDATA%\Kustos`, never in
  the synced folder or git; `cmd_passwd` writes it, `auth_set` changes the
  `version` that ends old sessions. Sessions are in memory; wrong logins sleep
  and count towards `lock`; `access_log` writes `ACCESS_LOG` beside it. Keep
  the plain `web` (the window's, Peritia's) working without a login, and keep
  every server on 127.0.0.1. Test with `LOCALAPPDATA` pointed at a scratch
  folder, never at a real one.
  `cmd_service` (`_kustos_serve.cmd`) makes it start at every Windows login: a
  scheduled task (`SERVICE_TASK`, PowerShell scripts `PS_*` that get their
  values as `$env:KUSTOS_*`, never spliced in), `--allow-host` the machine's
  MagicDNS name (`tailscale_name`), `tailscale serve --bg 8484` in front, and
  `serve_answers` to check the login answers. Test it with `run_ps`,
  `run_tailscale` and `sys.platform` stood in for.
- **The backup** (`cmd_backup`, `_kustos_backup.cmd`): restic, never crypto
  of our own. `BACKUP_FILE` (under `%LOCALAPPDATA%\Kustos`) holds the
  repository and its password sealed by `seal` (Windows DPAPI, ctypes);
  `backup_run` is what the daily task (`BACKUP_TASK`) runs: backup, then
  when due `forget --prune` (`BACKUP_KEEP`), `check --read-data-subset=5%`
  and `backup_restore_test`, which restores into a temporary folder (its
  caches redirected there too), runs that copy's doctor and deletes it.
  `BACKUP_STATE` feeds `backup_notice`, shown when the window opens. Test it
  with the real restic, `seal` and `run_ps` stood in for, `LOCALAPPDATA` and
  the repository in scratch folders.
- **GEO** (`# ==== geo`): a field of every record but the drafts, kept as
  typed (points `lat, lon` one per line, or GeoJSON pasted whole) and read by
  `parse_geo` into GeoJSON geometries only when needed: the card's hint
  (`App.geo_field`, `geo_put`), the doctor (warnings, never errors), the
  mirror, `is:geo`, and `cmd_geojson`, which leaves health out unless `--all`.
  Keep it offline: no geocoding and no tiles (the page's CSP is
  `default-src 'none'`). A new collection with a GEO joins `GEO_COLLS`.
- **The map** (`# ==== map`, Ctrl+Shift+L, `map [id]`, the page's `#map`):
  `map_features` (all of `GEO_COLLS`, accounts too; `geojson` keeps its own
  rule) feeds `MapView` and `web_map` alike; the outline is
  `kustos_basemap.json`, read lazily by `load_basemap` and served to the page
  by `/api/basemap` with the token, never fetched from anywhere. It is made by
  `tools/make_basemap.py` (Natural Earth, a pinned release; the only network
  call, run by hand) and versioned; the map works without it. `MapView`
  follows the window's search as the timeline does (`timeline_ids`,
  `timeline_soon`), the chosen record drawn even outside it; only a new
  search (`filter_sig`, its `get_key`) moves the view, not a save that
  changes what it finds. A gesture only `move`s or `scale`s the canvas, and
  `draw` runs once it stops. Tk fills a polygon even-odd: an area's holes
  join its outer ring in one polygon, its edges drawn as lines. The
  basemap's checks refuse what is not a finite position on the Earth.
  Tk 9 costs ~50-100 µs a canvas item to draw
  on every step, whatever its size: keep the item count down (markers that
  would overlap are one, `MAP_MOVING_MARKS` while moving, no borders below
  `MAP_BORDERS_K`), and time a change on 2 000 invented points. The page's
  `mRender` is the same drawing as SVG, transformed while it moves.
- **Observator** (`# ==== observator`): `ui.observator` is the p_ id of the
  person this instance belongs to (derived once from `ui.corpus_subject` by
  `observator_default`, in `upgrade_vault` and on open). `save_record` stamps
  `observator` on the record and on the links that are new in that save (an
  old link keeps who made it); `log_append`/`log_many` put `obs` beside `host`,
  kept current by `_remember_disk` (`_OBS`), so the cached vault never leaves
  it stale. The eye is drawn from one set of points (`eye_points`): `draw_eye`
  on a Tk canvas (status bar, `App.draw_observator`), `observator_svg` for the
  page (header and record kicker, from `web_observator` in the boot data).
  States: own / alienus (dashed lids: signed by someone else) / unsigned (no
  mark). Nothing is rewritten on its own: an unsigned record stays so until
  saved. The doctor warns, never errors. `cmd_observator` sets or shows it.
  **Signatures** (`# ---- signing the logs`): a person's `gpg` holds an
  OpenPGP fingerprint as typed (`gpg_fpr` reads it). `cmd_sign` makes one
  detached signature per run over a manifest (`sig_manifest`: who, machine,
  the canonical `line_hash`es of the lines not signed yet) into `SIG_FILE`
  (`_kustos.sig.<host>.jsonl`, ignored by git); `cmd_verify`/`verify_batch`
  check every machine's against its log and the key the observator's record
  names. GnuPG is optional and only called there (`gpg_run`). Test with a
  throwaway keyring: `GNUPGHOME` in a short `%TEMP%` folder (the agent's
  socket path has a length limit), a key made with `--quick-gen-key` and no
  passphrase, never the owner's own.
- **Observations** (`# ==== observations`, before `# ==== file`): the top-level
  list `observations` (`o_<stamp>_<6 hex>`), a satellite like `skills`
  (`SATELLITES`): saved, logged, merged (`merge_vault`, `absorb_conflicts`)
  and replayed like records, but out of `COLLS` and the register;
  `fix_observation` fills its defaults, no SCHEMA step. Fields: `observator`,
  `t`, `updated_at`, `targets` (record ids), `kind` (`OBS_KINDS`: distinguo,
  reobservo; alinho, proponho are accepted for later steps), `auto`,
  `distinction`, `criterion` (text or `c_…`), `confidence` (1-3 or null),
  `source`, `changed`, `before`, `prev` (the `updated_at` of the version
  `before` describes), `status`, `notes`. `save_record` calls `observe_save`
  for every record of COLLS saved while there is an observator: a
  `distinguo` on the first save, a `reobservo` with `changed`/`before`
  (`obs_diff`; bookkeeping keys in `OBS_IGNORED` are not changes; `links`
  when the outgoing links differ), written in the same `write_json` and
  logged with the record in one `log_many`. **Coalescing**: one automatic
  observation per record, observator and local day -- a later save that day
  updates it (union of `changed`, the earliest `before` kept; a distinguo
  stays one). A value over `OBS_BEFORE_MAX` characters of compact JSON is
  stored as null and `reobserve` reads it back from the logs
  (`log_lines_of`, `logged_state` by `prev`). `add_observation` (the
  window's `ObserveDialog`, Ctrl+Shift+O, and the page's `/api/observe`) makes
  deliberate ones, never coalesced; `delete_observation` (`/api/observe/delete`)
  deletes only one's own deliberate ones, with a tombstone. `record_observations`
  is the one list the dialog, the page and `reobserve` show. `obs_index`,
  `obs_recent`, `obs_stats` and `obs_crit_text` are cached per observations
  list and day (`_OBS_CACHE`): they feed `is:reobserved`, `crit:`, the card's
  line, the status bar's *re-obs* and `observe`. The doctor only warns.
  Observations of health (`h_`) records and of accounts carry their earlier
  values: any later export must leave them in the base.
- **Proposals** (`# ---- proposals`, at the end of `# ==== observations`):
  `save_record` is now `put_record` (the work on a vault in memory, returning
  the log lines) plus the write and the log; both take `proposed`, `sign` and
  `aside`. A batch (`import_sources`, `sign_proposals`) passes `put_record` an
  `at` from `put_index`, so each record, tombstone and today's observation is
  found once, not once per record: keep a new per-record scan out of
  `put_record`, or give it a place in `at`.
  `proposed` (the imports through `import_sources(..., proposed=True)`, which
  `cmd_import_zotero` and `import <file.bib|.json>` use, and
  `save_bulk_concepts`, also through `write_link(..., proposed=True)`) keeps a
  new record's `observator` "" (a record already there keeps its own) and its
  new links unsigned, and `propose_save` adds (or updates) a `proponho` with
  `status: "proposed"`, no observator, `auto`, no distinguo, and `links`: the
  [rel, to] of the links it brought. `sign` (`sign_proposals`: the window's
  `sign_open`, `/api/sign`, `sign-proposals`) stamps an unsigned record, and
  `seal_proposal` the proponho's `links` still unsigned (an older unsigned
  link keeps nobody) and turns the proponho `signed` with `observator` and
  `signed_at` (kind stays proponho); obs_diff ignores `observator`, so no
  reobservo. A save of a pending proposal by the observator that changes
  something signs it (and its reobservo is against the proposed version); one
  that changes nothing keeps it a proposal, and so does `aside`
  (`write_inverse_links`: a line typed on another record's card). A pending
  proponho counts in no tally (`obs_looked`, `recent` in `_obs_cache`), and no
  later save coalesces into a proponho (`obs_coalesces`). `proposal_of` finds a
  record's pending one (looked for only when the record is unsigned, or on
  `sign`, so the ordinary save pays nothing), `obs_proposed` (in `_OBS_CACHE`)
  feeds `is:proposed`, the card's line, `proposal_info` for the page and
  `check_proposals` (warnings: pending over `PROPOSAL_DAYS`, or a proposal
  whose signing did not take, the record or the links it brought left
  unsigned by another machine's save -- `proposals_astray`, which
  `sign_proposals` signs again, with `sign_brought`). `proposal_brought` is
  the one reading of a proponho's `links` (one written without them brought
  every unsigned link). The page and the window sign with the stamp the
  record was shown with (`base`): one changed since is a WebConflict.
- **doctor --observe** (`# ---- doctor --observe`, after `cmd_doctor`):
  `observe_audit(data, days, seen)` returns the sections, `cmd_doctor_observe`
  prints them; it must stay read-only -- `load_json`, `seen_read` and no
  write of any kind. Test it on invented data in memory (`seen={}`).
- **Long texts are markdown**: `textfield(..., pages=True)` (every NOTES and the
  draft's text) gets `MarkdownKeys`, and `fit(opening=True)` paints it before
  the pages are measured. The text stored stays plain.
- **Motion** (`# ==== motion`): the timings are constants there, and `tween`
  follows the clock. Animate a tag's colour, not a Text's options: `configure`
  on a Text costs ~20 times as much per frame.
- **Dust off** (`App.dust_off`, Ctrl+D): opens the record of the list
  (`self.view`) gone longest without a visit, by `dust_order` (`last_visit`:
  the later of a visit and `updated_at`). Visits live outside the JSON, in
  `_kustos.seen.<host>.json` per machine (`seen_read` merges all of them,
  `seen_write` rereads this machine's before writing; ignored by git as
  `_kustos.*.json`); a card counts as visited after `DUST_DWELL_MS` open
  (`dwell_done`), and `flush_seen` writes them a moment later and before the
  window goes. Never write a visit into a record: it would save, log and
  sync on every open.
- **The wide card's search** (F11, then Ctrl+F): `quick_*` methods show the
  index's results (`self.view` after `refresh_list`) in a frame placed over
  the card under the search; the search entry's keys go to it while it is
  shown (`entry_key`, `entry_escape`), and `search_changed` refreshes it.
- **The logs are the history**: `history <id>` and `replay` (rebuilds the base
  from logs into `_kustos.replay.json`) read them; there are no `.bak` files.
- **Drafts live in files**: the `notes` collection is an index (id, title,
  file, tags, register number); the text of each draft is a markdown file in
  `notes/` with a small header, also read by Obsidian. `index_notes` takes in
  new or moved files; saving writes the file and logs the text as a `text`
  line (ignored by `replay`). The texts are cached per machine in
  `%LOCALAPPDATA%\Kustos` by mtime and size. Test drafts only with invented
  `.md` files, never real notes.

## The two instances

- **Dev**: this repository, public on GitHub: anyone can read it, so nothing
  personal goes into the code, the docs or the commit messages either.
- **Instance**: a separate folder, outside this repository, which holds the
  program *and the owner's data*. Its location is not recorded here.

The rules, in order:

1. **The instance comes first and must stay safe.** The program is for
   the owner's own use.
2. **Both instances always run the same, latest program.**
3. **The owner's data never goes to GitHub.** `.gitignore` keeps out `_kustos.json`,
   logs, locks, mirrors, reports, conflicts and Syncthing files; never add them,
   and never copy real records into tests, fixtures or examples.

## How a change is made

1. Edit `_kustos.py` here, in the repository.
2. Test on a **temporary copy** of the personal data (a `kustos_*` folder in
   `%TEMP%`), never on the instance itself; delete the copy, and any
   screenshots, afterwards. Health data is sensitive. Or test on invented
   records: `python tools/demo_base.py <folder>` builds the web demo's base
   through Kustos's own save functions (`tools\demo.cmd` opens it in
   `%TEMP%\kustos_demo`); its pictures can be shared, and it refuses a folder
   it did not make.
3. `python _kustos.py doctor` must report 0 errors.
4. Commit with an English message ending in
   `Co-Authored-By: Claude <noreply@anthropic.com>`, then push.
5. Copy to the instance (`tools\update-instance.cmd`, or copy
   `_kustos.py`, `_kustos.cmd`, `_kustos_logbook.cmd`, `_kustos_peritia.cmd`,
   `_kustos_serve.cmd`, `_kustos_backup.cmd`, `kustos.ico`,
   `kustos_basemap.json`) **only when
   Kustos is closed** — check that no `python`/`pythonw` process is running, or
   ask the owner — then verify the copies match (ignoring CRLF/LF). The
   always-on `web --serve` (task *Kustos web*) does not count: it holds nothing
   unsaved, and `update-instance.cmd` restarts it after copying
   (`service restart --quiet`).

Force pushes are run by the owner, not by Claude.

## Conventions

- Code, comments, commit messages and docs are in **English**. Portuguese is an
  optional interface language: strings go through `tr(...)` and their
  translation into the `PT` dict at the end of the file. A `tr` placeholder must
  not be called `text` (it clashes with `tr`'s own parameter).
- Stored data keys stay as they are, even the Portuguese ones (`reg_origem`,
  `reg_n_anterior`): renaming them would break existing bases.
- Keep it fluid: the list pages instead of scrolling (`rows_fit`, `turn`),
  searching is debounced, and heavy work (the mirror) runs in the background.
  Measure before and after a change that touches typing or redrawing.
- A touchpad sends many small wheel events where a mouse sends one a notch:
  never move a fixed step per event. Amounts (a zoom, a scroll) take
  `wheel_units(e)`; steps (a page) count with `WheelNotches` / `wheel_turn`.
  The page's graph does the same in `gWheelZoom`.
  A card's wheel goes through one window-wide handler, `App.card_wheel`,
  which finds the card from the widget under the pointer (Tk sends the wheel
  there on every system); do not switch wheel handlers on Enter/Leave --
  a click could leave one off.
  Over a card the vertical wheel scrolls the card, whatever field is under
  the pointer; a long (paged) field turns its pages with a sideways swipe or
  Shift+wheel, or with the wheel once the card is at its end (a new gesture,
  so one that only reaches the end does not spill into page turns). A field
  that scrolls inside (Continuous, `ui.max_rows`) does the same; `text_wheel`
  replaces Tk's own Text wheel so a card's field never scrolls by itself, and
  a `TCombobox` has no wheel at all -- it changed a record's type in passing
  (`python tools/dropdown_check.py <folder>` lists, read-only from the logs,
  every change of a drop-down value, marking those saved alone).
  From Tk 9 (Python 3.13 and later on Windows; the owner runs 3.14 / Tk 9)
  a touchpad comes as `<TouchpadScroll>`, in pixels with dx and dy packed in
  `delta` (`touchpad_deltas`); only a mouse wheel's notches stay
  `<MouseWheel>`. Every wheel binding has a `bind_touchpad` twin, which reads
  the event as a `TouchWheel`; the card follows its `pixels`. Test wheel and
  window changes under Tk 9 as well (`uv python install 3.14` brings one).
  What a machine's wheel or touchpad really sends, and what each signal does,
  is recorded by `python tools/wheel_probe.py` (invented records, written to
  `wheel_probe.txt`, ignored by git): ask for it before guessing again.
- Patching with shell heredocs mangles backslashes; write patch scripts to a
  file and `compile()` the result before writing it.

## Talking with the owner

The owner writes in Portuguese or English; answer in the language of the
message. Never ask for passwords or tokens.
