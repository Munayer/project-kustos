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
records, **notes** `n_` — shown as "drafts"), then file, register, conflicts, lock, doctor, mirror, search,
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
- **Monads** (`# ==== monads`): read-only view; `MonadIndex` weighs shared words
  and links, `MonadView` draws them with no lines. `MONAD_COLLS` keeps health and
  drafts out, also as bridges between records; keep it that way. To measure its
  frames, time the moves themselves: `update()` does not return while two tweens run.
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
- **GEO** (`# ==== geo`): a field of every record but the drafts, kept as
  typed (points `lat, lon` one per line, or GeoJSON pasted whole) and read by
  `parse_geo` into GeoJSON geometries only when needed: the card's hint
  (`App.geo_field`, `geo_put`), the doctor (warnings, never errors), the
  mirror, `is:geo`, and `cmd_geojson`, which leaves health out unless `--all`.
  Keep it offline: no geocoding and no tiles (the page's CSP is
  `default-src 'none'`). A new collection with a GEO joins `GEO_COLLS`.
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
   `_kustos_serve.cmd`, `kustos.ico`) **only when
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
