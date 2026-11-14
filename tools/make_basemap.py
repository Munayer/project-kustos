"""Makes kustos_basemap.json, the map's outline of the Earth, from Natural
Earth (naturalearthdata.com, public domain): the coastlines and the land
borders between countries at 1:50m, simplified (Douglas-Peucker) and rounded,
so that the file stays small enough to keep in git.

    python tools/make_basemap.py [--tolerance DEG] [--digits N] [--110m]
                                 [--no-borders] [--from FOLDER]

It downloads the GeoJSON once, from the official Natural Earth repository on
GitHub (a pinned release), and writes kustos_basemap.json at the root of this
repository; nothing else. --from reads the same files from a folder instead
(ne_50m_coastline.geojson ...), with no network. This is the only part of
Kustos that ever goes to the network, and only when it is run by hand:
_kustos.py reads the file it makes, and works without it.

The file: {"about", "source", "layers": {"coast": [line, ...], "borders":
[...]}}, each line a flat list lon, lat, lon, lat, ... in degrees (WGS 84),
one line of the file per line of the map.
"""
import hashlib
import json
import math
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "kustos_basemap.json"
RELEASE = "v5.1.2"
URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{release}/geojson/{name}"
LAYERS = (("coast", "ne_{scale}_coastline.geojson"),
          ("borders", "ne_{scale}_admin_0_boundary_lines_land.geojson"))
TOLERANCE = 0.05       # degrees (about 5 km): a vertex nearer than this to the line goes
DIGITS = 2             # 0.01 degree, about 1 km
MIN_EXTENT = 0.12      # degrees: a line smaller than this (a rock) is left out


def fetch(name, folder):
    """The bytes of one Natural Earth file, and where they came from."""
    if folder:
        path = Path(folder) / name
        return path.read_bytes(), str(path)
    url = URL.format(release=RELEASE, name=name)
    req = urllib.request.Request(url, headers={"User-Agent": "kustos-make-basemap"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read(), url


def simplify(pts, tol):
    """Douglas-Peucker on a list of (lon, lat), in degrees: the vertices kept."""
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    tol2 = tol * tol
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        n2 = dx * dx + dy * dy
        far, at = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            if n2 == 0:
                d2 = (px - x1) ** 2 + (py - y1) ** 2
            else:
                t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / n2))
                d2 = (px - x1 - t * dx) ** 2 + (py - y1 - t * dy) ** 2
            if d2 > far:
                far, at = d2, i
        if far > tol2:
            keep[at] = True
            stack.append((a, at))
            stack.append((at, b))
    return [p for p, k in zip(pts, keep) if k]


def lines_of(geometry):
    """The polylines of a LineString or MultiLineString (or a polygon's rings)."""
    t, c = geometry.get("type"), geometry.get("coordinates")
    if t == "LineString":
        return [c]
    if t in ("MultiLineString", "Polygon"):
        return list(c)
    if t == "MultiPolygon":
        return [ring for poly in c for ring in poly]
    return []


def clean(line):
    """(lon, lat) floats on the Earth, or None for a line that does not read."""
    out = []
    for pos in line:
        if not isinstance(pos, list) or len(pos) < 2:
            return None
        lon, lat = pos[0], pos[1]
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lon, lat)):
            return None
        out.append((max(-180.0, min(180.0, float(lon))), max(-90.0, min(90.0, float(lat)))))
    return out


def chain(lines):
    """Lines that meet end to end, where only two meet, joined into one: the
    borders come as one piece per pair of countries, and every line is one
    item more for the map to draw. Lines meeting three or more at a point
    stay apart there."""
    ends = {}
    for n, pts in enumerate(lines):
        for p in (pts[0], pts[-1]):
            ends.setdefault(p, []).append(n)
    used, out = set(), []

    def other(p, n):
        at = [m for m in ends.get(p, ()) if m != n and m not in used]
        return at[0] if len(ends.get(p, ())) == 2 and len(at) == 1 else None

    for n, pts in enumerate(lines):
        if n in used or pts[0] == pts[-1]:
            continue
        used.add(n)
        run = list(pts)
        for grow_end in (True, False):          # forward from its end, then back from its start
            while True:
                p = run[-1] if grow_end else run[0]
                m = other(p, n)
                if m is None:
                    break
                used.add(m)
                nxt = lines[m] if lines[m][0] == p else lines[m][::-1]
                if not grow_end:
                    nxt = nxt[::-1]
                run = run + nxt[1:] if grow_end else nxt[:-1] + run
                n = m
        out.append(run)
    out += [pts for n, pts in enumerate(lines) if n not in used]     # rings, and what was left
    return out


def layer(raw, tol, digits):
    """The simplified lines of one GeoJSON FeatureCollection, and counts."""
    data = json.loads(raw)
    lines, before, after, dropped = [], 0, 0, 0
    found = [pts for f in data.get("features") or []
             for pts in map(clean, lines_of(f.get("geometry") or {})) if pts and len(pts) >= 2]
    pieces = len(found)
    found = chain(found)
    print(f"  {pieces:,} lines, {len(found):,} once joined end to end")
    for pts in found:
        before += len(pts)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        if max(max(xs) - min(xs), max(ys) - min(ys)) < MIN_EXTENT:
            dropped += 1
            continue
        kept = []
        for lon, lat in simplify(pts, tol):
            p = (round(lon, digits), round(lat, digits))
            if not kept or p != kept[-1]:
                kept.append(p)
        if len(kept) < 2:
            dropped += 1
            continue
        after += len(kept)
        lines.append([v for p in kept for v in p])
    return lines, before, after, dropped


def number(v, digits):
    """A coordinate as short as it reads back: 12.3, not 12.30, -0.0 as 0."""
    s = f"{v:.{digits}f}"
    if "." in s:                        # 10 stays 10 with --digits 0
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def main(argv):
    tol, digits, scale, borders, folder = TOLERANCE, DIGITS, "50m", True, None
    args = list(argv)
    try:
        while args:
            a = args.pop(0)
            if a == "--tolerance":
                tol = float(args.pop(0))
            elif a == "--digits":
                digits = int(args.pop(0))
            elif a == "--110m":
                scale = "110m"
            elif a == "--no-borders":
                borders = False
            elif a == "--from":
                folder = args.pop(0)
            else:
                print(__doc__)
                return 2
    except (IndexError, ValueError):
        print(__doc__)
        return 2
    out_layers, sources = {}, []
    for key, pattern in LAYERS:
        if key == "borders" and not borders:
            continue
        name = pattern.format(scale=scale)
        raw, where = fetch(name, folder)
        lines, before, after, dropped = layer(raw, tol, digits)
        out_layers[key] = lines
        # the release's address, never a local path (--from): the file is public
        sources.append({"file": name, "url": URL.format(release=RELEASE, name=name),
                        "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        print(f"{key}: {where}\n  {len(raw):,} bytes, {before:,} vertices -> "
              f"{len(lines):,} lines, {after:,} vertices ({dropped} small lines left out)")
    head = {"about": f"Natural Earth 1:{scale} ({RELEASE}), public domain "
                     "(naturalearthdata.com); simplified by tools/make_basemap.py",
            "release": RELEASE, "scale": f"1:{scale}", "tolerance": tol, "digits": digits,
            "source": sources}
    parts = ['{' + json.dumps(head, ensure_ascii=False)[1:-1] + ',\n"layers":{']
    for i, (key, lines) in enumerate(out_layers.items()):
        body = ",\n".join("[" + ",".join(number(v, digits) for v in line) + "]" for line in lines)
        parts.append(("," if i else "") + f'\n"{key}":[\n{body}\n]')
    parts.append("\n}}\n")
    text = "".join(parts)
    json.loads(text)                    # it must read back
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"-> {OUT.name}: {OUT.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
