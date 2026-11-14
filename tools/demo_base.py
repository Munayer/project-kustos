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
PROGRAM = ("_kustos.py", "_kustos.cmd", "_kustos_logbook.cmd", "_kustos_peritia.cmd", "kustos.ico",
           "kustos_basemap.json")
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
    odd = words - {"fresh", "pt", "en", "web"}       # web: for demo.cmd, which opens the page
    if odd:
        print("Only these words are understood: fresh, pt, en, web. Not: " + " ".join(sorted(odd)))
        print("Nothing was done.")
        return 2
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
        if (REPO / name).exists():      # the basemap is optional, as in Kustos
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
    """The web demo's records: a few people, sources, verba, health records,
    things of the house (res: items and accounts) and drafts, then a web of
    concepts with many links for the graph."""
    def put(coll, rec, edges=None):
        {"people": K.fix_person, "entries": K.fix_entry, "sources": K.fix_source,
         "corpus": K.fix_metric, "res": K.fix_res}[coll](rec)
        K.touch(rec)
        return K.save_record(coll, rec, edges=edges)

    def edge(a, rel, b, why=""):
        return {"from": a, "rel": rel, "to": b, "when": "", "why": why, "source": "",
                "certainty": "established"}

    # the demo's observator: every record below is saved in Ada's name
    K.save_ui({"observator": "p_ada00001"})

    def on_day(n, fn):
        """Runs fn with Kustos's clock n days from now (n < 0: in the past)."""
        then = datetime.now() + timedelta(days=n)
        real = K.NOW, K.TODAY
        K.NOW = lambda: then.isoformat(timespec="seconds")
        K.TODAY = lambda: then.date().isoformat()
        try:
            return fn()
        finally:
            K.NOW, K.TODAY = real

    # ---- people (phones in the 555-01xx range, kept for fiction; example.org addresses)
    put("people", {"id": "p_iss00004", "name": "Institute of Steering Studies", "org": True,
                   "place": "Lisboa", "tags": ["research"], "geo": "38.7075, -9.1364  office",
                   "notes_raw": "A small institute on the history of control and regulation.",
                   "links": ["office: contact@example.org", "+1 202 555 0143",
                             "https://example.org/institute"],
                   "interactions": [{"date": "2026-10-15", "text": "Asked about the spring seminar."}]})
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
                   "links": ["work: ada@example.org", "mobile: +1 202 555 0168",
                             "home: 202 555 0175", "https://example.org/ada"]},
        edges=[edge("p_ada00001", "author_of", "s_okafor_2021_notes"),
               edge("p_ada00001", "works_at", "p_iss00004", "research fellow since 2023")])
    put("people", {"id": "p_tom00002", "name": "Tomás Weber", "place": "Basel",
                   "geo": "47.5596, 7.5886  workshop\n47.5480, 7.5890  the old mill",
                   "tags": ["teacher"], "born": "1950", "circles": ["concern"],
                   "notes_raw": "Retired engineer. Keeps a workshop full of governors and valves.",
                   "links": ["tom.weber@example.org"],
                   "interactions": [{"date": "2025-12-20", "text": "Letter about the old mill."}]},
        edges=[edge("p_tom00002", "member_of", "p_iss00004", "on the advisory board")])
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
    # ---- res (things of the house, invented); dates from today, so that the
    # reminders show: a warranty ending soon, a bicycle lent long ago
    def day(n):
        return (datetime.now() + timedelta(days=n)).date().isoformat()

    put("people", {"id": "p_cor00005", "name": "Corner Electronics", "org": True, "place": "Porto",
                   "tags": ["shop"], "links": ["https://example.org/corner-electronics"]})
    put("sources", {"id": "s_laptop_guide", "type": "documento", "name": "Laptop user guide",
                    "authors": ["CORNER ELECTRONICS"], "date": "2025",
                    "notes": "Battery care is on page 14."})
    # accounts (res): an invented bank, a checking account, a card whose last
    # four digits are plainly not real, and savings. Entries go through
    # Kustos's own reader, as typed on the card; the checking account moves
    # money into the savings and pays the card (transfers: their other half is
    # computed there), and the card paid for the laptop and the kettle's repair
    put("people", {"id": "p_ban00006", "name": "Banco Exemplo", "org": True, "place": "Porto",
                   "tags": ["bank"], "links": ["https://example.org/banco-exemplo"]})
    put("res", {"id": "r_demo_checking", "rtype": "account", "name": "Checking account",
                "atype": "checking", "currency": "BRL", "institution": "p_ban00006",
                "opening": "2500.00", "opening_date": day(-60), "tags": ["demo"],
                "entries": K.parse_entries("\n".join([
                    f"{day(-40)}  +3200,00  salary #income",
                    f"{day(-38)}  -1.250,00  rent #housing",
                    f"{day(-35)}  -500  > r_demo_savings  reserve",
                    f"{day(-30)}  -89,90  market #food",
                    f"{day(-12)}  +3200,00  salary #income",
                    f"{day(-10)}  -1.250,00  rent #housing",
                    f"{day(-8)}  -620,40  > r_demo_card  card payment",
                    f"{day(-3)}  -45,90  market #food:market"]))})
    put("res", {"id": "r_demo_card", "rtype": "account", "name": "Credit card",
                "atype": "card", "currency": "BRL", "institution": "p_ban00006", "last4": "0000",
                "notes": "An invented card: **0000** is not a real number.",
                "entries": K.parse_entries("\n".join([
                    f"{day(-345)}  -5.890,00  laptop #electronics → r_laptop_14",
                    f"{day(-15)}  -32,50  bookshop #books",
                    f"{day(-6)}  -120,00  kettle repair #home → r_electric_kettle",
                    f"{day(-2)}  -58,00  pharmacy #health"]))})
    put("res", {"id": "r_demo_savings", "rtype": "account", "name": "Savings",
                "atype": "savings", "currency": "BRL", "institution": "Cooperativa Exemplo",
                "opening": "10000", "opening_date": day(-90),
                "entries": K.parse_entries(f"{day(-31)}  +12,34  interest #interest")})
    put("res", {"id": "r_garden_shed", "name": "Garden shed", "category": "other",
                "where": "home › garden", "bought": "2019-04", "geo": "41.1579, -8.6291  garden"})
    # the toolbox was first saved forty days ago and saved again, changed, twelve
    # days ago: Kustos observed it on each of those days (is:reobserved finds it)
    toolbox = {"id": "r_toolbox", "name": "Red toolbox", "category": "tools", "status": "in use",
               "where": "home › garage", "tags": ["diy"],
               "log": [{"date": "2026-06-14", "text": "New set of screwdrivers."}]}
    on_day(-40, lambda: put("res", dict(toolbox), edges=[]))
    on_day(-12, lambda: put("res", dict(toolbox, status="stored", where="home › garden › shed"),
                            edges=[edge("r_toolbox", "kept_in", "r_garden_shed", "on the left shelf")]))
    put("res", {"id": "r_city_bicycle", "name": "City bicycle", "category": "vehicle", "status": "lent",
                "status_since": day(-75), "where": "home › garage", "bought": "2021-05-10",
                "price": "1450,00 BRL", "serial": "BK-DEMO-7781",
                "log": [{"date": "2025-09-02", "text": "New tyres."},
                        {"date": day(-75), "text": "Lent to Mira for her trip."}]},
        edges=[edge("r_city_bicycle", "lent_to", "p_mir00003", "for her trip")])
    put("res", {"id": "r_laptop_14", "name": "Laptop, 14-inch", "category": "electronics",
                "where": "home › office › desk", "bought": day(-345), "warranty_until": day(20),
                "price": "5890,00 BRL", "serial": "SN-DEMO-0042", "tags": ["work"],
                "notes": "Keep the box until the **warranty** ends."},
        edges=[edge("r_laptop_14", "bought_from", "p_cor00005", "with a one-year warranty"),
               edge("r_laptop_14", "manual_in", "s_laptop_guide", "the printed guide"),
               edge("r_laptop_14", "paid_from", "r_demo_card", "in one payment")])
    put("res", {"id": "r_electric_kettle", "name": "Electric kettle", "category": "kitchen",
                "status": "in repair", "where": "home › kitchen",
                "log": [{"date": day(-6), "text": "Taken to the repair shop: the switch."}]})
    put("res", {"id": "r_winter_coats", "name": "Winter coats", "category": "clothes", "qty": 3,
                "status": "stored", "where": "home › bedroom › wardrobe"})
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
    # ---- observations: every save above was observed by itself (a distinguo the
    # first time); a few deliberate ones, by invented criteria. One criterion
    # comes back three times without a concept of its own (`observe` lists it as
    # an eigenform); one is a concept of the demo.
    K.add_observation(["c_feedback_loop"], "a loop that corrects the output, not one that amplifies it",
                      "sign of the feedback", 3, "s_okafor_2021_notes")
    K.add_observation(["c_homeostasis"], "a steady state kept against change, not a fixed one",
                      "sign of the feedback", 2)
    K.add_observation(["s_weber_1979_valves"], "valves that regulate, apart from valves that only close",
                      "sign of the feedback", 1, notes="Read again after the workshop visit.")
    K.add_observation(["f_kybernetes"], "the steersman's image, apart from the governor's",
                      "c_feedback_loop", 2)
    # ---- proposals: what comes in without being typed -- a source imported as
    # CSL-JSON (as a research agent's output would come), forty-five days ago,
    # and the bulk entry's concepts with their forms -- stays unsigned until Ada
    # signs it (is:proposed finds them; `doctor --observe` lists the old one).
    # The bulk line for Steering gives Ada's form κυβερνήτης a second concept,
    # unsigned: a form in conflict. One concept is signed, the rest wait.
    def import_one():
        data = K.load_json()
        K.import_sources([K.source_from_csl({
            "type": "article-journal", "title": "Governors and the Helm",
            "author": [{"family": "Lindqvist", "given": "Maren"}], "issued": {"date-parts": [[2016]]},
            "container-title": "Invented Review of Control", "volume": "4", "page": "1-19"})],
            data, proposed=True)
        K.write_json(data)
    on_day(-45, import_one)
    plan, _bad = K.parse_bulk_concepts(
        "Feedforward | acting on a disturbance before it shows: Vorsteuerung (deu); anticipazione (ita)\n"
        "Setpoint drift | a target that moves by itself: deriva (ita)\n"
        "Steering | guiding a course by small corrections: κυβερνήτης (grc)")
    K.save_bulk_concepts(plan, "")
    K.sign_proposals([e["id"] for e in K.load_json()["entries"] if e.get("name") == "Feedforward"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
