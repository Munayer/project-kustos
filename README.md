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
2. Open `_kustos.cmd` to start using. The empty folder will be the locus of files.
3. Upon the first entry, the program creates the `_kustos.json` database. All files are local and don't leave your computer, unless you use a cloud or sync app.

## Components

- **Four collections** on the left menu, each with an unique ID:
  `p_` people · `c_` concept · `f_` form · `s_` source · `h_` health track.
- **Linked entries** between any registers (`author_of`, `cites`,
  `attested_in`, `defined_in`, `translates`, `measured_in`…). Labels outside of the table are accepted and marked as atypical.
- **Source**: free types (book, paper, thesis, law/bill, decisions, webpages, videos), citations in academic formats, BibTeX and CSL-JSON.
  Can import from Zotero via CSL-JSON or BibTeX without duplicating entries.
- **Health track**: trackings with each body system, units, reference margin, dated entries; minimalist vitruvian-inspired body mapping with tendency curve. Also generates an HTML to open in the web browser.
- **Register number**, similar to notary and public registry systems: on its
  first save, every entry gets a stamp (`YYYYMMDDHHmmss`) and a sequential
  order number (`nº 1852`). The number never changes and is never reused;
  deleting an entry keeps its number in the sequence, marked as cancelled.
  Without a search, the list is the register itself, in number order.
- **No scrolling**: the list shows exactly as many rows as fit the window and
  pages through the rest (PageUp/PageDown or the mouse wheel turn a page).
- **Search**, the "indexer": results come in alphabetic order, paged, each with its register number, with operators of search:

  ```
  p: v: f: c:                       only people / verba / sources / body tracks
  ^ab                               name that starts with "ab"
  tag:x lang:de type:livro sys:renal dom:direito id:c_
  ```

- **Sync between machines**: each machine that you end up using and syncing will write its own diary of usage
  (`_kustos.log.<machine>.jsonl`); files `*.sync-conflict-*` are mixed register by register on opening. The complete history of each register comes out in the diaries.

## Command lines (optional)

```
python _kustos.py doctor                data-health check
python _kustos.py search <texto>
python _kustos.py cite <id|texto> [abnt|abnt-autor-data|bibtex|csl-json|bruto]  pulls citation from source
python _kustos.py export [bibtex|csl|abnt] [arquivo]
python _kustos.py import zotero <export.json|.bib>
python _kustos.py mirror | corpus | merge | history <id> | replay
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
