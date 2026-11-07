"""Records what the wheel and the touchpad send to Kustos, and what each
signal does -- on INVENTED records only, in a folder of their own.

    python tools/wheel_probe.py

Kustos opens on invented records, a long one on the card. Scroll over the
places that do not work (and one that does), then close the window. The
record of every scroll signal is written to wheel_probe.txt beside this
repository's README: send that file. It holds the invented records' names,
the widgets the signals reached and the versions of Python, Tk and Windows;
nothing of your own base, which this never opens.
"""
import importlib.util
import platform
import sys
import tempfile
import time
import tkinter
from pathlib import Path
from tkinter import font, ttk

REPO = Path(__file__).resolve().parent.parent
FOLDER = Path(tempfile.gettempdir()) / "kustos_wheel_probe"
OUT = REPO / "wheel_probe.txt"
SEQS = ("<MouseWheel>", "<Shift-MouseWheel>", "<Button-4>", "<Button-5>")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    demo = load(REPO / "tools" / "demo_base.py", "probe_demo_base")
    if demo.main([str(FOLDER), "fresh"]) != 0:
        print("The invented base could not be made; see above.")
        return 1
    K = load(FOLDER / "_kustos.py", "probe_kustos")
    K.tk, K.tkfont, K.ttk = tkinter, font, ttk
    # one long invented record, so the card scrolls and its NOTES and LOG page
    data = K.load_json()
    p = next(x for x in data["people"] if x["id"] == "p_tom00002")
    p["notes_raw"] = "\n\n".join(f"Paragraph {i}: an invented note about valves, mills and governors. " * 3
                                 for i in range(40))
    p["interactions"] = [{"date": f"2025-{1 + i % 12:02d}-{1 + i % 27:02d}", "text": f"Invented call {i}."}
                         for i in range(120)]
    p["tasks"] = [{"text": f"Invented task {i}", "state": "todo", "due": "", "at": ""} for i in range(25)]
    K.touch(p)
    K.save_record("people", p)
    K.load_palette("paper")

    t0 = time.perf_counter()
    lines = []
    root = tkinter.Tk()

    def note(*parts):
        lines.append(f"{(time.perf_counter() - t0) * 1000:9.0f} ms  " + " ".join(str(x) for x in parts))

    def short(w):
        if w is None:
            return "-"
        s = str(w)
        return s if len(s) <= 60 else "…" + s[-59:]

    def cls(w):
        try:
            return w.winfo_class()
        except Exception:
            return "?"

    lines += [f"Kustos wheel probe, {time.strftime('%Y-%m-%d %H:%M')}",
              f"python {sys.version.split()[0]} · tk {root.tk.call('info', 'patchlevel')} · "
              f"{platform.platform()} · tk scaling {root.tk.call('tk', 'scaling')}",
              f"screen {root.winfo_screenwidth()}x{root.winfo_screenheight()} · "
              f"program has text_wheel: {hasattr(K.App, 'text_wheel')}", ""]

    app_box = {}

    def card_of(w):
        app = app_box.get("app")
        return app.card_canvas(w) if app is not None and w is not None else None

    def state_of(w):
        """Where the card and the field under the pointer stand."""
        cv = card_of(w)
        out = []
        if cv is not None:
            out.append("card %.3f-%.3f" % cv.yview())
        if isinstance(w, tkinter.Text):
            book = getattr(w, "pages", None)
            out.append("field %.3f-%.3f" % w.yview())
            if book is not None:
                out.append(f"paged={book.paged} page={book.cur}")
        return " ".join(out) or "not in a card"

    def raw(e):
        """Every wheel signal, before anything else sees it."""
        w = e.widget if not isinstance(e.widget, str) else None
        under = root.winfo_containing(e.x_root, e.y_root)
        note("SIGNAL", f"{cls(w)} {short(w)}", f"delta={getattr(e, 'delta', '')}",
             f"state={getattr(e, 'state', '')}", f"num={getattr(e, 'num', '')}",
             f"under pointer: {cls(under)} {short(under) if under is not w else '(same)'}",
             "|", state_of(w))
        root.after(300, lambda: note("   0.3 s later:", state_of(w)))

    for seq in SEQS:
        root.bind_class("WheelProbe", seq, raw)

    def tag_all(w=None):
        """The probe's tag first on every widget, so it sees each signal before any handler."""
        for c in (w or root).winfo_children():
            try:
                tags = c.bindtags()
                if "WheelProbe" not in tags:
                    c.bindtags(("WheelProbe",) + tags)
            except tkinter.TclError:
                pass
            tag_all(c)

    for name in ("text_wheel", "card_wheel"):        # which of Kustos's handlers ran
        orig = getattr(K.App, name)

        def wrapped(self, e, orig=orig, name=name):
            note("   handler", name, cls(e.widget))
            return orig(self, e)
        setattr(K.App, name, wrapped)

    app = app_box["app"] = K.App(root, "paper", [])
    for cv in getattr(app, "canvases", []):           # what the card's own handler did
        orig_wheel = cv.wheel

        def wheel(e, orig_wheel=orig_wheel, cv=cv):
            before = cv.yview()
            r = orig_wheel(e)
            note("   card wheel: card %.3f -> %.3f (at once; it glides on)" % (before[0], cv.yview()[0]))
            return r
        cv.wheel = wheel
    root.after(800, lambda: app.open_record("p_tom00002"))

    def keep_tagging():
        tag_all()
        try:
            OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass
        root.after(1000, keep_tagging)

    root.after(1200, keep_tagging)
    print("Kustos is open on invented records (a long one on the card).")
    print("Scroll with the touchpad over the places that do not work, and one that does;")
    print("then close the window. The record goes to:", OUT)
    root.mainloop()
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Written:", OUT, f"({sum(1 for l in lines if 'SIGNAL' in l)} scroll signals)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
