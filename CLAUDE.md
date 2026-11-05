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
history, migration, upgrade, citation, health report, peritia, themes, motion,
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
  records; `RELS` defines the types.
- **Peritia** (`# ==== peritia`): the skills panel is a page served by
  `cmd_peritia` on 127.0.0.1 (a token in the page, the Host header checked),
  from the template `PERITIA_HTML` (strings as `@@English@@`, translated by
  `tr` when the page is built). Skills are the top-level list `skills` (`k_`),
  the panel's parameters are in `peritia`; they save, log, merge and replay
  like records but stay out of `COLLS` and the register. Test it on invented
  data with `peritia_api(...)`, no browser needed.
- **Long texts are markdown**: `textfield(..., pages=True)` (every NOTES and the
  draft's text) gets `MarkdownKeys`, and `fit(opening=True)` paints it before
  the pages are measured. The text stored stays plain.
- **Motion** (`# ==== motion`): the timings are constants there, and `tween`
  follows the clock. Animate a tag's colour, not a Text's options: `configure`
  on a Text costs ~20 times as much per frame.
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
   screenshots, afterwards. Health data is sensitive.
3. `python _kustos.py doctor` must report 0 errors.
4. Commit with an English message ending in
   `Co-Authored-By: Claude <noreply@anthropic.com>`, then push.
5. Copy to the instance (`tools\update-instance.cmd`, or copy
   `_kustos.py`, `_kustos.cmd`, `_kustos_logbook.cmd`, `_kustos_peritia.cmd`,
   `kustos.ico`) **only when
   Kustos is closed** — check that no `python`/`pythonw` process is running, or
   ask the owner — then verify the copies match (ignoring CRLF/LF).

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
- Patching with shell heredocs mangles backslashes; write patch scripts to a
  file and `compile()` the result before writing it.

## Talking with the owner

The owner writes in Portuguese or English; answer in the language of the
message. Never ask for passwords or tokens.
