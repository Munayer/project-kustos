"""A Kustos base of INVENTED records -- the same as the web demo's -- in a
folder of its own, apart from your Kustos folder: to try a change, to compare
the window with the web page on the same records, or to take pictures that can
be shared. tools/demo.cmd runs it and opens Kustos there.

    python tools/demo_base.py <folder> [fresh] [pt|en]

The folder gets this repository's program every time, so it runs what the
repository holds. Its records are made once, through Kustos's own save
functions, and then kept -- add test records of your own to them -- until
`fresh` makes new ones. `pt` or `en` sets the interface language.

A folder that is not empty and was not made by this script is refused: a real
base is never touched. Nothing here reads or writes anything else.
"""
import importlib.util
import json
import random
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROGRAM = ("_kustos.py", "_kustos.cmd", "_kustos_logbook.cmd", "_kustos_peritia.cmd", "kustos.ico")
MARK = ".kustos-demo"


def open_here(folder):
    """A lock under a day old: Kustos is open on the folder (as _kustos.py reads it)."""
    for path in folder.glob("_kustos.lock.*.json"):
        try:
            since = json.loads(path.read_text(encoding="utf-8")).get("since", "")
            if (datetime.now() - datetime.fromisoformat(since)).total_seconds() < 24 * 3600:
                return True
        except (OSError, ValueError, AttributeError):
            return True
    return False


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    folder = Path(argv[0]).resolve()
    words = {a.lower() for a in argv[1:]}
    if folder == REPO or REPO in folder.parents or folder in REPO.parents:
        print(f"Not inside the repository, nor above it: {folder}")
        return 1
    if folder.exists() and any(folder.iterdir()) and not (folder / MARK).exists():
        print(f"{folder} is not empty and was not made by demo_base.py: nothing was done.")
        return 1
    if "fresh" in words and folder.exists():
        if open_here(folder):
            print("Kustos is open on the demo base: close it, then ask for fresh records again.")
            return 1
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / MARK).write_text("A base of invented records made by tools/demo_base.py; safe to delete.\n",
                               encoding="utf-8")
    for name in PROGRAM:
        shutil.copy2(REPO / name, folder / name)
    spec = importlib.util.spec_from_file_location("kustos_demo_base", folder / "_kustos.py")
    K = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(K)          # works on the folder it sits in: the demo's
    if (folder / "_kustos.json").exists():
        print(f"Program refreshed; the records are kept: {folder}")
    else:
        build(K, folder)
        print(f"Invented records made: {folder}")
    for code in ("pt", "en"):
        if code in words:
            K.save_ui({"lang": code})
    K.cmd_doctor()
    return 0


def build(K, folder):
    """The web demo's records: a few people, sources, verba, health records and
    drafts, then a web of concepts with many links for the graph."""
    def put(coll, rec, edges=None):
        {"people": K.fix_person, "entries": K.fix_entry, "sources": K.fix_source,
         "corpus": K.fix_metric}[coll](rec)
        K.touch(rec)
        return K.save_record(coll, rec, edges=edges)

    def edge(a, rel, b, why=""):
        return {"from": a, "rel": rel, "to": b, "when": "", "why": why, "source": "",
                "certainty": "established"}

    # ---- people
    put("people", {"id": "p_ada00001", "name": "Ada Okafor", "place": "Porto",
                   "tags": ["colleague", "research"], "circles": ["influence"],
                   "born": "1984", "met": "2023-04-02",
                   "notes_raw": "Works on **steering metaphors** in early control theory.\n\n"
                                "- prefers email\n- reads Portuguese and German",
                   "tasks": [{"text": "Send the draft chapter", "state": "todo", "due": "2026-11-12", "at": ""},
                             {"text": "Review her translation notes", "state": "doing", "due": "", "at": ""}],
                   "interactions": [{"date": "2026-09-14", "text": "Coffee after the seminar; talked about helmsmen."},
                                    {"date": "2026-10-03", "text": "She sent two articles on feedback."},
                                    {"date": "2026-10-28", "text": "Call: agreed to co-write a short note."}],
                   "links": ["https://example.org/ada"]},
        edges=[edge("p_ada00001", "author_of", "s_okafor_2021_notes")])
    put("people", {"id": "p_tom00002", "name": "Tomás Weber", "place": "Basel",
                   "tags": ["teacher"], "born": "1950", "circles": ["concern"],
                   "notes_raw": "Retired engineer. Keeps a workshop full of governors and valves.",
                   "interactions": [{"date": "2025-12-20", "text": "Letter about the old mill."}]})
    put("people", {"id": "p_mir00003", "name": "Mira Castellano", "tags": ["friend"],
                   "tasks": [{"text": "Return the atlas", "state": "todo", "due": "", "at": ""}]})
    # ---- sources
    put("sources", {"id": "s_okafor_2021_notes", "type": "livro", "name": "Notes on Steering Systems",
                    "authors": ["OKAFOR, Ada"], "date": "2021", "publisher": "Harbor Press",
                    "place": "Lisboa", "pages": "212", "tags": ["control"],
                    "notes": "Chapter 3 compares rudders and thermostats."})
    put("sources", {"id": "s_weber_1979_valves", "type": "artigo", "name": "Valves that think",
                    "authors": ["WEBER, Tomás"], "date": "1979", "container": "Workshop Quarterly",
                    "volume": "12", "issue": "3", "pages": "40-51"})
    # ---- verba
    put("entries", {"id": "c_feedback_loop", "kind": "concept", "name": "Feedback loop",
                    "gloss": "A circuit in which part of the output returns as input.",
                    "domains": ["control"], "tags": ["core"], "source": "s_okafor_2021_notes",
                    "notes": "Compare with *homeostasis*."},
        edges=[edge("c_feedback_loop", "defined_in", "s_okafor_2021_notes", "first clear statement")])
    put("entries", {"id": "c_homeostasis", "kind": "concept", "name": "Homeostasis",
                    "gloss": "Keeping an inner state steady against outer change.", "domains": ["biology"]},
        edges=[edge("c_homeostasis", "analogous_to", "c_feedback_loop")])
    put("entries", {"id": "f_kybernetes", "kind": "form", "name": "κυβερνήτης", "lang": "grc",
                    "roman": "kybernḗtēs", "attested": "-800", "gloss": "helmsman, steersman"},
        edges=[edge("f_kybernetes", "expresses", "c_feedback_loop", "the steering image")])
    # ---- corpus (health records, invented)
    put("corpus", {"id": "h_cardio_resting_hr", "ctype": "measure", "name": "Resting heart rate",
                   "system": "cardiovascular", "unit": "bpm", "ref_low": "50", "ref_high": "90",
                   "readings": [{"date": d, "value": v, "note": n} for d, v, n in [
                       ("2026-05-02", "64", ""), ("2026-06-01", "61", ""), ("2026-07-03", "66", "after travel"),
                       ("2026-08-05", "59", ""), ("2026-09-02", "58", ""), ("2026-10-01", "93", "fever"),
                       ("2026-10-20", "62", "")]]})
    put("corpus", {"id": "h_vitamin_d", "ctype": "medication", "name": "Vitamin D", "system": "endócrino",
                   "dose": "1000 IU", "frequency": "daily", "start": "2026-01-10", "purpose": "winter"})
    put("corpus", {"id": "h_swimming", "ctype": "activity", "name": "Swimming", "system": "atividade",
                   "target": "2 times a week",
                   "sessions": [{"date": "2026-10-21", "text": "40 min"}, {"date": "2026-10-24", "text": "35 min"},
                                {"date": "2026-11-02", "text": "45 min, easy"}]})
    put("corpus", {"id": "h_checkup", "ctype": "event", "name": "Annual check-up", "etype": "consultation",
                   "date": "2026-10-02", "doctor": "Dr. Example", "place": "Clinic"})
    # ---- drafts: files in notes/, taken in as Kustos does
    notes = folder / "notes"
    notes.mkdir(exist_ok=True)
    (notes / "Reading list for winter.md").write_text(
        "---\ntags: [reading]\n---\n# Winter\n\n- [ ] *Notes on Steering Systems*\n- [x] the valves article\n\n"
        "Ask about [[Feedback loop]] and the mill.\n", encoding="utf-8")
    (notes / "On steering.md").write_text(
        "A helmsman does not fight the sea; he answers it.\n\n> every correction is a small listening\n",
        encoding="utf-8")
    K.index_notes()

    # ---- a web of concepts, people and sources with many links, for the graph
    rng = random.Random(7)
    concepts = ["Setpoint", "Error signal", "Damping", "Oscillation", "Equilibrium", "Gain", "Delay",
                "Noise", "Signal", "Channel", "Redundancy", "Entropy", "Information", "Message",
                "Regulation", "Variety", "Model", "Observer", "System", "Environment", "Boundary",
                "Black box", "Memory", "Thermostat", "Governor", "Steering", "Purpose", "Learning"]
    people = ["Ilse Varga", "Kenji Moreau", "Rosa Lind", "Pavel Duarte", "Noor Halvorsen", "Lior Bastos"]
    sources = [("Small Machines that Listen", "VARGA, Ilse", "2014"),
               ("The Patient Valve", "MOREAU, Kenji", "2009"),
               ("On Holding Course", "LIND, Rosa", "2018"),
               ("Signals in the Workshop", "DUARTE, Pavel", "2011"),
               ("Quiet Systems", "HALVORSEN, Noor", "2020")]
    rel_cc = ["specializes", "opposes", "analogous_to", "requires", "instrument_of"]

    def woven(a, rel, b):
        return edge(a, rel, b, "invented for the demo")

    taken = set(K.by_id(K.load_json()))
    cids = ["c_feedback_loop", "c_homeostasis"]
    for name in concepts:
        cid = K.new_id("concept", name, taken)
        taken.add(cid)
        cids.append(cid)
    sids = ["s_okafor_2021_notes", "s_weber_1979_valves"]
    for title, author, year in sources:
        s = K.fix_source({"type": "livro", "name": title, "authors": [author], "date": year,
                          "publisher": "Invented Press"})
        s["id"] = K.new_source_id(s, taken)
        taken.add(s["id"])
        sids.append(s["id"])
        K.touch(s)
        K.save_record("sources", s, edges=[])
    pids = ["p_ada00001", "p_tom00002", "p_mir00003"]
    for name in people:
        pid = K.make_id(name, taken)
        taken.add(pid)
        pids.append(pid)
        p = K.fix_person({"id": pid, "name": name, "tags": ["demo"]})
        K.touch(p)
        K.save_record("people", p)
    for i, cid in enumerate(cids[2:]):
        out = set()
        for _ in range(rng.randint(2, 3)):
            other = rng.choice(cids)
            if other != cid:
                out.add((rng.choice(rel_cc), other))
        if rng.random() < 0.6:
            out.add(("defined_in", rng.choice(sids)))
        if rng.random() < 0.35:
            out.add(("coined_by", rng.choice(pids)))
        rec = K.fix_entry({"id": cid, "kind": "concept", "name": concepts[i],
                           "gloss": "An invented gloss for the demo.", "domains": ["control"]})
        K.touch(rec)
        K.save_record("entries", rec, edges=[woven(cid, r, t) for r, t in sorted(out)])
    for pid in pids[3:]:
        out = {("knows", rng.choice(pids)) for _ in range(2)}
        out.add(("author_of", rng.choice(sids)))
        rec = next(p for p in K.load_json()["people"] if p["id"] == pid)
        K.save_record("people", rec, edges=[woven(pid, r, t) for r, t in sorted(out) if t != pid])
    # edits spread over the last six months, as in a base in use (life seeds from recency)
    data = K.load_json()
    for coll in ("people", "entries", "sources"):
        for r in data[coll]:
            when = datetime.now() - timedelta(days=rng.uniform(0, 180))
            r["updated_at"] = when.isoformat(timespec="seconds")
            r["updated"] = when.date().isoformat()
    K.write_json(data)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
