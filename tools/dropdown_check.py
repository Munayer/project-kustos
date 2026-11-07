"""Lists every time a record's drop-down value changed, from the logs -- to
find the ones the wheel changed in passing, before Kustos stopped drop-down
boxes from listening to it.

    python tools/dropdown_check.py "<your Kustos folder>"

It only reads: the logs (_kustos.log.*.jsonl) and _kustos.json in that folder.
Nothing is written, nothing leaves the computer. It prints, oldest first, each
change of a source's type, a form's status, or a health record's type, system
or event kind: when, on which computer, the record, the value before and after,
and the value now. "only this changed" marks a save where nothing else of the
record changed, as when the wheel turned the box: those are the ones to look
at first. A change you made yourself is fine; one you did not, fix on the card.
"""
import json
import sys
from pathlib import Path

STEM = "_kustos"
# the drop-down boxes of the cards, and the stored fields they set
WATCH = {"sources": ("type",), "entries": ("status",), "corpus": ("ctype", "system", "etype")}
QUIET = {"updated", "updated_at", "reg", "reg_n", "reg_origem", "reg_n_anterior"}


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    folder = Path(argv[0]).expanduser()
    logs = sorted(folder.glob(f"{STEM}.log.*.jsonl"))
    if not logs:
        print(f"No Kustos logs in {folder}: is it the folder with _kustos.json?")
        return 1
    lines = []
    for path in logs:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Could not read {path.name}: {exc}")
            continue
        for raw in text.splitlines():
            try:
                line = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if line.get("op") == "put" and line.get("coll") in WATCH and isinstance(line.get("rec"), dict):
                lines.append(line)
    lines.sort(key=lambda l: l.get("t", ""))
    now = {}
    try:
        data = json.loads((folder / f"{STEM}.json").read_text(encoding="utf-8"))
        for coll in WATCH:
            for rec in data.get(coll, []):
                now[rec.get("id")] = rec
    except (OSError, json.JSONDecodeError):
        pass

    last, found = {}, []
    for line in lines:
        rec, rid = line["rec"], line.get("id") or line["rec"].get("id")
        before = last.get(rid)
        last[rid] = rec
        if before is None:
            continue                            # the record's first save: nothing changed
        changed = [k for k in WATCH[line["coll"]] if (before.get(k) or "") != (rec.get(k) or "")]
        if line["coll"] == "entries" and rec.get("kind") != "form":
            changed = []
        if not changed:
            continue
        others = [k for k in set(before) | set(rec)
                  if k not in QUIET and k not in changed and before.get(k) != rec.get(k)]
        for k in changed:
            found.append((line.get("t", "")[:16].replace("T", " "), line.get("host", "?"), line["coll"], rid,
                          rec.get("name") or rec.get("raw") or rid, k, before.get(k) or "",
                          rec.get(k) or "", (now.get(rid) or {}).get(k, "(deleted)"), not others))
    if not found:
        print(f"No drop-down value ever changed after a record's first save ({len(lines)} saves read).")
        return 0
    print(f"{len(found)} change(s) of a drop-down value, oldest first ({len(lines)} saves read):\n")
    for when, host, coll, rid, name, k, old, new, cur, alone in found:
        print(f"{when}  {host}  {coll}/{k}  {name}  ({rid})")
        print(f"      {old!r} -> {new!r}   now {cur!r}" + ("   << only this changed" if alone else ""))
    print("\nA change you made yourself is fine. One you did not: open the record and set it back.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
