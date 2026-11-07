# Project Kustos

Project Kustos is a personal index of people, concepts, forms, sources, health tracking, all linked within the same base.

It's a python-based, Tk interface app, using .json files as the database set,
mirrored in markdown files capable of giving users readibility out of the
python ecosystem. Can be runned locally with synchronized folders, with automatic
updating of files and conflicts if used any syncing app or cloud sync.

## Requisites

- Python 3.10 or newer with Tkinter.

## How to use

1. Download `_kustos.py` and `_kustos.cmd` onto an empty folder.
2. Open `_kustos.cmd` to start using (or `_kustos_logbook.cmd` to read the base as a logbook, read-only; inside the app, `Ctrl+B` opens the logbook on the current entry and `Enter` in the logbook brings an entry back to the app). The empty folder will be the locus of files.
   On Windows you can also make a shortcut to `pythonw.exe "<folder>\_kustos.py"` with
   `kustos.ico` as its icon (`python tools/make_icon.py` draws it) and pin it to the
   Start menu or the taskbar.
3. Upon the first entry, the program creates the `_kustos.json` database. All files are local and don't leave your computer, unless you use a cloud or sync app.

## Components

- **Five collections** on the left menu, each with an unique ID:
  `p_` people · `c_` concept · `f_` form · `s_` source · `h_` health track ·
  `n_` draft.
- **Drafts**: free notes in markdown, one `.md` file each in `notes/` beside the
  program, so other markdown tools (Obsidian, say) read and edit the same
  files. The title is the file name; a small header (`id`, `reg_n`, `reg`,
  `tags`) lets Kustos follow a file renamed or moved inside `notes/`, and any
  other header field is kept. The JSON holds only an index entry per draft,
  never the text, so saving one does not rewrite the others; the log keeps the
  text of every save. A `.md` put into `notes/` comes in when Kustos opens or on
  `F5`. A file changed outside since it was opened is not overwritten without
  asking. Deleting moves the file to `notes/.deleted`. In a draft's text, in
  any record's NOTES and in reading mode: `Ctrl+B` bold, `Ctrl+I` italic, `Ctrl+K` `[[link]]`, `Ctrl+Backspace`/`Delete`
  a word, `Enter` continues a list or task, `Tab`/`Shift+Tab` indent it,
  `Alt+↑`/`Alt+↓` move lines, with a light markdown highlight. *as HTML* writes
  the draft as a page to read or print; **Base › Export drafts** puts them all
  in one markdown file. On Windows the drafts' text is cached in
  `%LOCALAPPDATA%\Kustos` (opening files is slow there), so only changed files
  are read again.
- **Linked entries** between any registers (`author_of`, `cites`,
  `attested_in`, `defined_in`, `translates`, `measured_in`…). Labels outside of the table are accepted and marked as atypical.
- **Link graph** (`Ctrl+Shift+G`, **View › Link graph**, or `python _kustos.py graph [id]`):
  a second, read-only window with the open record in the middle and the records
  one to three links away around it, laid out by springs that settle by
  themselves. It follows the record you open in the main window. The records
  glow and the glow changes as it runs, by one of three rules (`m` switches):
  *spreading glow* (the default: light runs along the links and fades, fed by
  recent edits and by sparks), *Conway's life* (the Game of Life with the links
  as neighbours: a lit record stays lit with 2 or 3 lit neighbours, a dark one
  lights with exactly 3) and *still*. Click a record to bring it to the middle;
  double-click or `Enter` opens it on the card; right-click sparks it (in life
  mode it flips the cell). It shows at most 160 records at a time.
  `p` **replays the logs**: the base grows on screen as it grew, records
  appearing when they were first saved, links when they were written, each
  edit a flash, with a timeline below (click or drag it to go to a moment;
  `space` pauses, `+`/`-` change the speed, `←`/`→` skip). `w` switches between
  the whole base (what was being worked on, and what it links to) and only the
  records that were on screen when the replay began. Records saved before
  there were logs open the timeline. `Esc` goes back to the live graph.
- **Timeline** (`Ctrl+Shift+T`, **View › Timeline**, or `python _kustos.py
  timeline [id]`): everything dated on one line of time, in lanes — the
  people's LOG (the facts of a life), births and deaths (`BORN` / `DIED` on the
  person card), tasks due, when sources came out, links with a
  span (`-800/400`), health readings, sessions, events and medicines, and
  drafts with a `date` or `period` in their header. From centuries to minutes:
  the wheel zooms where the pointer is, dragging moves along, `Home` shows
  everything, `t` today, `r` adds when each record was registered. It follows
  the main window's search and filters (`f` switches), and `Enter` opens the
  chosen record on the card. A LOG line may carry a year (`2021`), a month
  (`2024-03`) or a time (`2024-03-11 14:30`). **Base › Real dates in the logs**
  (or `python _kustos.py real-dates [apply [order]]`) finds log entries whose
  text starts with a date — as imported notes have it, `20240311…` — and, on
  confirmation, makes it the entry's date.
- **Peritia, the skills panel** (`_kustos_peritia.cmd`, **View › Skills (Peritia)**,
  or `python _kustos.py peritia`): a page in the browser, served by Kustos itself
  on 127.0.0.1 only, that stops two minutes after the page is closed. Skills
  (`k_`) sit on a star chart, domains as sectors and prerequisites as rings;
  each has a journal of *study*, *practice* and *proof* entries (a proof asks
  for a reference: a file that runs, a link, or a Kustos id), which add up to
  XP and to a level from I to V named after Dreyfus (from III up, XP alone is
  not enough: it takes proofs). Brightness shows freshness, and a level never
  falls. The *Foundations* page explains where each rule comes from and lets
  you change its numbers, keeping a dated history of every change. Skills
  live in `_kustos.json` beside the rest, link to any record, and go through
  the same log and conflict merge, but outside the register. A skill saved
  over a version that changed on disk is refused and the current one
  reloaded. `_kustos_peritia.html` is a read-only snapshot, rewritten on every
  change; a `_peritia.json` from the panel's standalone days can be imported.
- **Web version** (`python _kustos.py web`): the whole base in the browser,
  laid out for a phone as much as for a desk, served by Kustos itself on
  127.0.0.1 only; it stops two minutes after the page is closed (`--stay`
  keeps it up). Search with the same operators as the window, the five
  collections as tabs, every record readable and editable, new records of
  every kind, and on the card quick entries: a line in a person's LOG, a
  reading, a session; tick a task and it goes to the log. The fields hold the
  same text as the window's cards (a LOG line, a task line, a link line), and
  saving goes the same way — register, log, mirror — so both can be used on
  the same base. A record changed on disk since the page opened it (in the
  window, or synced from another machine) is not overwritten without asking.
  The menu opens the health report and the body map.
- **Source**: free types (book, paper, thesis, law/bill, decisions, webpages, videos), citations in academic formats, BibTeX and CSL-JSON.
  Can import from Zotero via CSL-JSON or BibTeX without duplicating entries.
- **Health (corpus)**: four kinds of record, each with its own fields —
  *measurements* (unit, reference range, dated readings with a trend curve),
  *medications* (dose, frequency, since/until, prescriber, purpose),
  *activities and habits* (aim and a diary of sessions) and *events*
  (consultations, exams, symptoms, procedures, vaccines). A minimalist
  Vitruvian body map shows the systems involved. **Base › Health report** (or
  `python _kustos.py health`) writes `_kustos_health.html` with two views:
  *Consultation* (medications in use, latest values with their status, recent
  events, current activities) and *Follow-up* (trends, sessions per week, full
  history); printing prints the view on screen.
- **Register number**, similar to notary and public registry systems: on its
  first save, every entry gets a stamp (`YYYYMMDDHHmmss`) and a sequential
  order number (`nº 1852`). The number never changes and is never reused;
  deleting an entry keeps its number in the sequence, marked as cancelled.
  Without a search, the list is the register itself, in number order.
- **No scrolling**: the list shows exactly as many rows as fit the window and
  pages through the rest (PageUp/PageDown or the mouse wheel turn a page).
- **Reading long notes**: `Ctrl+E` (or a double-click on a field's title) opens
  the field across the whole card, read in pages with PageUp/PageDown or the
  wheel, with `Ctrl+F` to find inside it; it stays editable. `F11` hides the
  rail and the list so the card takes the whole window; the text column keeps
  a readable width. A long LOG or NOTES field is read one page per view
  inside the card: each page holds what fits on screen and starts at an entry
  or paragraph (`‹ ›` beside the title, PageUp/PageDown, or the mouse wheel
  over it); the LOG opens on the newest. **View › Long texts › Continuous**
  makes them scroll instead.
- **Search**, the "indexer": results come in alphabetic order, paged, each with its register number, with operators of search:

  ```
  p: v: f: c: d:                    only people / verba / sources / body tracks / drafts
  ^ab                               name that starts with "ab"
  tag:x lang:de type:book sys:renal dom:law id:c_
  ```

  The search always runs over the whole base. The rail keeps every category
  visible and its numbers count what the search finds (categories with nothing
  are dimmed), so a search in one collection shows at once where else it
  matches. The filters in force sit as chips above the list: `×` drops one,
  *clear all* drops them all.

- **Sync between machines**: each machine that you end up using and syncing will write its own diary of usage
  (`_kustos.log.<machine>.jsonl`); files `*.sync-conflict-*` are mixed register by register on opening. The complete history of each register comes out in the diaries.

## Language

The interface is in English. Portuguese is available under **View › Language**
(saved as `ui.lang` in `_kustos.json`); the window reopens in the chosen
language. Your data is never translated: source types and corpus systems are
stored under their original keys and only *shown* in the interface language.
ABNT citations stay in Portuguese, as the standard itself is.

## Command lines (optional)

```
python _kustos.py doctor                data-health check
python _kustos.py search <texto>
python _kustos.py cite <id|texto> [abnt|abnt-autor-data|bibtex|csl-json|bruto]  pulls citation from source
python _kustos.py export [bibtex|csl|abnt] [arquivo]
python _kustos.py import zotero <export.json|.bib>
python _kustos.py mirror | corpus | merge | history <id> | replay
python _kustos.py logbook                  the base as a logbook (read-only)
python _kustos.py peritia [--no-open] [--port N]   the skills panel, in the browser
python _kustos.py web [--stay] [--no-open] [--port N]   the whole base, in the browser (phone or desk)
```

## Suggestion: Using Syncthing to sync

Suggestion for the `.stignore` of folder, if synced with Syncthing:

```
*.tmp
_kustos.replay.json
_kustos_fontes.*
__pycache__
```

## License

MIT. See [LICENSE](LICENSE).
