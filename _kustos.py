#!/usr/bin/env python3
"""
_kustos.py -- um índice só: pessoas (personne), conceitos e formas (verba),
fontes (sources, à maneira do Zotero) e medidas do corpo (corpus).

Um JSON canônico como fonte de verdade, espelho markdown gerado, busca
literal, biblioteca padrão apenas, um arquivo só. As quatro coleções vivem
na mesma base e se ligam entre si: qualquer registro pode citar uma fonte
pelo campo FONTE, e as ligações tipadas atravessam coleções.

ARQUIVOS (todos lado a lado, mesmo prefixo)
    _kustos.json                  FONTE DE VERDADE.
    _kustos.log.<máquina>.jsonl   Diário só-de-acréscimo, um por máquina:
                                     cada salvamento anexa o registro inteiro.
                                     É o histórico completo (sem .bak).
    _kustos.lock.<máquina>.json   Aviso de "está aberto ali". Some ao fechar.
    _kustos_mirror.md             Espelho legível (Obsidian, celular).
    _kustos_conflicts/            *.sync-conflict-* já absorvidos. Nada é apagado.
    _kustos_old/                  O que `migrate` aposentou.

COMO O CONFLITO É RESOLVIDO
    1. Toda gravação relê o JSON, aplica só o registro que mudou e grava.
    2. Ao abrir, *.sync-conflict-* são fundidos registro a registro (o
       `updated_at` mais novo vence; apagamento é lembrado por lápide).
    3. Se a outra máquina deixou a trava, a barra de status avisa.

IDS: p_ pessoa · c_ conceito · f_ forma · s_ fonte · h_ medida.

LIVRO: além do id, todo registro tem um carimbo de registro (AAAAMMDDhhmmss)
e um número de ordem no Livro Geral (G). Folhas de 50 números, volumes de 200
folhas: o nº 1852 mora em G-1 · fl. 38. O número nunca muda nem volta a ser
usado; apagar deixa o número na folha como cancelado.

USO
    python _kustos.py                 abre a janela
    python _kustos.py app [id]        abre a janela, já no registro
    python _kustos.py doctor          valida a estrutura, não muda nada
    python _kustos.py mirror          refaz o espelho markdown
    python _kustos.py corpus          refaz o mapa do corpo (HTML) e abre
    python _kustos.py search <texto>  busca literal nas quatro coleções
    python _kustos.py cite <id|texto> [abnt|abnt-autor-data|bibtex|csl-json|bruto]
    python _kustos.py export [bibtex|csl|abnt] [arquivo]
    python _kustos.py import zotero <export.json|.bib>
    python _kustos.py import <notas.md>   "- Nome. Notas" -> pessoas
    python _kustos.py merge           absorve *.sync-conflict-* agora
    python _kustos.py history <id>    versões de um registro, pelos logs
    python _kustos.py replay          reconstrói o JSON só dos logs (.replay.json)
    python _kustos.py upgrade         index/2 -> index/3 (roda sozinho ao abrir)
    python _kustos.py migrate         personne + verba antigos -> _kustos.json
    python _kustos.py normalize       #tags e datas inline -> tags (pessoas)
"""

import hashlib
import json
import os
import re
import shutil
import socket
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent
STEM = "_kustos"
JSON_FILE = BASE / f"{STEM}.json"
MIRROR_FILE = BASE / f"{STEM}_mirror.md"
MIRROR_MARK = "<!-- gerado por _kustos.py -- não editar à mão -->"
CONFLICT_DIR = BASE / f"{STEM}_conflicts"
OLD_DIR = BASE / f"{STEM}_old"
SCHEMA = "index/4"
# o corpus é de uma pessoa só: o nome vai na legenda do mapa e, se houver
# registro de pessoa com esse nome, as medidas ficam ligadas a ele. O valor
# de verdade mora no JSON (ui.corpus_subject); este é só o padrão inicial.
CORPUS_SUBJECT = ""
# as coleções, na ordem em que aparecem em tudo. Cada uma tem um prefixo de
# id próprio, e é pelo prefixo que o programa sabe de que tipo é um registro.
COLLS = ("people", "entries", "sources", "corpus")
PREFIX = {"p_": "people", "c_": "entries", "f_": "entries",
          "s_": "sources", "h_": "corpus"}
COLL_PT = {"people": "pessoas", "entries": "verba", "sources": "fontes",
           "corpus": "corpus"}


# ids sem prefixo (os mais antigos do personne eram carimbos de tempo) são
# resolvidos por este registro, preenchido a cada leitura do vault
_ID_COLL = {}


def coll_of(rid):
    """A coleção de um id: pelo prefixo, ou pelo registro de ids lidos.
    Rascunhos são '__draft_<x>__'."""
    rid = rid or ""
    if rid.startswith("__draft_"):
        return {"p": "people", "e": "entries", "s": "sources",
                "h": "corpus"}.get(rid[8:9], "entries")
    coll = PREFIX.get(rid[:2])
    if coll:
        return coll
    return _ID_COLL.get(rid, "people")


def kind_of(rec):
    """person | concept | form | source | metric -- o que as ligações checam."""
    coll = coll_of(rec.get("id", ""))
    if coll == "entries":
        return rec.get("kind", "concept")
    return {"people": "person", "sources": "source", "corpus": "metric"}[coll]


def _host():
    raw = socket.gethostname().split(".")[0] or "maquina"
    return re.sub(r"[^A-Za-z0-9_-]+", "_", raw)[:32]


HOST = _host()
LOG_FILE = BASE / f"{STEM}.log.{HOST}.jsonl"
LOCK_FILE = BASE / f"{STEM}.lock.{HOST}.json"


def TODAY():
    return date.today().isoformat()


def NOW():
    return datetime.now().isoformat(timespec="seconds")


# ================================================================ comum

def sort_key(text):
    """Ordem alfabética que serve ao português e ao grego: sem caixa, e com
    acentos junto da letra que acentuam em vez de depois do z."""
    folded = unicodedata.normalize("NFKD", (text or "").casefold())
    return ("".join(c for c in folded if not unicodedata.combining(c)),
            text or "")


def slug(text):
    folded = unicodedata.normalize("NFKD", (text or "").casefold())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = re.sub(r"[^a-z0-9]+", "_", folded).strip("_")
    return folded or "verbete"


def one_liner(text, limit=140):
    text = " ".join((text or "").split())
    return text[:limit] + ("..." if len(text) > limit else "")


def stamp_of(rec):
    """Carimbo comparável de um registro. `updated_at` (data e hora) vence
    `updated` (só data); os dois são texto ISO, então comparam como texto."""
    return rec.get("updated_at") or rec.get("updated") or ""


# ================================================================ pessoas

def make_id(name, taken):
    base = "p_" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"


# Os caracteres de checkbox do Obsidian, para que as tarefas do espelho
# também sejam renderizadas lá.
TASK_MARK = {" ": "todo", "/": "doing", ">": "waiting",
             "x": "done", "-": "cancelled"}
MARK_OF = {"todo": " ", "doing": "/", "waiting": ">",
           "done": "x", "cancelled": "-"}
TASK_CYCLE = ("todo", "doing", "waiting", "done")
TASK_RE = re.compile(r"^\s*(?:[-*]\s*)?\[(.)\]\s*(.*)$")
# 2026-09-10 · 2026-09-10-1000 · 2026-09-10 10:00 · ~2026-09-10T10:00
DUE_RE = re.compile(
    r"(~?)(\d{4}-\d{2}-\d{2})(?:(?:[ T]|-)(\d{2}):?(\d{2}))?")


def split_due(body):
    """Tira o prazo de uma linha de tarefa: (texto, data, hora).

    A ÚLTIMA data da linha vence, então outras datas podem aparecer no
    texto. Uma marcada com ~ vence sempre uma sem marca."""
    hits = list(DUE_RE.finditer(body))
    if not hits:
        return body.strip(), "", ""
    marked = [m for m in hits if m.group(1)]
    m = (marked or hits)[-1]
    text = (body[:m.start()] + " " + body[m.end():]).strip()
    text = re.sub(r"\s{2,}", " ", text)
    hour, minute = m.group(3), m.group(4)
    return text, m.group(2), (f"{hour}:{minute}" if hour else "")


def parse_tasks(text):
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = TASK_RE.match(line)
        if m:
            state = TASK_MARK.get(m.group(1).lower(), "todo")
            body = m.group(2).strip()
        else:
            state, body = "todo", line
        body, due, at = split_due(body)
        if body:
            out.append({"text": body, "state": state, "due": due, "at": at})
    return out


def due_label(t):
    if not t.get("due"):
        return ""
    return t["due"] + (" " + t["at"] if t.get("at") else "")


def format_tasks(tasks):
    return "\n".join(
        "[{}] {}{}".format(MARK_OF.get(t.get("state", "todo"), " "),
                           t.get("text", ""),
                           " ~" + due_label(t) if t.get("due") else "")
        for t in (tasks or []))


# Os círculos de Covey, do mais externo ao mais interno.
CIRCLES = ("concern", "adapt", "influence", "control")


def parse_circles(value):
    got = {c for c in (value or []) if c in CIRCLES}
    return [c for c in CIRCLES if c in got]


LOG_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})(?:\s+(.*))?$")


def parse_log(text):
    """'2026-08-01   Conversa sobre o processo' -> {date, text}. Linha sem
    data recebe a de hoje."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = LOG_RE.match(line)
        if m:
            if (m.group(2) or "").strip():
                out.append({"date": m.group(1), "text": m.group(2).strip()})
        else:
            out.append({"date": TODAY(), "text": line})
    return out


def format_log(items):
    return "\n".join(f"{i.get('date', '')}   {i.get('text', '')}"
                      for i in (items or []))


def dated_tasks(p):
    return [t for t in p.get("tasks", [])
            if t.get("due") and t.get("state") not in ("done", "cancelled")]


def fold_finished_tasks(rec):
    """Tarefa concluída sai da lista e vira linha datada no log."""
    keep, moved = [], 0
    for t in rec.get("tasks", []):
        state = t.get("state")
        if state in ("done", "cancelled"):
            rec.setdefault("interactions", []).append({
                "date": TODAY(),
                "text": ("done: " if state == "done" else "cancelled: ")
                        + t.get("text", ""),
            })
            moved += 1
        else:
            keep.append(t)
    rec["tasks"] = keep
    return moved


def open_tasks(p, state=None):
    return [t for t in p.get("tasks", [])
            if (state is None or t.get("state") == state)]


def parse_aliases(text):
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        lang, sep, name = line.partition(":")
        if sep and name.strip():
            out.append({"lang": lang.strip().lower(), "name": name.strip()})
        else:
            out.append({"lang": "", "name": line})
    return out


def format_aliases(aliases):
    return "\n".join((f"{a.get('lang', '')}: {a.get('name', '')}"
                       if a.get("lang") else a.get("name", ""))
                      for a in (aliases or []))


def haystack_person(p):
    parts = [p.get("id", ""), p.get("name", ""), " ".join(p.get("tags", [])),
             p.get("notes_raw", ""), " ".join(p.get("links", [])),
             p.get("place", "")]
    for al in p.get("aliases", []):
        parts.append(al.get("lang", "") + " " + al.get("name", ""))
    for t in p.get("tasks", []):
        parts.append(t.get("text", "") + " " + due_label(t))
    parts.extend(p.get("circles", []))
    for it in p.get("interactions", []):
        parts.append(it.get("text", ""))
    return "  ".join(parts).lower()


def blank_person(name=""):
    return {"id": None, "name": name, "tags": [], "met": None, "notes_raw": "",
            "links": [], "place": "", "aliases": [], "interactions": [],
            "tasks": [], "circles": [], "followup": None, "updated": None}


def fix_person(p):
    p.setdefault("tags", [])
    p.setdefault("links", [])
    p.setdefault("interactions", [])
    p.setdefault("aliases", [])
    p.setdefault("place", "")
    p.setdefault("notes_raw", "")
    p.setdefault("met", None)
    p.setdefault("followup", None)
    p.setdefault("tasks", [])
    p["circles"] = parse_circles(p.get("circles"))
    fu = p.get("followup")
    if fu and (fu.get("text") or "").strip():
        p["tasks"].append({"text": fu["text"].strip(), "state": "todo",
                           "due": fu.get("date", "")})
        p["followup"] = None
    return p


# ---- importação: "- Nome. Notas" ou "## Nome"

ABBREVS = {"st", "mr", "mrs", "ms", "dr", "prof", "fr", "sr", "jr", "ss", "rev"}
URL_RE = re.compile(r"^(https?://|www\.)\S+$", re.IGNORECASE)


def split_name_notes(line):
    idx = 0
    while True:
        pos = line.find(". ", idx)
        if pos == -1:
            return line.strip(), ""
        words = line[:pos].split()
        last = words[-1].strip(".,;:").lower() if words else ""
        if last in ABBREVS or len(last) == 1:
            idx = pos + 2
            continue
        return line[:pos].strip(), line[pos + 1:].strip()


def strip_frontmatter(text):
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1:])
    return text


def parse_bullet_list(text):
    people, current = [], None
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("- ") or s.startswith("* "):
            body = s[2:].strip()
            if not body:
                continue
            if current and current["name"]:
                people.append(current)
            name, notes = split_name_notes(body)
            current = blank_person(name)
            current["notes_raw"] = notes
        elif s and current is not None:
            if URL_RE.match(s):
                current["links"].append(s)
            else:
                current["notes_raw"] = (current["notes_raw"] + " " + s).strip()
    if current and current["name"]:
        people.append(current)
    return people


def parse_headings(text):
    people = []
    for block in re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]:
        lines = block.strip().splitlines()
        if not lines:
            continue
        rec = blank_person(lines[0].strip())
        notes = []
        for line in lines[1:]:
            for key, field in (("tags", "tags"), ("met", "met"), ("links", "links")):
                m = re.match(key + r":\s*(.+)", line, re.IGNORECASE)
                if m:
                    if field == "met":
                        rec["met"] = m.group(1).strip()
                    else:
                        rec[field] = [x.strip() for x in
                                      re.split(r"[,\s]+" if field == "links" else ",",
                                               m.group(1)) if x.strip()]
                    break
            else:
                notes.append(line)
        rec["notes_raw"] = "\n".join(notes).strip()
        people.append(rec)
    return people


def merge_into(target, rec):
    """Dobra um registro que chega no que já existe. Texto já presente não
    é acrescentado de novo: importar o mesmo arquivo duas vezes não muda nada."""
    changed = False
    note = (rec.get("notes_raw") or "").strip()
    if note and note not in (target.get("notes_raw") or ""):
        stamp = f"[addendum {TODAY()}]"
        target["notes_raw"] = (
            (target.get("notes_raw") or "").rstrip() + "\n\n" + stamp + " " + note
        ).strip()
        changed = True
    for field in ("tags", "links"):
        for item in rec.get(field, []):
            if item not in target.setdefault(field, []):
                target[field].append(item)
                changed = True
    for al in rec.get("aliases", []):
        if al not in target.setdefault("aliases", []):
            target["aliases"].append(al)
            changed = True
    if not (target.get("place") or "").strip() and (rec.get("place") or "").strip():
        target["place"] = rec["place"].strip()
        changed = True
    if changed:
        touch(target)
    return changed


def ingest(text, data):
    """Devolve (added, merged, identical, merged_names) e grava cada registro
    tocado (com log)."""
    text = strip_frontmatter(text)
    people = (parse_headings(text) if re.search(r"^##\s+", text, flags=re.MULTILINE)
              else parse_bullet_list(text))
    taken = {p["id"] for p in data["people"]}
    index = {}
    for p in data["people"]:
        index.setdefault(p["name"].strip().lower(), p)
        for al in p.get("aliases", []):
            key = (al.get("name") or "").strip().lower()
            if key:
                index.setdefault(key, p)
    added = merged = identical = 0
    merged_names = []
    for rec in people:
        key = rec["name"].strip().lower()
        target = index.get(key)
        if target is None:
            rec["id"] = make_id(rec["name"], taken)
            rec["met"] = rec.get("met") or TODAY()
            touch(rec)
            taken.add(rec["id"])
            data["people"].append(rec)
            index[key] = rec
            log_put("people", rec)
            added += 1
        elif merge_into(target, rec):
            log_put("people", target)
            merged += 1
            merged_names.append(target["name"])
        else:
            identical += 1
    return added, merged, identical, merged_names


# ---- normalize: #tags e datas inline -> tags

DATE_KEYWORDS = ("birthday", "funeral", "deathday", "death", "born")
DATE_TAG_RE = re.compile(
    r"#?\b(" + "|".join(DATE_KEYWORDS) + r")\b\s*:?\s*"
    r"(\d{4}-\d{2}-\d{2}|-\d{2}-\d{2}|\d{2}-\d{2})", re.IGNORECASE)
BARE_HASHTAG_RE = re.compile(r"#(\w+)")


def extract_inline(text, tags):
    tags = list(tags)
    changed = False

    def repl_date(m):
        nonlocal changed
        t = f"{m.group(1).lower()}:{m.group(2)}"
        if t not in tags:
            tags.append(t)
        changed = True
        return ""

    def repl_tag(m):
        nonlocal changed
        w = m.group(1).lower()
        if w not in tags:
            tags.append(w)
        changed = True
        return ""

    out = BARE_HASHTAG_RE.sub(repl_tag, DATE_TAG_RE.sub(repl_date, text))
    out = re.sub(r"[;,]\s*[;,]", ";", out)
    out = re.sub(r"^[\s;,.]+|[\s;,.]+$", "", out)
    return re.sub(r"\s{2,}", " ", out).strip(), tags, changed


# ================================================================ verba

KINDS = ("concept", "form")

# As ligações TÍPICAS: que tipos de registro cada uma pode ligar. "*" é
# qualquer tipo. Uma ligação com rel fora desta tabela não é erro: é ATÍPICA,
# fica guardada com o rótulo que foi escrito e aparece no doctor para você
# decidir se a promove a típica (acrescentando-a aqui).
RELS = {
    # verba
    "expresses":     ("form", "concept"),
    "derives_from":  ("form", "form"),
    "cognate_of":    ("form", "form"),
    "borrows_from":  ("form", "form"),
    "calques":       ("form", "form"),
    "specializes":   ("concept", "concept"),
    "opposes":       ("concept", "concept"),
    "analogous_to":  ("concept", "concept"),
    "instrument_of": ("concept", "concept"),
    "requires":      ("concept", "concept"),
    # pessoas
    "coined_by":     ("*", "person"),
    "used_by":       ("*", "person"),
    "about":         ("*", "*"),
    "author_of":     ("person", "source"),
    "editor_of":     ("person", "source"),
    "translator_of": ("person", "source"),
    "knows":         ("person", "person"),
    # fontes
    "cites":         ("*", "source"),
    "attested_in":   ("form", "source"),
    "defined_in":    ("concept", "source"),
    "measured_in":   ("metric", "source"),
    "part_of":       ("source", "source"),
    "edition_of":    ("source", "source"),
    "translates":    ("source", "source"),
    "comments_on":   ("source", "source"),
    "responds_to":   ("source", "source"),
    # corpus
    "affects":       ("*", "metric"),
    "correlates":    ("metric", "metric"),
}
REL_PT = {
    "expresses": "exprime", "derives_from": "deriva de",
    "cognate_of": "cognato de", "borrows_from": "empresta de",
    "calques": "decalca", "specializes": "especializa",
    "opposes": "opõe-se a", "analogous_to": "análogo a",
    "instrument_of": "instrumento de", "requires": "exige",
    "coined_by": "cunhado por", "used_by": "usado por", "about": "sobre",
    "author_of": "autor de", "editor_of": "organizador de",
    "translator_of": "tradutor de", "knows": "conhece",
    "cites": "cita", "attested_in": "atestada em", "defined_in": "definido em",
    "measured_in": "medido em", "part_of": "parte de", "edition_of": "edição de",
    "translates": "traduz", "comments_on": "comenta", "responds_to": "responde a",
    "affects": "afeta", "correlates": "correlaciona com",
}


def rel_label(rel):
    return REL_PT.get(rel, rel + " (atípica)" if rel not in RELS else rel)

# Campos do verbete que podem ser reordenados ou escondidos.
CARD_FIELDS = [
    ("gloss",    "Glosa"),
    ("form_row", "Língua, romanização, atestada, status"),
    ("domains",  "Domínios"),
    ("tags",     "Tags"),
    ("source",   "Fonte"),
    ("notes",    "Notas"),
    ("edges",    "Ligações (texto)"),
    ("out",      "Ligações resolvidas"),
    ("inb",      "Citado por"),
    ("links",    "Links"),
]
FIELD_IDS = [f for f, _ in CARD_FIELDS]
FIELD_TITLE = dict(CARD_FIELDS)


def parse_layout(saved):
    out, seen = [], set()
    for item in (saved or []):
        if isinstance(item, dict):
            fid, on = item.get("id"), bool(item.get("on", True))
        else:
            fid, on = item, True
        if fid in FIELD_TITLE and fid not in seen:
            out.append((fid, on))
            seen.add(fid)
    for fid in FIELD_IDS:
        if fid not in seen:
            out.append((fid, True))
    return out


def year_of(span):
    span = (span or "").strip()
    if not span:
        return float("inf")
    try:
        return int(span.split("/")[0])
    except ValueError:
        return float("inf")


def new_id(kind, name, taken):
    base = ("c_" if kind == "concept" else "f_") + slug(name)[:40]
    cand, n = base, 2
    while cand in taken:
        cand = f"{base}_{n}"
        n += 1
    return cand


#   expresses c_timoneiro -800/400 — razão # fonte
EDGE_RE = re.compile(
    r"^\s*(?P<rel>[^\s#—]+)\s+(?P<to>[A-Za-z0-9_]+(?::[A-Za-z0-9_]+)?)"
    r"(?:\s+(?P<when>-?\d{1,4}(?:/-?\d{0,4})?))?"
    r"(?:\s*[—-]{1,2}\s*(?P<why>[^#]*))?"
    r"(?:\s*#\s*(?P<source>.*))?\s*$")


def norm_ref(ref):
    """'personne:p_x' era como o verba antigo apontava para o outro banco.
    Agora é tudo um banco só: fica 'p_x'."""
    ref = (ref or "").strip()
    if ":" in ref:
        return ref.split(":", 1)[1]
    return ref


def parse_edges(text, source_id):
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = EDGE_RE.match(line)
        if not m:
            out.append({"from": source_id, "rel": "?", "to": line,
                        "when": "", "why": "", "source": "",
                        "certainty": "working", "_bad": True})
            continue
        rel = m.group("rel").strip().lower()
        out.append({
            "from": source_id,
            "rel": rel,
            "to": norm_ref(m.group("to")),
            "when": (m.group("when") or "").strip(),
            "why": (m.group("why") or "").strip(),
            "source": (m.group("source") or "").strip(),
            "certainty": "established" if rel in RELS else "atypical",
        })
    return out


def format_edges(edges):
    lines = []
    for e in edges:
        line = f"{e.get('rel','')} {e.get('to','')}"
        if e.get("when"):
            line += f" {e['when']}"
        if e.get("why"):
            line += f" — {e['why']}"
        if e.get("source"):
            line += f" # {e['source']}"
        lines.append(line)
    return "\n".join(lines)


def fix_entry(e):
    e.pop("_provisional", None)
    e.setdefault("kind", "concept")
    e.setdefault("name", "")
    e.setdefault("gloss", "")
    e.setdefault("notes", "")
    e.setdefault("source", "")
    e.setdefault("tags", [])
    e.setdefault("links", [])
    e.setdefault("domains", [])
    e.setdefault("updated", TODAY())
    if e["kind"] == "form":
        e.setdefault("lang", "")
        e.setdefault("roman", "")
        e.setdefault("attested", "")
        e.setdefault("status", "attested")
    return e


def label_of(e):
    if not e:
        return "?"
    if e.get("kind") == "form":
        name = e.get("name", "")
        if e.get("roman"):
            name += f" [{e['roman']}]"
        return f"{name} ({e.get('lang','')})"
    return e.get("name", "")


def label_any(rec, data=None):
    """Rótulo de qualquer registro, de qualquer coleção."""
    if not rec:
        return "?"
    coll = coll_of(rec.get("id", ""))
    if coll == "entries":
        return label_of(rec)
    if coll == "sources":
        return source_label(rec, data)
    if coll == "corpus":
        return metric_label(rec)
    return rec.get("name", "")


def edges_from(data, rid):
    return [a for a in data["edges"] if a["from"] == rid]


def edges_to(data, rid):
    return [a for a in data["edges"] if a["to"] == rid]


def haystack_entry(e, data):
    parts = [e.get("id", ""), e.get("name", ""), e.get("roman", ""),
             e.get("gloss", ""), e.get("notes", ""), e.get("lang", ""),
             e.get("source", ""),
             " ".join(e.get("tags", [])), " ".join(e.get("domains", [])),
             " ".join(e.get("links", []))]
    for a in edges_from(data, e["id"]):
        parts.append(f"{a['rel']} {a['to']} {a.get('why','')} {a.get('source','')}")
    return "  ".join(parts).lower()


# ================================================================ fontes
#
# Uma fonte é qualquer coisa que se cita: livro, artigo, lei, acórdão, carta,
# vídeo, aula, conversa. O tipo é texto livre com uma lista de sugestões, e
# os campos são os do Zotero reduzidos ao que a citação precisa; o que não
# couber vai em `extra`, uma linha "chave: valor" por vez, como no Zotero.

SOURCE_TYPES = [
    "livro", "capítulo", "artigo", "tese", "dissertação", "monografia",
    "verbete", "dicionário", "relatório", "documento", "manuscrito", "carta",
    "lei", "decreto", "acórdão", "súmula", "parecer", "tratado",
    "página web", "vídeo", "áudio", "aula", "palestra", "entrevista",
    "conversa", "conjunto de dados", "obra de arte", "outro",
]
# tipo -> campos que fazem sentido mostrar (os demais ficam ocultos, mas
# nunca são apagados: mudar o tipo não perde dado)
SOURCE_FIELDS = {
    "*": ["authors", "date", "container", "publisher", "place", "edition",
          "volume", "issue", "pages", "doi", "isbn", "url", "accessed",
          "lang", "extra"],
    "livro": ["authors", "date", "publisher", "place", "edition", "volume",
              "pages", "isbn", "url", "lang", "extra"],
    "capítulo": ["authors", "date", "container", "publisher", "place",
                 "edition", "pages", "isbn", "url", "lang", "extra"],
    "artigo": ["authors", "date", "container", "place", "volume", "issue",
               "pages", "doi", "url", "lang", "extra"],
    "tese": ["authors", "date", "publisher", "place", "pages", "url", "extra"],
    "dissertação": ["authors", "date", "publisher", "place", "pages", "url", "extra"],
    "lei": ["authors", "date", "container", "publisher", "place", "url",
            "accessed", "extra"],
    "decreto": ["authors", "date", "container", "publisher", "place", "url",
                "accessed", "extra"],
    "acórdão": ["authors", "date", "container", "publisher", "place", "url",
                "accessed", "extra"],
    "súmula": ["authors", "date", "publisher", "url", "accessed", "extra"],
    "página web": ["authors", "date", "container", "url", "accessed", "extra"],
    "vídeo": ["authors", "date", "container", "url", "accessed", "extra"],
    "aula": ["authors", "date", "container", "place", "extra"],
    "entrevista": ["authors", "date", "container", "place", "url", "extra"],
    "conversa": ["authors", "date", "place", "extra"],
}
SOURCE_FIELD_PT = {
    "authors": "AUTORES  (um por linha: SOBRENOME, Nome  ·  ou p_… de uma pessoa)",
    "date": "DATA / ANO", "container": "EM  (periódico, livro, coletânea, site, órgão)",
    "publisher": "EDITORA / INSTITUIÇÃO / TRIBUNAL", "place": "LOCAL",
    "edition": "EDIÇÃO", "volume": "VOLUME", "issue": "NÚMERO",
    "pages": "PÁGINAS", "doi": "DOI", "isbn": "ISBN / ISSN", "url": "URL",
    "accessed": "ACESSO EM", "lang": "LÍNGUA",
    "extra": "EXTRA  (chave: valor, uma por linha — relator, ementa, número…)",
}
CITE_STYLES = ("abnt", "abnt-autor-data", "bibtex", "csl-json", "bruto")


def fix_source(s):
    s.setdefault("type", "outro")
    s.setdefault("name", "")
    s.setdefault("authors", [])
    for k in ("date", "container", "publisher", "place", "edition", "volume",
              "issue", "pages", "doi", "isbn", "url", "accessed", "lang",
              "raw", "notes"):
        s.setdefault(k, "")
    s.setdefault("extra", [])
    s.setdefault("tags", [])
    s.setdefault("links", [])
    s.setdefault("updated", TODAY())
    return s


def source_fields_for(stype):
    return SOURCE_FIELDS.get((stype or "").strip().lower(), SOURCE_FIELDS["*"])


def new_source_id(s, taken):
    """s_<sobrenome>_<ano>_<primeira palavra do título>"""
    au = author_names(s)
    head = slug(au[0].split(",")[0] if au else (s.get("container") or "anon"))[:20]
    year = year_of_source(s)
    word = slug(s.get("name", ""))[:16].strip("_")
    base = "s_" + "_".join(x for x in (head, year, word) if x).strip("_")
    cand, n = base, 2
    while cand in taken:
        cand = f"{base}_{n}"
        n += 1
    return cand


def year_of_source(s):
    m = re.search(r"\d{4}", s.get("date") or "")
    return m.group(0) if m else ""


_PERSON_NAMES = {}


def author_names(s, data=None):
    """Autores como texto. Uma linha 'p_xxxx' aponta para uma pessoa do
    índice; o nome dela é lido do vault quando ele é dado."""
    out = []
    for a in s.get("authors", []):
        a = (a or "").strip()
        if not a:
            continue
        if a.startswith("p_") and " " not in a:
            name = None
            if data is not None:
                p = next((p for p in data["people"] if p["id"] == a), None)
                name = p["name"] if p else None
            out.append(as_surname_first(name) if name else a)
        else:
            out.append(a)
    return out


def as_surname_first(name):
    """'Norbert Wiener' -> 'WIENER, Norbert'. Já invertido, fica como está."""
    name = (name or "").strip()
    if "," in name:
        return name
    parts = name.split()
    if len(parts) < 2:
        return name.upper()
    return parts[-1].upper() + ", " + " ".join(parts[:-1])


def abnt_author(a):
    """'Wiener, Norbert' -> 'WIENER, Norbert'; 'BRASIL' fica."""
    a = a.strip()
    if "," in a:
        sur, rest = a.split(",", 1)
        return sur.strip().upper() + ", " + rest.strip()
    return a.upper()


def abnt_authors(names):
    if not names:
        return ""
    if len(names) > 3:
        return abnt_author(names[0]) + " et al."
    return "; ".join(abnt_author(a) for a in names)


def extra_dict(s):
    out = {}
    for line in s.get("extra", []):
        k, sep, v = (line or "").partition(":")
        if sep:
            out[k.strip().lower()] = v.strip()
    return out


def cite(s, style="abnt", data=None):
    """Citação da fonte no estilo pedido. ABNT é a NBR 6023 no que cabe em
    metadados: o que faltar simplesmente não aparece."""
    style = (style or "abnt").lower()
    t = (s.get("type") or "outro").lower()
    names = author_names(s, data)
    title = (s.get("name") or "").strip()
    date = (s.get("date") or "").strip()
    year = year_of_source(s)
    ex = extra_dict(s)
    if style == "bruto":
        return s.get("raw") or title
    if style == "abnt-autor-data":
        if names:
            head = names[0].split(",")[0].strip().upper()
            if len(names) == 2:
                head += "; " + names[1].split(",")[0].strip().upper()
            elif len(names) > 2:
                head += " et al."
        else:
            head = (title.split(":")[0].split(".")[0] or "s.n.").upper()
        return f"({head}, {year or 's.d.'})"
    if style == "bibtex":
        return bibtex_of(s, names, year)
    if style == "csl-json":
        return json.dumps(csl_of(s, names), ensure_ascii=False, indent=2)
    # ---- abnt referência
    au = abnt_authors(names)
    bits = []

    def add(x):
        if x and str(x).strip():
            bits.append(str(x).strip())

    def dot(x):
        x = (x or "").strip()
        return x if not x or x.endswith((".", "?", "!")) else x + "."

    pub = s.get("publisher", "")
    place = s.get("place", "")
    pubblock = ": ".join(x for x in (place, pub) if x)
    if t in ("artigo",):
        add(dot(au))
        add(dot(title))
        cont = s.get("container", "")
        seg = [cont]
        if place:
            seg.append(place)
        if s.get("volume"):
            seg.append(f"v. {s['volume']}")
        if s.get("issue"):
            seg.append(f"n. {s['issue']}")
        if s.get("pages"):
            seg.append(f"p. {s['pages']}")
        seg.append(date or year)
        add(dot(", ".join(x for x in seg if x)))
        if s.get("doi"):
            add(f"DOI: {s['doi']}.")
    elif t == "capítulo":
        add(dot(au))
        add(dot(title))
        cont = s.get("container", "")
        org = ex.get("org") or ex.get("organizador") or ""
        add("In: " + (dot(abnt_author(org) + " (org.)") + " " if org else "") + dot(cont))
        if s.get("edition"):
            add(dot(f"{s['edition']}. ed" if s["edition"].isdigit() else s["edition"]))
        add(dot(", ".join(x for x in (pubblock, year) if x)))
        if s.get("pages"):
            add(f"p. {s['pages']}.")
    elif t in ("tese", "dissertação", "monografia"):
        add(dot(au))
        add(dot(title))
        add(dot(year))
        kind = t.capitalize()
        prog = ex.get("programa") or ex.get("curso") or ""
        add(dot(f"{kind}" + (f" ({prog})" if prog else "") + " – " +
                ", ".join(x for x in (pub, place) if x) + (f", {year}" if year else "")))
    elif t in ("lei", "decreto", "súmula", "tratado", "parecer"):
        add(dot(au or "BRASIL"))
        num = ex.get("número") or ex.get("numero") or ""
        head = title if not num else f"{t.capitalize()} nº {num}, de {abnt_date(date)}" \
            if date else f"{t.capitalize()} nº {num}"
        add(dot(head))
        if num and title:
            add(dot(title))
        cont = s.get("container", "")
        if cont:
            add(dot(", ".join(x for x in (cont, place, abnt_date(date)) if x)))
        if s.get("url"):
            add(f"Disponível em: {s['url']}.")
            if s.get("accessed"):
                add(f"Acesso em: {abnt_date(s['accessed'])}.")
    elif t == "acórdão":
        add(dot(au or pub or "BRASIL"))
        add(dot(title))
        rel = ex.get("relator") or ""
        if rel:
            add(dot("Relator: " + rel))
        if date:
            add(dot("Julgado em " + abnt_date(date)))
        cont = s.get("container", "")
        if cont:
            add(dot(cont))
        if s.get("url"):
            add(f"Disponível em: {s['url']}.")
            if s.get("accessed"):
                add(f"Acesso em: {abnt_date(s['accessed'])}.")
    elif t in ("página web", "vídeo", "áudio"):
        add(dot(au))
        add(dot(title))
        add(dot(", ".join(x for x in (s.get("container", ""), abnt_date(date) or year) if x)))
        if s.get("url"):
            add(f"Disponível em: {s['url']}.")
        if s.get("accessed"):
            add(f"Acesso em: {abnt_date(s['accessed'])}.")
    elif t in ("aula", "palestra", "entrevista", "conversa"):
        add(dot(au))
        add(dot(title))
        add(dot(", ".join(x for x in (s.get("container", ""), place, abnt_date(date)) if x)))
        add(dot(t.capitalize()))
    else:  # livro e o resto
        add(dot(au))
        add(dot(title))
        if s.get("edition"):
            e = s["edition"]
            add(dot(f"{e}. ed" if e.isdigit() else e))
        if s.get("volume"):
            add(dot(f"v. {s['volume']}"))
        add(dot(", ".join(x for x in (pubblock, year or date) if x)))
        if s.get("pages") and t not in ("livro",):
            add(f"p. {s['pages']}.")
        if s.get("url"):
            add(f"Disponível em: {s['url']}.")
            if s.get("accessed"):
                add(f"Acesso em: {abnt_date(s['accessed'])}.")
    out = " ".join(bits)
    if not out.strip(".") and s.get("raw"):
        return s["raw"]
    return out


BIBTYPE = {"livro": "book", "capítulo": "incollection", "artigo": "article",
           "tese": "phdthesis", "dissertação": "mastersthesis",
           "monografia": "mastersthesis", "relatório": "techreport",
           "página web": "online", "vídeo": "online", "conjunto de dados": "misc"}
CSLTYPE = {"livro": "book", "capítulo": "chapter", "artigo": "article-journal",
           "tese": "thesis", "dissertação": "thesis", "monografia": "thesis",
           "relatório": "report", "lei": "legislation", "decreto": "legislation",
           "acórdão": "legal_case", "página web": "webpage", "vídeo": "motion_picture",
           "áudio": "song", "entrevista": "interview", "aula": "speech",
           "palestra": "speech", "conversa": "personal_communication",
           "manuscrito": "manuscript", "carta": "personal_communication",
           "dicionário": "book", "verbete": "entry-dictionary"}
BIBTYPE.update({"dicionário": "book", "verbete": "inbook", "lei": "misc",
                "decreto": "misc", "acórdão": "misc", "manuscrito": "unpublished"})
CSL_TO_TYPE = {v: k for k, v in CSLTYPE.items()}
# onde vários tipos nossos caem no mesmo tipo CSL/BibTeX, a volta escolhe o
# mais comum
CSL_TO_TYPE.update({"book": "livro", "thesis": "tese", "speech": "aula",
                    "personal_communication": "conversa", "legislation": "lei",
                    "paper-conference": "artigo", "post-weblog": "página web",
                    "document": "documento", "entry-encyclopedia": "verbete"})
BIB_TO_TYPE = {v: k for k, v in BIBTYPE.items()}
BIB_TO_TYPE.update({"book": "livro", "mastersthesis": "dissertação",
                    "inbook": "capítulo", "inproceedings": "artigo",
                    "misc": "outro", "unpublished": "manuscrito"})

MESES = ["jan.", "fev.", "mar.", "abr.", "maio", "jun.", "jul.", "ago.",
         "set.", "out.", "nov.", "dez."]


def abnt_date(text):
    """'2002-01-10' -> '10 jan. 2002'; '2002-01' -> 'jan. 2002'; resto intacto."""
    m = re.match(r"^\s*(\d{4})-(\d{2})(?:-(\d{2}))?\s*$", text or "")
    if not m:
        return (text or "").strip()
    y, mo, d = m.group(1), int(m.group(2)), m.group(3)
    if not 1 <= mo <= 12:
        return text.strip()
    return (f"{int(d)} " if d else "") + f"{MESES[mo - 1]} {y}"


def bibkey(s, names, year):
    head = slug(names[0].split(",")[0] if names else s.get("name", "anon"))[:20]
    word = slug(s.get("name", ""))[:12].strip("_")
    return "_".join(x for x in (head, year, word) if x).strip("_") or s.get("id", "x")


def bibtex_of(s, names, year):
    t = BIBTYPE.get((s.get("type") or "").lower(), "misc")
    f = [("title", s.get("name")), ("author", " and ".join(names)),
         ("year", year), ("publisher", s.get("publisher")),
         ("address", s.get("place")), ("edition", s.get("edition")),
         ("volume", s.get("volume")), ("number", s.get("issue")),
         ("pages", s.get("pages")), ("doi", s.get("doi")), ("url", s.get("url")),
         ("urldate", s.get("accessed")), ("language", s.get("lang")),
         ("note", "; ".join(s.get("extra", [])))]
    cont = s.get("container")
    if cont:
        f.append(("journal" if t == "article" else "booktitle", cont))
    if t in ("phdthesis", "mastersthesis"):
        f.append(("school", s.get("publisher")))
    if s.get("isbn"):
        f.append(("issn" if t == "article" else "isbn", s["isbn"]))
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in f if v)
    return f"@{t}{{{bibkey(s, names, year)},\n{body}\n}}"


def csl_of(s, names):
    def person(n):
        if "," in n:
            fam, giv = n.split(",", 1)
            return {"family": fam.strip(), "given": giv.strip()}
        return {"literal": n}
    item = {"id": s.get("id"), "type": CSLTYPE.get((s.get("type") or "").lower(), "document"),
            "title": s.get("name")}
    if names:
        item["author"] = [person(n) for n in names]
    y = year_of_source(s)
    if y:
        parts = [int(x) for x in re.findall(r"\d+", s.get("date", ""))[:3]]
        if parts and parts[0] > 31:  # ano-mês-dia
            item["issued"] = {"date-parts": [parts]}
        else:
            item["issued"] = {"date-parts": [[int(y)]]}
    for k, ck in (("container", "container-title"), ("publisher", "publisher"),
                  ("place", "publisher-place"), ("edition", "edition"),
                  ("volume", "volume"), ("issue", "issue"), ("pages", "page"),
                  ("doi", "DOI"), ("isbn", "ISBN"), ("url", "URL"),
                  ("lang", "language"), ("notes", "note")):
        if s.get(k):
            item[ck] = s[k]
    if s.get("accessed"):
        parts = [int(x) for x in re.findall(r"\d+", s["accessed"])[:3]]
        if parts:
            item["accessed"] = {"date-parts": [parts]}
    if s.get("extra"):
        item["note"] = ((item.get("note", "") + "\n") if item.get("note") else "") \
            + "\n".join(s["extra"])
    return item


def source_from_csl(item):
    """Um item CSL-JSON (export do Zotero) -> registro de fonte."""
    s = fix_source({"type": CSL_TO_TYPE.get(item.get("type", ""), "outro"),
                    "name": item.get("title", "")})
    for a in item.get("author", []) + item.get("editor", []):
        if a.get("literal"):
            s["authors"].append(a["literal"])
        else:
            s["authors"].append(", ".join(x for x in (a.get("family", ""),
                                                       a.get("given", "")) if x))
    dp = (item.get("issued") or {}).get("date-parts") or [[]]
    s["date"] = "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(dp[0]))
    ap = (item.get("accessed") or {}).get("date-parts") or [[]]
    s["accessed"] = "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(ap[0]))
    for ck, k in (("container-title", "container"), ("publisher", "publisher"),
                  ("publisher-place", "place"), ("edition", "edition"),
                  ("volume", "volume"), ("issue", "issue"), ("page", "pages"),
                  ("DOI", "doi"), ("ISBN", "isbn"), ("ISSN", "isbn"), ("URL", "url"),
                  ("language", "lang"), ("abstract", "notes")):
        if item.get(ck):
            s[k] = str(item[ck])
    if item.get("note"):
        s["extra"] = [l for l in str(item["note"]).splitlines() if ":" in l]
        rest = [l for l in str(item["note"]).splitlines() if ":" not in l and l.strip()]
        if rest:
            s["notes"] = (s["notes"] + "\n" + "\n".join(rest)).strip()
    return s


BIB_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)\n\}", re.S)
BIB_FIELD_RE = re.compile(r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)\s*,?")


def sources_from_bibtex(text):
    out = []
    for m in BIB_ENTRY_RE.finditer(text):
        btype, body = m.group(1).lower(), m.group(3)
        f = {}
        for fm in BIB_FIELD_RE.finditer(body):
            v = fm.group(2).strip().strip(",").strip()
            if v[:1] in "{\"":
                v = v[1:-1]
            f[fm.group(1).lower()] = v.replace("{", "").replace("}", "").strip()
        s = fix_source({"type": BIB_TO_TYPE.get(btype, "outro"),
                        "name": f.get("title", "")})
        s["authors"] = [a.strip() for a in re.split(r"\s+and\s+", f.get("author", ""))
                        if a.strip()]
        s["date"] = f.get("year", "")
        s["container"] = f.get("journal") or f.get("booktitle") or ""
        s["publisher"] = f.get("publisher") or f.get("school") or f.get("institution") or ""
        for k in ("address", "edition", "volume", "number", "pages", "doi", "url",
                  "urldate", "isbn", "issn", "language", "note"):
            v = f.get(k, "")
            if not v:
                continue
            key = {"address": "place", "number": "issue", "urldate": "accessed",
                   "issn": "isbn", "language": "lang", "note": "notes"}.get(k, k)
            s[key] = v.replace("--", "-") if key == "pages" else v
        out.append(s)
    return out


def source_from_raw(text):
    """Um texto livre de referência ('LOCHTROP, Leonardo. Dicionário de
    alemão-português. 8. ed. São Paulo: Globo, 2006') vira uma fonte com o
    que der para ler: autor, título, ano. O texto inteiro fica em `raw`, e a
    citação 'bruto' devolve-o intacto."""
    raw = " ".join((text or "").split())
    s = fix_source({"type": "outro", "name": raw, "raw": raw})
    m = re.match(r"^([A-ZÀ-Ý][A-ZÀ-Ý'\- ]+,\s*[^.]+?)\.\s+(.+)$", raw)
    if m:
        s["authors"] = [m.group(1).strip()]
        rest = m.group(2)
        s["name"] = rest.split(". ")[0].strip().rstrip(".")
        y = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", rest)
        if y:
            s["date"] = y.group(1)
        e = re.search(r"(\d+)\.\s*ed\.", rest)
        if e:
            s["edition"] = e.group(1)
        pp = re.search(r"([A-ZÀ-Ý][^:.,]+):\s*([^,.]+),\s*(?:1[5-9]|20)\d\d", rest)
        if pp:
            s["place"], s["publisher"] = pp.group(1).strip(), pp.group(2).strip()
        if re.search(r"dicion[aá]rio|vocabul[aá]rio|dictionary", raw, re.I):
            s["type"] = "dicionário"
        elif s["publisher"]:
            s["type"] = "livro"
    elif re.match(r"^(https?://|www\.)", raw) or re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", raw):
        s["type"] = "página web"
        s["url"] = raw
    return s


def source_label(s, data=None):
    names = author_names(s, data)
    head = names[0].split(",")[0].strip() if names else ""
    y = year_of_source(s)
    title = one_liner(s.get("name", ""), 60)
    return " ".join(x for x in (head.upper() if head else "", f"({y})" if y else "",
                                title) if x) or s.get("id", "?")


def haystack_source(s, data):
    parts = [s.get("id", ""), s.get("name", ""), s.get("type", ""),
             " ".join(author_names(s, data)), s.get("date", ""),
             s.get("container", ""), s.get("publisher", ""), s.get("place", ""),
             s.get("doi", ""), s.get("isbn", ""), s.get("url", ""),
             s.get("notes", ""), s.get("raw", ""), " ".join(s.get("tags", [])),
             " ".join(s.get("extra", [])), " ".join(s.get("links", []))]
    for a in edges_from(data, s["id"]):
        parts.append(f"{a['rel']} {a['to']} {a.get('why', '')}")
    return "  ".join(parts).lower()


def resolve_source(text, data):
    """O campo FONTE de qualquer registro: um id s_… ou texto livre.
    Devolve (registro_da_fonte ou None, texto_para_mostrar)."""
    text = (text or "").strip()
    if text.startswith("s_"):
        s = next((x for x in data["sources"] if x["id"] == text), None)
        return s, (source_label(s, data) if s else f"{text} (fonte inexistente)")
    return None, text


# ================================================================ corpus
#
# O corpus é o monitoramento de saúde: cada registro é uma MEDIDA (métrica)
# de um sistema do corpo -- hemoglobina, pressão arterial, peso -- e guarda
# as suas LEITURAS ao longo do tempo, uma por linha, como o log de pessoas.

SYSTEMS = ["cardiovascular", "hematológico", "metabólico", "renal", "hepático",
           "endócrino", "imunológico", "respiratório", "musculoesquelético",
           "nervoso", "digestivo", "dermatológico", "antropometria", "sono",
           "atividade", "outro"]
READING_RE = re.compile(
    r"^\s*(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?\s+([-+]?\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)?)"
    r"(?:\s+(.*))?$")


def parse_readings(text):
    """'2026-09-01 13.5 jejum' -> {date, value, note}. Aceita '12/8' para
    pares (pressão). Linha sem data ganha a de hoje; linha só com data e
    sem valor é descartada, que é como se apaga uma leitura."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = READING_RE.match(line)
        if m:
            out.append({"date": m.group(1) + (" " + m.group(2) if m.group(2) else ""),
                        "value": m.group(3).replace(",", "."),
                        "note": (m.group(4) or "").strip()})
            continue
        m2 = re.match(r"^([-+]?\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)?)(?:\s+(.*))?$", line)
        if m2:
            out.append({"date": TODAY(), "value": m2.group(1).replace(",", "."),
                        "note": (m2.group(2) or "").strip()})
    out.sort(key=lambda r: r["date"])
    return out


def format_readings(items):
    return "\n".join(f"{r.get('date', '')}   {r.get('value', '')}"
                     + (f"   {r['note']}" if r.get("note") else "")
                     for r in (items or []))


def reading_number(value):
    try:
        return float(str(value).split("/")[0])
    except ValueError:
        return None


def out_of_range(m, r):
    """True se a leitura está fora da faixa de referência da medida."""
    v = reading_number(r.get("value"))
    if v is None:
        return False
    lo, hi = m.get("ref_low"), m.get("ref_high")
    try:
        if lo not in ("", None) and v < float(lo):
            return True
        if hi not in ("", None) and v > float(hi):
            return True
    except ValueError:
        pass
    return False


def fix_metric(m):
    m.setdefault("name", "")
    m.setdefault("system", "")
    m.setdefault("unit", "")
    m.setdefault("ref_low", "")
    m.setdefault("ref_high", "")
    m.setdefault("source", "")
    m.setdefault("notes", "")
    m.setdefault("tags", [])
    m.setdefault("links", [])
    m.setdefault("readings", [])
    m.setdefault("updated", TODAY())
    return m


def new_metric_id(m, taken):
    base = "h_" + slug(m.get("system", ""))[:12] + "_" + slug(m.get("name", ""))[:24]
    base = base.replace("__", "_").rstrip("_")
    cand, n = base, 2
    while cand in taken:
        cand = f"{base}_{n}"
        n += 1
    return cand


def last_reading(m):
    return m["readings"][-1] if m.get("readings") else None


def metric_label(m):
    return f"{m.get('name', '')} ({m.get('system', '')})" if m.get("system") \
        else m.get("name", "")


def haystack_metric(m, data):
    parts = [m.get("id", ""), m.get("name", ""), m.get("system", ""),
             m.get("unit", ""), m.get("notes", ""), m.get("source", ""),
             " ".join(m.get("tags", [])), " ".join(m.get("links", []))]
    for r in m.get("readings", []):
        parts.append(f"{r.get('date', '')} {r.get('value', '')} {r.get('note', '')}")
    for a in edges_from(data, m["id"]):
        parts.append(f"{a['rel']} {a['to']} {a.get('why', '')}")
    return "  ".join(parts).lower()


# ================================================================ arquivo

def blank_vault():
    return {"schema": SCHEMA, "ui": {}, "people": [], "entries": [],
            "sources": [], "corpus": [], "edges": [], "deleted": [],
            "book": {"opened": NOW(), "folha": FOLHA, "folhas": FOLHAS_POR_LIVRO}}


def fix_vault(data):
    data.setdefault("schema", SCHEMA)
    data.setdefault("ui", {})
    for coll in COLLS:
        data.setdefault(coll, [])
    data.setdefault("edges", [])
    data.setdefault("deleted", [])
    for p in data["people"]:
        fix_person(p)
    for e in data["entries"]:
        fix_entry(e)
    for s in data["sources"]:
        fix_source(s)
    for m in data["corpus"]:
        fix_metric(m)
    for coll in COLLS:
        for r in data[coll]:
            if r.get("id") and r["id"][:2] not in PREFIX:
                _ID_COLL[r["id"]] = coll
    for a in data["edges"]:
        a.setdefault("when", "")
        a.setdefault("why", "")
        a.setdefault("source", "")
        a.setdefault("certainty", "established")
        a["to"] = norm_ref(a.get("to"))
    return data


def read_vault(path):
    try:
        return fix_vault(json.loads(Path(path).read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return None


def load_json():
    if not JSON_FILE.exists():
        return blank_vault()
    data = read_vault(JSON_FILE)
    if data is None:
        raise SystemExit(f"{JSON_FILE.name} não pôde ser lido. Nada foi gravado. "
                         "Confira o arquivo, ou use `replay` para reconstruir "
                         "a partir dos logs.")
    return data


def write_json(data):
    """Escrita atômica: grava ao lado e troca. Sem .bak -- a história está
    no log. Antes, todo registro que ainda não tem número no livro recebe o
    seu: é por aqui que passa toda gravação, venha de onde vier."""
    novos = register_new(data)
    tmp = JSON_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    # no Windows, o Syncthing pode estar com o arquivo aberto por um instante
    import time
    for tent in range(6):
        try:
            tmp.replace(JSON_FILE)
            break
        except PermissionError:
            if tent == 5:
                raise
            time.sleep(0.25 * (tent + 1))
    if novos:
        log_append("reg", "vault", {"regs": novos})


def by_id(data):
    idx = {}
    for coll in COLLS:
        for r in data.get(coll, []):
            idx[r["id"]] = r
    return idx


def touch(rec):
    rec["updated"] = TODAY()
    rec["updated_at"] = NOW()


# ---- log só-de-acréscimo, um por máquina

def log_append(op, coll, payload):
    line = {"t": NOW(), "host": HOST, "op": op, "coll": coll}
    line.update(payload)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass          # o log é histórico, nunca impede a gravação


def log_put(coll, rec):
    clean = {k: v for k, v in rec.items() if not k.startswith("_")}
    log_append("put", coll, {"id": rec.get("id"), "rec": clean})


def log_del(coll, rid, name=""):
    log_append("del", coll, {"id": rid, "name": name})


def log_edges(from_id, edges):
    log_append("edges", "edges", {"id": from_id, "edges": edges})


def log_files():
    return sorted(BASE.glob(f"{STEM}.log.*.jsonl"))


def read_logs():
    lines = []
    for path in log_files():
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                raw = raw.strip()
                if raw:
                    try:
                        lines.append(json.loads(raw))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
    lines.sort(key=lambda l: l.get("t", ""))
    return lines


# ================================================================ livro
#
# Registro à maneira do cartório. Todo registro, ao entrar na base, recebe
# um carimbo de registro (AAAAMMDDhhmmss, único) e um número de ordem no
# Livro Geral. O número nunca muda nem é reaproveitado: o que é apagado
# continua na folha, como cancelado. Volume e folha saem do número por
# regra fixa, então o endereço de um registro não muda quando outros entram.
#
# FOLHA e FOLHAS_POR_LIVRO fazem parte do formato: mudá-los muda o endereço
# de tudo que já foi registrado.

BOOK = "G"
FOLHA = 50
FOLHAS_POR_LIVRO = 200
STAMP_FMT = "%Y%m%d%H%M%S"
REG_ORIGEM = {"id": "carimbo do id antigo", "log": "primeira gravação no log",
              "atualizado": "última atualização",
              "dia": "dia da última atualização", "abertura": "abertura do livro"}


def stamp_now():
    return datetime.now().strftime(STAMP_FMT)


def stamp_from(text):
    """'2026-09-27T23:42:59', '2026-09-27', '202609272342' ou
    '20260927234259' -> '20260927234259'; o que não for data -> ''."""
    digits = re.sub(r"\D", "", text or "")
    if len(digits) == 8:
        digits += "000000"
    elif len(digits) == 12:
        digits += "00"
    if len(digits) != 14:
        return ""
    try:
        datetime.strptime(digits, STAMP_FMT)
    except ValueError:
        return ""
    return digits


def stamp_label(stamp):
    s = stamp or ""
    if len(s) != 14:
        return s
    return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}:{s[12:]}"


def stamp_free(stamp, taken):
    """O carimbo pedido, ou o segundo seguinte livre."""
    while stamp in taken:
        stamp = (datetime.strptime(stamp, STAMP_FMT)
                 + timedelta(seconds=1)).strftime(STAMP_FMT)
    return stamp


def folha_of(n):
    """Folha corrida (1, 2, 3…) do número n, contando todos os volumes."""
    return (n - 1) // FOLHA + 1


def locus(n):
    """(volume, folha dentro do volume) do número n."""
    per_vol = FOLHA * FOLHAS_POR_LIVRO
    return (n - 1) // per_vol + 1, ((n - 1) % per_vol) // FOLHA + 1


def locus_label(n):
    if not n:
        return "sem registro"
    vol, fl = locus(n)
    return f"{BOOK}-{vol} · fl. {fl} · nº {n}"


def folha_label(folha):
    vol, fl = locus((folha - 1) * FOLHA + 1)
    return f"LIVRO {BOOK}-{vol} · FOLHA {fl}"


def book_rows(data):
    """Tudo o que ocupa número no livro: registros vivos e cancelados."""
    rows = [r for coll in COLLS for r in data.get(coll, [])]
    return rows + list(data.get("deleted", []))


def book_max(data):
    return max((r.get("reg_n") or 0 for r in book_rows(data)), default=0)


def first_seen_in_logs():
    first = {}
    for l in read_logs():
        if l.get("op") == "put" and l.get("id"):
            t = l.get("t", "")
            if t and (l["id"] not in first or t < first[l["id"]]):
                first[l["id"]] = t
    return first


def open_book(data):
    """Termo de abertura: numera de uma vez o que já existe sem número.

    Como a base antiga não guardava a data de criação, o carimbo de cada
    registro é a melhor evidência disponível, nesta ordem: id que já é um
    carimbo (o personne antigo), primeira gravação no log, última
    atualização com hora, dia da última atualização, e por fim o próprio
    momento da abertura. A evidência usada fica em `reg_origem`. Os números
    seguem a ordem dos carimbos; empates, a ordem alfabética."""
    first = first_seen_in_logs()
    opened = stamp_now()
    pend = []
    for coll in COLLS:
        for r in data.get(coll, []):
            if r.get("reg_n") or r.get("id", "").startswith("__"):
                continue
            idstamp = stamp_from(r["id"]) if re.fullmatch(r"\d{12}|\d{14}", r["id"]) else ""
            if idstamp:
                st, why = idstamp, "id"
            elif first.get(r["id"]):
                st, why = stamp_from(first[r["id"]]), "log"
            elif stamp_from(r.get("updated_at")):
                st, why = stamp_from(r["updated_at"]), "atualizado"
            elif stamp_from(r.get("updated")):
                st, why = stamp_from(r["updated"]), "dia"
            else:
                st, why = opened, "abertura"
            pend.append((st, sort_key(label_any(r, data)), r, why))
    pend.sort(key=lambda x: (x[0], x[1]))
    taken = {r.get("reg") for r in book_rows(data) if r.get("reg")}
    n = book_max(data)
    regs = {}
    for st, _, r, why in pend:
        n += 1
        r["reg"] = stamp_free(st, taken)
        taken.add(r["reg"])
        r["reg_n"] = n
        r["reg_origem"] = why
        regs[r["id"]] = [r["reg"], n, why]
    data["book"] = {"opened": NOW(), "folha": FOLHA, "folhas": FOLHAS_POR_LIVRO}
    return regs


def register_new(data):
    """Dá número a quem ainda não tem e desfaz números repetidos.

    Repetição só acontece quando as duas máquinas registram ao mesmo tempo
    sem sincronizar: fica com o número quem tem o carimbo mais antigo; o
    outro recebe o próximo livre e guarda o antigo em `reg_n_anterior`.
    Devolve {id: [carimbo, número]} do que mudou, para o log."""
    if "book" not in data:
        return open_book(data)
    regs = {}
    owner = {}
    for r in sorted((r for r in book_rows(data) if r.get("reg_n")),
                    key=lambda r: (r.get("reg") or "", r.get("id", ""))):
        owner.setdefault(r["reg_n"], r)
    taken = {r.get("reg") for r in book_rows(data) if r.get("reg")}
    n = book_max(data)
    live = [r for coll in COLLS for r in data.get(coll, [])
            if not r.get("id", "").startswith("__")]
    clash = [r for r in live if r.get("reg_n") and owner[r["reg_n"]] is not r]
    fresh = [r for r in live if not r.get("reg_n")]
    for r in clash:
        n += 1
        r["reg_n_anterior"] = r["reg_n"]
        r["reg_n"] = n
        regs[r["id"]] = [r["reg"], n]
    for r in sorted(fresh, key=lambda r: (r.get("updated_at") or "",
                                          sort_key(label_any(r, data)))):
        n += 1
        r["reg"] = stamp_free(stamp_now(), taken)
        taken.add(r["reg"])
        r["reg_n"] = n
        regs[r["id"]] = [r["reg"], n]
    return regs


def find_by_reg(data, key):
    """Registro (ou cancelado) pelo número de ordem ou pelo carimbo."""
    key = key.strip()
    for r in book_rows(data):
        if key.isdigit() and len(key) < 12 and r.get("reg_n") == int(key):
            return r
        if len(key) >= 12 and r.get("reg") == stamp_from(key):
            return r
    return None


# ---- as operações de gravação. Todas releem o disco antes.

def save_record(coll, rec, edges=None):
    """Grava UM registro: relê o JSON, substitui só ele, grava, loga.
    `edges`, se dado, substitui as ligações que saem dele. Devolve o vault."""
    data = load_json()
    rid = rec["id"]
    clean = {k: v for k, v in rec.items() if not k.startswith("_")}
    src = " ".join((clean.get("source") or "").split())
    if src and not src.startswith("s_"):
        for s in data.get("sources", []):
            if s.get("raw") and " ".join(s["raw"].split()) == src:
                clean["source"] = s["id"]
                break
    rows = data[coll]
    for i, old in enumerate(rows):
        if old.get("id") == rid:
            for k in ("reg", "reg_n", "reg_origem", "reg_n_anterior"):
                if old.get(k) and not clean.get(k):
                    clean[k] = old[k]
            rows[i] = clean
            break
    else:
        rows.append(clean)
    for d in data["deleted"]:
        # o id volta a existir: retoma o número que tinha antes de apagado
        if d.get("id") == rid and d.get("reg_n") and not clean.get("reg_n"):
            clean["reg"], clean["reg_n"] = d.get("reg"), d["reg_n"]
    data["deleted"] = [d for d in data["deleted"] if d.get("id") != rid]
    if edges is not None:
        data["edges"] = [a for a in data["edges"] if a["from"] != rid] + edges
    write_json(data)
    log_put(coll, clean)
    if edges is not None:
        log_edges(rid, edges)
    return data


def delete_record(coll, rid, name=""):
    data = load_json()
    gone = next((r for r in data[coll] if r.get("id") == rid), {})
    data[coll] = [r for r in data[coll] if r.get("id") != rid]
    n = len(data["edges"])
    data["edges"] = [a for a in data["edges"]
                     if a["from"] != rid and a["to"] != rid]
    tomb = {"id": rid, "at": NOW(), "name": name}
    if gone.get("reg_n"):
        # o número fica no livro, como cancelado
        tomb.update(reg=gone.get("reg"), reg_n=gone["reg_n"])
    data["deleted"].append(tomb)
    write_json(data)
    log_del(coll, rid, name)
    return data, n - len(data["edges"])


def rename_id(coll, old, new):
    """Um verbete nasce com id provisório; ao ganhar nome, o id definitivo é
    gerado e tudo que apontava para o antigo é reapontado."""
    data = load_json()
    for r in data[coll]:
        if r.get("id") == old:
            r["id"] = new
    for a in data["edges"]:
        if a["from"] == old:
            a["from"] = new
        if a["to"] == old:
            a["to"] = new
    write_json(data)
    return data


def save_ui(patch):
    data = load_json()
    ui = data.setdefault("ui", {})
    for k, v in patch.items():
        if v is None:
            ui.pop(k, None)
        else:
            ui[k] = v
    write_json(data)
    return data


# ================================================================ conflitos

def merge_vault(base, other):
    """Funde `other` em `base`, registro a registro. Devolve relatório.

    Regra: quem tem carimbo mais novo vence. Registro que só existe de um
    lado entra -- a menos que o outro lado tenha uma lápide mais nova que
    ele (foi apagado depois de criado). Ligações seguem o registro de
    origem que venceu."""
    report = {"added": [], "replaced": [], "kept": 0, "skipped_deleted": []}
    tomb_base = {d["id"]: d.get("at", "") for d in base.get("deleted", [])}
    tomb_other = {d["id"]: d.get("at", "") for d in other.get("deleted", [])}
    winners_from_other = set()

    for coll in COLLS:
        base.setdefault(coll, [])
        idx = {r["id"]: i for i, r in enumerate(base[coll])}
        for rec in other.get(coll, []):
            rid = rec.get("id")
            if not rid:
                continue
            if rid in idx:
                mine = base[coll][idx[rid]]
                if stamp_of(rec) > stamp_of(mine):
                    base[coll][idx[rid]] = rec
                    winners_from_other.add(rid)
                    report["replaced"].append((coll, rid, rec.get("name", "")))
                else:
                    report["kept"] += 1
            else:
                if rid in tomb_base and tomb_base[rid] >= stamp_of(rec):
                    report["skipped_deleted"].append((coll, rid, rec.get("name", "")))
                    continue
                base[coll].append(rec)
                winners_from_other.add(rid)
                report["added"].append((coll, rid, rec.get("name", "")))
        # lápides do outro lado apagam aqui o que foi criado antes delas
        for rid, at in tomb_other.items():
            if rid in idx and rid not in winners_from_other:
                mine = base[coll][idx[rid]]
                if at > stamp_of(mine):
                    base[coll] = [r for r in base[coll] if r["id"] != rid]
                    report["skipped_deleted"].append((coll, rid, mine.get("name", "")))
    if winners_from_other:
        base["edges"] = [a for a in base["edges"]
                         if a["from"] not in winners_from_other]
        base["edges"] += [a for a in other.get("edges", [])
                          if a["from"] in winners_from_other]
    # lápides: união, a mais nova por id
    tombs = {}
    for d in base.get("deleted", []) + other.get("deleted", []):
        if d.get("id") and d.get("at", "") >= tombs.get(d["id"], {}).get("at", ""):
            tombs[d["id"]] = d
    live = set(by_id(base))
    base["deleted"] = [d for d in tombs.values() if d["id"] not in live]
    return report


def relink_sources(data):
    """Campo FONTE em texto que coincide com o `raw` de uma fonte existente
    passa a apontar para ela. Roda depois de toda fusão, porque a outra
    máquina pode ter gravado o texto enquanto esta já tinha a fonte."""
    by_raw = {" ".join(s["raw"].split()): s["id"] for s in data.get("sources", [])
              if s.get("raw")}
    n = 0
    for coll in ("people", "entries", "corpus"):
        for r in data.get(coll, []):
            src = " ".join((r.get("source") or "").split())
            if src and not src.startswith("s_") and src in by_raw:
                r["source"] = by_raw[src]
                n += 1
    return n


def conflict_files():
    return sorted(BASE.glob(f"{STEM}.sync-conflict-*.json"))


def absorb_conflicts():
    """Funde todo *.sync-conflict-* na base e move o arquivo para a pasta de
    conflitos. Devolve lista de (arquivo, relatório)."""
    done = []
    for path in conflict_files():
        other = read_vault(path)
        if other is None:
            continue
        data = load_json()
        report = merge_vault(data, other)
        relink_sources(data)
        write_json(data)
        log_append("merge", "vault", {"file": path.name,
                                       "added": len(report["added"]),
                                       "replaced": len(report["replaced"])})
        # o que a fusão mudou entra no log como se tivesse sido digitado aqui,
        # para que `replay` reconstrua o mesmo estado
        idx = by_id(data)
        for coll, rid, _ in report["added"] + report["replaced"]:
            if rid in idx:
                log_put(coll, idx[rid])
                log_edges(rid, edges_from(data, rid))
        for coll, rid, name in report["skipped_deleted"]:
            if rid not in idx:
                log_del(coll, rid, name)
        CONFLICT_DIR.mkdir(exist_ok=True)
        try:
            shutil.move(str(path), str(CONFLICT_DIR / path.name))
        except OSError:
            pass
        done.append((path.name, report))
    # espelho em conflito é lixo regenerável, mas não se apaga: só se guarda
    for path in BASE.glob(f"{STEM}_mirror.sync-conflict-*.md"):
        CONFLICT_DIR.mkdir(exist_ok=True)
        try:
            shutil.move(str(path), str(CONFLICT_DIR / path.name))
        except OSError:
            pass
    return done


def describe_merge(reports):
    if not reports:
        return ""
    bits = []
    for name, r in reports:
        b = f"{name}: {len(r['added'])} entraram, {len(r['replaced'])} atualizados"
        if r["skipped_deleted"]:
            b += f", {len(r['skipped_deleted'])} apagados"
        bits.append(b)
    return " · ".join(bits)


# ================================================================ trava

def other_locks():
    out = []
    for path in BASE.glob(f"{STEM}.lock.*.json"):
        if path == LOCK_FILE:
            continue
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        since = info.get("since", "")
        try:
            age = datetime.now() - datetime.fromisoformat(since)
            if age.total_seconds() > 24 * 3600:
                continue        # trava velha: a máquina não fechou direito
        except ValueError:
            pass
        out.append(info)
    return out


def take_lock():
    try:
        LOCK_FILE.write_text(json.dumps({"host": HOST, "pid": os.getpid(),
                                         "since": NOW()}), encoding="utf-8")
    except OSError:
        pass


def drop_lock():
    try:
        LOCK_FILE.unlink()
    except OSError:
        pass


# ================================================================ doctor

def check(data):
    idx = by_id(data)
    errors, warnings = [], []
    seen = set()
    for p in data["people"]:
        if p["id"] in seen:
            errors.append(f"id repetido: {p['id']}")
        seen.add(p["id"])
        if not p.get("name"):
            errors.append(f"{p['id']}: pessoa sem nome")
    names = {}
    for p in data["people"]:
        names.setdefault(p["name"].strip().lower(), []).append(p["id"])
    for n, ids in names.items():
        if len(ids) > 1:
            warnings.append(f"nome repetido entre pessoas: {n} ({', '.join(ids)})")
    for e in data["entries"]:
        if e["id"] in seen:
            errors.append(f"id repetido: {e['id']}")
        seen.add(e["id"])
        if e["kind"] not in KINDS:
            errors.append(f"{e['id']}: tipo desconhecido {e['kind']!r}")
        if not e.get("name"):
            errors.append(f"{e['id']}: sem nome")
        if e["kind"] == "concept" and not (e.get("gloss") or "").strip():
            errors.append(f"{e['id']}: conceito sem glosa")
        if e["kind"] == "form":
            if not e.get("lang"):
                errors.append(f"{e['id']}: forma sem língua")
            recon = e.get("status") == "reconstructed"
            star = e.get("name", "").startswith("*")
            if recon and not star:
                warnings.append(f"{e['id']}: reconstruída sem asterisco")
            if star and not recon:
                errors.append(f"{e['id']}: asterisco mas status não é reconstructed")
    for s in data["sources"]:
        if s["id"] in seen:
            errors.append(f"id repetido: {s['id']}")
        seen.add(s["id"])
        if not (s.get("name") or s.get("raw")):
            errors.append(f"{s['id']}: fonte sem título")
        if not s.get("authors") and not s.get("raw"):
            warnings.append(f"{s['id']}: fonte sem autor")
    for m in data["corpus"]:
        if m["id"] in seen:
            errors.append(f"id repetido: {m['id']}")
        seen.add(m["id"])
        if not m.get("name"):
            errors.append(f"{m['id']}: medida sem nome")
        if not m.get("system"):
            warnings.append(f"{m['id']}: medida sem sistema")
        for r in m.get("readings", []):
            if out_of_range(m, r):
                warnings.append(f"{metric_label(m)}: {r['date']} = {r['value']} "
                                f"fora da referência")
    for coll in ("people", "entries", "corpus"):
        for r in data[coll]:
            src = (r.get("source") or "").strip()
            if src.startswith("s_") and src not in idx:
                errors.append(f"{r['id']}: FONTE aponta para {src}, que não existe")
    atypical = []
    for i, a in enumerate(data["edges"]):
        src = idx.get(a["from"])
        if not src:
            errors.append(f"ligação {i}: origem inexistente {a['from']}")
            continue
        dst = idx.get(a["to"])
        if not dst:
            errors.append(f"ligação {i}: alvo inexistente {a['to']} "
                          f"(em {label_any(src)})")
            continue
        rule = RELS.get(a["rel"])
        if not rule:
            atypical.append(f"{label_any(src)} -{a['rel']}-> {label_any(dst)}")
            continue
        sk = kind_of(src)
        dk = kind_of(dst)
        if (rule[0] not in ("*", sk)) or (rule[1] not in ("*", dk)):
            errors.append(
                f"ligação {i}: {a['rel']} liga {rule[0]}->{rule[1]}, "
                f"mas recebeu {sk}->{dk} ({label_any(src)} -> {label_any(dst)})")
        if a["from"] == a["to"]:
            errors.append(f"ligação {i}: liga {label_any(src)} a si mesmo")
        if not (a.get("why") or "").strip() and not (a.get("source") or "").strip():
            warnings.append(f"sem razão nem fonte: {label_any(src)} "
                            f"-{a['rel']}-> {label_any(dst)}")
    if atypical:
        warnings.append(f"{len(atypical)} ligação(ões) atípica(s), com rel fora "
                        "da tabela RELS (não é erro; promova ao editar o programa):")
        warnings.extend("    " + x for x in atypical)
    check_book(data, errors, warnings)
    return errors, warnings


def check_book(data, errors, warnings):
    if "book" not in data:
        warnings.append(f"livro {BOOK} ainda não aberto: abre na próxima gravação "
                        "(ou rode `upgrade`)")
        return
    rows = book_rows(data)
    by_n, by_stamp = {}, {}
    for r in rows:
        if not r.get("reg_n"):
            if r in data.get("deleted", []):
                continue
            warnings.append(f"{r.get('id')}: sem número no livro "
                            "(recebe na próxima gravação)")
            continue
        by_n.setdefault(r["reg_n"], []).append(r.get("id"))
        if not stamp_from(r.get("reg")):
            errors.append(f"{r.get('id')}: carimbo de registro inválido {r.get('reg')!r}")
        by_stamp.setdefault(r.get("reg"), []).append(r.get("id"))
    for n, ids in sorted(by_n.items()):
        if len(ids) > 1:
            errors.append(f"nº {n} repetido no livro: {', '.join(ids)} "
                          "(resolve sozinho na próxima gravação)")
    for st, ids in by_stamp.items():
        if st and len(ids) > 1:
            errors.append(f"carimbo {st} repetido: {', '.join(ids)}")
    top = max(by_n, default=0)
    gaps = [n for n in range(1, top + 1) if n not in by_n]
    if gaps:
        shown = ", ".join(str(n) for n in gaps[:10]) + (" …" if len(gaps) > 10 else "")
        warnings.append(f"{len(gaps)} número(s) sem registro nem cancelamento no "
                        f"livro: {shown}")


def summary(data):
    n_c = sum(1 for e in data["entries"] if e["kind"] == "concept")
    n_f = sum(1 for e in data["entries"] if e["kind"] == "form")
    n_r = sum(len(m.get("readings", [])) for m in data.get("corpus", []))
    return (f"{len(data['people'])} pessoas · {len(data['entries'])} verbetes "
            f"({n_c} conceitos, {n_f} formas) · {len(data.get('sources', []))} fontes · "
            f"{len(data.get('corpus', []))} medidas ({n_r} leituras) · "
            f"{len(data['edges'])} ligações")


def cmd_doctor():
    data = load_json()
    errors, warnings = check(data)
    print("\n" + summary(data))
    print(f"{len(errors)} erros, {len(warnings)} avisos\n")
    for x in errors:
        print("  ERRO  ", x)
    for x in warnings:
        print("  aviso ", x)
    others = other_locks()
    if others:
        print("\n  travas de outras máquinas:")
        for o in others:
            print(f"    {o.get('host')} desde {o.get('since')}")
    pend = conflict_files()
    if pend:
        print(f"\n  {len(pend)} arquivo(s) de conflito à espera: rode `merge`.")
    print()
    return 1 if errors else 0


# ================================================================ espelho

def mirror_locus(r):
    if not r.get("reg_n"):
        return "*sem registro no livro*"
    return f"*{locus_label(r['reg_n'])} · registrado {stamp_label(r.get('reg'))}*"


def write_mirror(data):
    if MIRROR_FILE.exists():
        head = MIRROR_FILE.read_text(encoding="utf-8")[:400]
        if MIRROR_MARK not in head:
            raise SystemExit(
                f"Não sobrescrevo {MIRROR_FILE.name}: não tem a marca de "
                "arquivo gerado, pode ter sido escrito à mão. Renomeie-o.")
    idx = by_id(data)
    out = [MIRROR_MARK, "", "# Index", "",
           f"*Espelho de {JSON_FILE.name}. {summary(data)}. "
           f"Refeito em {TODAY()}. Edite o app, não este arquivo.*", "",
           "# Personne", ""]
    for p in sorted(data["people"], key=lambda x: sort_key(x["name"])):
        out.append(f"## {p['name']}")
        out.append(mirror_locus(p))
        meta = []
        if p.get("tags"):
            meta.append("tags: " + ", ".join(p["tags"]))
        if p.get("place"):
            meta.append("domicilium: " + p["place"])
        if p.get("met"):
            meta.append("met: " + p["met"])
        if p.get("source"):
            meta.append("fonte: " + resolve_source(p["source"], data)[1])
        if meta:
            out.append("  ·  ".join(meta))
        if p.get("aliases"):
            out.append("also: " + "  ·  ".join(
                (f"[{a['lang']}] {a['name']}" if a.get("lang") else a["name"])
                for a in p["aliases"]))
        if p.get("notes_raw"):
            out += ["", p["notes_raw"]]
        if p.get("links"):
            out += [""] + [f"- {l}" for l in p["links"]]
        if p.get("interactions"):
            out.append("")
            for it in p["interactions"]:
                out.append(f"- {it.get('date', '')} — {it.get('text', '')}")
        if p.get("circles"):
            out += ["", "circles: " + ", ".join(p["circles"])]
        if p.get("tasks"):
            out.append("")
            for t in p["tasks"]:
                out.append("- [{}] {}{}".format(
                    MARK_OF.get(t.get("state", "todo"), " "), t.get("text", ""),
                    "  ~" + due_label(t) if t.get("due") else ""))
        citing = edges_to(data, p["id"])
        if citing:
            out.append("")
            for a in citing:
                out.append(f"- [[{label_any(idx.get(a['from']), data)}]] "
                           f"{rel_label(a['rel'])}")
        out += ["", f"`{p['id']}`", ""]
    out += ["# Verba", ""]
    for e in sorted(data["entries"], key=lambda x: sort_key(x["name"])):
        out.append(f"## {label_of(e)}")
        out.append(mirror_locus(e))
        meta = []
        if e["kind"] == "concept":
            meta.append("conceito")
            if e.get("domains"):
                meta.append("domínios: " + ", ".join(e["domains"]))
        else:
            meta.append("forma")
            if e.get("attested"):
                meta.append(f"atestada: {e['attested']}")
            if e.get("status") != "attested":
                meta.append(e.get("status", ""))
        if e.get("tags"):
            meta.append("tags: " + ", ".join(e["tags"]))
        if e.get("source"):
            meta.append("fonte: " + resolve_source(e["source"], data)[1])
        out.append("  ·  ".join(m for m in meta if m))
        out.append("")
        if e.get("gloss"):
            out += [f"**{e['gloss']}**", ""]
        if e.get("notes"):
            out += [e["notes"], ""]
        saindo = edges_from(data, e["id"])
        if saindo:
            for a in sorted(saindo, key=lambda x: year_of(x.get("when"))):
                alvo = idx.get(a["to"])
                line = f"- {rel_label(a['rel'])} " \
                       f"[[{label_any(alvo, data) if alvo else a['to']}]]"
                if a.get("when"):
                    line += f"  ({a['when']})"
                if a.get("why"):
                    line += f" — {a['why']}"
                if a.get("source"):
                    line += f"  [{a['source']}]"
                out.append(line)
            out.append("")
        if e.get("links"):
            out += list(e["links"]) + [""]
        out += [f"`{e['id']}`", ""]
    out += ["# Fontes", ""]
    for s in sorted(data["sources"], key=lambda x: sort_key(source_label(x, data))):
        out.append(f"## {source_label(s, data)}")
        out.append(mirror_locus(s))
        out.append("  ·  ".join(x for x in (s.get("type", ""),
                                            "tags: " + ", ".join(s["tags"]) if s.get("tags") else "") if x))
        out += ["", cite(s, "abnt", data), ""]
        if s.get("notes"):
            out += [s["notes"], ""]
        citing = edges_to(data, s["id"])
        if citing:
            for a in citing:
                out.append(f"- [[{label_any(idx.get(a['from']), data)}]] {rel_label(a['rel'])}")
            out.append("")
        for coll in ("people", "entries", "corpus"):
            users = [r for r in data[coll] if r.get("source") == s["id"]]
            if users:
                out.append(f"- fonte de {len(users)} {COLL_PT[coll]}: "
                           + ", ".join(label_any(r, data) for r in users[:12])
                           + (" …" if len(users) > 12 else ""))
                out.append("")
        if s.get("links"):
            out += list(s["links"]) + [""]
        out += [f"`{s['id']}`", ""]
    out += ["# Corpus", ""]
    for m in sorted(data["corpus"], key=lambda x: (sort_key(x.get("system", "")),
                                                   sort_key(x["name"]))):
        out.append(f"## {metric_label(m)}")
        out.append(mirror_locus(m))
        meta = []
        if m.get("unit"):
            meta.append("unidade: " + m["unit"])
        if m.get("ref_low") or m.get("ref_high"):
            meta.append(f"referência: {m.get('ref_low', '')}–{m.get('ref_high', '')}")
        if m.get("source"):
            meta.append("fonte: " + resolve_source(m["source"], data)[1])
        if meta:
            out.append("  ·  ".join(meta))
        out.append("")
        if m.get("notes"):
            out += [m["notes"], ""]
        for r in m.get("readings", []):
            flag = " (!)" if out_of_range(m, r) else ""
            out.append(f"- {r.get('date', '')} — {r.get('value', '')}{flag}"
                       + (f" — {r['note']}" if r.get("note") else ""))
        if m.get("readings"):
            out.append("")
        out += [f"`{m['id']}`", ""]
    MIRROR_FILE.write_text("\n".join(out), encoding="utf-8")


def cmd_mirror():
    data = load_json()
    write_mirror(data)
    print(f"{summary(data)} -> {MIRROR_FILE.name}")
    return 0


# ================================================================ busca

def cmd_search(query):
    data = load_json()
    terms = [t for t in query.lower().split() if t]
    hits = []
    for p in data["people"]:
        low = haystack_person(p)
        if all(t in low for t in terms):
            hits.append((sum(low.count(t) for t in terms), "pessoa", p))
    for e in data["entries"]:
        low = haystack_entry(e, data)
        if all(t in low for t in terms):
            hits.append((sum(low.count(t) for t in terms), e["kind"], e))
    for s in data["sources"]:
        low = haystack_source(s, data)
        if all(t in low for t in terms):
            hits.append((sum(low.count(t) for t in terms), "fonte", s))
    for m in data["corpus"]:
        low = haystack_metric(m, data)
        if all(t in low for t in terms):
            hits.append((sum(low.count(t) for t in terms), "medida", m))
    hits.sort(key=lambda x: -x[0])
    print(f'\nResultados para "{query}"  ({len(hits)} encontrados)\n')
    for _, kind, r in hits[:24]:
        sub = r.get("gloss") or one_liner(r.get("notes_raw") or r.get("notes", ""), 60)
        print(f"  {kind:8} {label_any(r, data):34} {sub[:60]}")
        print(f"  {'':8} {r['id']}")
    if not hits:
        print("  (nada encontrado)")
    print()
    return 0


# ================================================================ histórico

def cmd_history(rid):
    lines = [l for l in read_logs() if l.get("id") == rid]
    if not lines:
        print(f"nenhuma linha de log para {rid}")
        return 1
    for l in lines:
        op = l.get("op")
        if op == "put":
            rec = l.get("rec", {})
            print(f"{l['t']}  {l.get('host'):12} put   {label_any(rec)}")
            body = rec.get("notes_raw") or rec.get("gloss") or rec.get("notes") or ""
            if body:
                print(f"{'':36}{one_liner(body, 90)}")
        elif op == "del":
            print(f"{l['t']}  {l.get('host'):12} del   {l.get('name','')}")
        elif op == "edges":
            print(f"{l['t']}  {l.get('host'):12} edges {len(l.get('edges', []))} ligações")
    return 0


def cmd_replay():
    """Reconstrói um vault só dos logs -- o teste de que o log basta.
    Não toca no JSON principal: escreve _kustos.replay.json."""
    data = blank_vault()
    idx = {}
    regs = {}
    for l in read_logs():
        if l.get("op") == "reg":
            regs.update(l.get("regs", {}))
            continue
        op, coll, rid = l.get("op"), l.get("coll"), l.get("id")
        if op == "put" and coll in COLLS:
            rec = l.get("rec", {})
            if rid in idx:
                rows = data[coll]
                for i, r in enumerate(rows):
                    if r["id"] == rid:
                        rows[i] = rec
            else:
                data[coll].append(rec)
            idx[rid] = coll
        elif op == "del" and rid in idx:
            data[idx[rid]] = [r for r in data[idx[rid]] if r["id"] != rid]
            data["edges"] = [a for a in data["edges"]
                             if a["from"] != rid and a["to"] != rid]
            del idx[rid]
        elif op == "edges":
            data["edges"] = [a for a in data["edges"] if a["from"] != rid] \
                + l.get("edges", [])
    # o número de quem foi gravado antes de ter número vem das linhas "reg"
    for r in book_rows(data):
        v = regs.get(r.get("id"))
        if v and not r.get("reg_n"):
            r["reg"], r["reg_n"] = v[0], v[1]
            if len(v) > 2:
                r["reg_origem"] = v[2]
    out = JSON_FILE.with_name(f"{STEM}.replay.json")
    out.write_text(json.dumps(fix_vault(data), indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print(f"{summary(data)} -> {out.name}")
    return 0


# ================================================================ migração

def cmd_migrate():
    """Funde as duas instâncias antigas em _kustos.json.

    Entram: o JSON atual de cada instância e os *.sync-conflict-* dela (que
    são o estado da outra máquina). Os .bak entram só como fonte de
    registros que não existam em lugar nenhum, porque um .bak também guarda
    o que foi apagado de propósito. Nada é apagado: os arquivos antigos vão
    para _kustos_old/."""
    if JSON_FILE.exists():
        print(f"{JSON_FILE.name} já existe; a migração só roda numa pasta sem ele.")
        return 1
    data = blank_vault()
    moved = []

    def take(coll_name, key, path, tag):
        raw = read_any(path)
        if raw is None:
            print(f"  ignorado (ilegível): {path.name}")
            return
        other = blank_vault()
        other[coll_name] = raw.get(key, [])
        if key == "entries":
            other["edges"] = raw.get("edges", [])
        if not data.get("ui") and raw.get("ui"):
            data["ui"] = raw["ui"]
        fix_vault(other)
        rep = merge_vault(data, other)
        print(f"  {tag:10} {path.name}: {len(other[coll_name])} registros, "
              f"{len(rep['added'])} novos, {len(rep['replaced'])} mais novos")
        moved.append(path)

    for inst, key in (("personne", "people"), ("verba", "entries")):
        main = BASE / f"{STEM}_{inst}.json"
        print(f"\n{inst}:")
        if main.exists():
            take(key, key, main, "atual")
        for p in sorted(BASE.glob(f"{STEM}_{inst}.sync-conflict-*.json")):
            take(key, key, p, "conflito")
        for p in sorted(BASE.glob(f"{STEM}_{inst}.bak*.json")):
            # .bak: só o que não existe em lugar nenhum (nem em lápide)
            raw = read_any(p)
            if raw is None:
                continue
            have = set(by_id(data))
            novos = [r for r in raw.get(key, []) if r.get("id") and r["id"] not in have]
            for r in novos:
                data[key].append(r)
            if key == "entries":
                ids = {r["id"] for r in novos}
                data["edges"] += [a for a in raw.get("edges", []) if a["from"] in ids]
            print(f"  {'bak':10} {p.name}: {len(novos)} registros que só existiam ali")
            moved.append(p)
    # verbetes sem nome eram provisórios que nunca foram salvos com nome
    vazios = [e["id"] for e in data["entries"] if not (e.get("name") or "").strip()]
    data["entries"] = [e for e in data["entries"] if e["id"] not in vazios]
    data["edges"] = [a for a in data["edges"]
                     if a["from"] not in vazios and a["to"] not in vazios]
    if vazios:
        print(f"\n  {len(vazios)} verbete(s) sem nome descartados: {', '.join(vazios)}")
    fix_vault(data)
    ui = data.setdefault("ui", {})
    for k in ("panes", "panes_locked"):
        ui.pop(k, None)
    write_json(data)
    for coll in ("people", "entries"):
        for r in data[coll]:
            log_put(coll, r)
    for rid in {a["from"] for a in data["edges"]}:
        log_edges(rid, edges_from(data, rid))
    write_mirror(data)
    OLD_DIR.mkdir(exist_ok=True)
    for inst in ("personne", "verba"):
        for p in list(BASE.glob(f"{STEM}_{inst}*")):
            if p.is_file() and p.suffix in (".json", ".md", ".py", ".tmp"):
                try:
                    shutil.move(str(p), str(OLD_DIR / p.name))
                except OSError as err:
                    print(f"  não movi {p.name}: {err}")
    launcher = BASE / f"{STEM}_launcher.json"
    if launcher.exists():
        shutil.move(str(launcher), str(OLD_DIR / launcher.name))
    print(f"\n{summary(data)} -> {JSON_FILE.name}")
    print(f"Arquivos antigos em {OLD_DIR.name}/. Espelho em {MIRROR_FILE.name}.\n")
    return 0


def read_any(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def cmd_import(path_str):
    path = Path(path_str)
    if not path.exists():
        raise SystemExit(f"Arquivo não existe: {path}")
    data = load_json()
    added, merged, identical, names = ingest(path.read_text(encoding="utf-8"), data)
    write_json(data)
    write_mirror(data)
    print(f"{added} pessoas novas de {path.name}.")
    if merged:
        print(f"{merged} receberam addendum [addendum {TODAY()}]:")
        for n in names[:12]:
            print("    · " + one_liner(n, 60))
    if identical:
        print(f"{identical} já tinham tudo; intocadas.")
    return 0


def cmd_normalize():
    data = load_json()
    touched = 0
    for p in data["people"]:
        tags = list(p.get("tags", []))
        new_name, tags, a = extract_inline(p.get("name", ""), tags)
        new_notes, tags, b = extract_inline(p.get("notes_raw", ""), tags)
        if a or b:
            if new_name:
                p["name"] = new_name
            p["notes_raw"] = new_notes
            p["tags"] = tags
            touch(p)
            log_put("people", p)
            touched += 1
    write_json(data)
    write_mirror(data)
    print(f"{touched} pessoas normalizadas. Espelho refeito.")
    return 0


def cmd_merge():
    reports = absorb_conflicts()
    if not reports:
        print("nenhum arquivo de conflito na pasta")
        return 0
    for name, r in reports:
        print(f"\n{name}")
        for coll, rid, nm in r["added"]:
            print(f"  + {nm}  ({rid})")
        for coll, rid, nm in r["replaced"]:
            print(f"  ~ {nm}  ({rid})")
        for coll, rid, nm in r["skipped_deleted"]:
            print(f"  - {nm}  ({rid}, apagado)")
        print(f"  {r['kept']} mantidos como estavam")
    write_mirror(load_json())
    print(f"\nconflitos guardados em {CONFLICT_DIR.name}/\n")
    return 0


# ================================================================ upgrade

def schema_version(data):
    try:
        return int(str(data.get("schema", "index/2")).split("/")[1])
    except (IndexError, ValueError):
        return 2


def needs_upgrade(data):
    return schema_version(data) < 4 or "book" not in data


def upgrade_vault(data):
    """index/2 -> index/3: cria as coleções de fontes e corpus e transforma
    cada texto distinto do campo FONTE em UMA fonte, apontada pelo id.
    O texto original fica em `raw` e continua a ser o que a citação 'bruto'
    devolve, então nada do que estava escrito se perde.

    index/3 -> index/4: abre o Livro Geral e numera o que já existe."""
    fix_vault(data)
    report = {"sources": [], "relinked": 0, "regs": {}}
    if schema_version(data) < 3:
        upgrade_sources(data, report)
    if "book" not in data:
        report["regs"] = open_book(data)
    data["schema"] = SCHEMA
    data.setdefault("ui", {}).setdefault("corpus_subject", CORPUS_SUBJECT)
    return report


def upgrade_sources(data, report):
    taken = set(by_id(data))
    by_raw = {s.get("raw", ""): s["id"] for s in data["sources"] if s.get("raw")}
    for coll in ("people", "entries", "corpus"):
        for r in data[coll]:
            src = (r.get("source") or "").strip()
            if not src or src.startswith("s_"):
                continue
            key = " ".join(src.split())
            sid = by_raw.get(key)
            if not sid:
                s = source_from_raw(key)
                s["id"] = new_source_id(s, taken)
                taken.add(s["id"])
                touch(s)
                data["sources"].append(s)
                by_raw[key] = s["id"]
                sid = s["id"]
                report["sources"].append(s)
            r["source"] = sid
            report["relinked"] += 1


def describe_opening(data, regs):
    if not regs:
        return ""
    n = max(v[1] for v in regs.values())
    why = {}
    for v in regs.values():
        why[v[2]] = why.get(v[2], 0) + 1
    bits = ", ".join(f"{k} por {REG_ORIGEM[w]}" for w, k in
                     sorted(why.items(), key=lambda x: -x[1]))
    return (f"Livro {BOOK} aberto: {len(regs)} registros numerados, até "
            f"{locus_label(n)}. Carimbos inferidos: {bits}.")


def cmd_upgrade(quiet=False):
    data = load_json()
    if not needs_upgrade(data):
        if not quiet:
            print(f"{JSON_FILE.name} já está em {data.get('schema')}.")
        return ""
    v = schema_version(data)
    report = upgrade_vault(data)
    write_json(data)
    for s in report["sources"]:
        log_put("sources", s)
    if v < 3:
        for coll in ("people", "entries", "corpus"):
            for r in data[coll]:
                if (r.get("source") or "").startswith("s_"):
                    log_put(coll, r)
    if report["regs"]:
        log_append("reg", "vault", {"regs": report["regs"], "abertura": True})
    log_append("upgrade", "vault", {"to": SCHEMA, "sources": len(report["sources"])})
    opening = describe_opening(data, report["regs"])
    if not quiet:
        print(f"\n{JSON_FILE.name} -> {SCHEMA}")
        if v < 3:
            print(f"{len(report['sources'])} fonte(s) criadas a partir do campo FONTE, "
                  f"{report['relinked']} registros reapontados:")
            for s in report["sources"]:
                print(f"  {s['id']:40} {source_label(s, data)}")
        if opening:
            print(opening)
        print()
    return opening


# ================================================================ citação

def find_source(data, key):
    if key in by_id(data):
        return by_id(data)[key]
    low = key.lower()
    hits = [s for s in data["sources"] if low in haystack_source(s, data)]
    return hits[0] if len(hits) == 1 else None


def cmd_cite(key, style="abnt"):
    data = load_json()
    s = find_source(data, key)
    if not s:
        print(f"fonte não encontrada (ou ambígua): {key}")
        return 1
    if style not in CITE_STYLES:
        print(f"estilo desconhecido; use um de: {', '.join(CITE_STYLES)}")
        return 1
    print(cite(s, style, data))
    return 0


def cmd_export(fmt, path_str=None):
    data = load_json()
    fmt = (fmt or "bibtex").lower()
    if fmt == "bibtex":
        body = "\n\n".join(cite(s, "bibtex", data) for s in data["sources"])
        ext = ".bib"
    elif fmt in ("csl", "csl-json"):
        body = json.dumps([csl_of(s, author_names(s, data)) for s in data["sources"]],
                          ensure_ascii=False, indent=2)
        ext = ".json"
    elif fmt == "abnt":
        body = "\n\n".join(sorted((cite(s, "abnt", data) for s in data["sources"]),
                                  key=sort_key))
        ext = ".txt"
    else:
        print("formato: bibtex | csl | abnt")
        return 1
    out = Path(path_str) if path_str else BASE / f"{STEM}_fontes{ext}"
    out.write_text(body, encoding="utf-8")
    print(f"{len(data['sources'])} fontes -> {out.name}")
    return 0


def import_sources(items, data):
    """Fontes vindas de fora entram sem duplicar: mesmo DOI, mesma URL ou
    mesmo (primeiro autor, ano, título) é a mesma fonte."""
    def key_of(s):
        if s.get("doi"):
            return "doi:" + s["doi"].lower()
        if s.get("url"):
            return "url:" + s["url"].lower().rstrip("/")
        au = author_names(s)
        return "k:" + slug((au[0] if au else "") + year_of_source(s) + s.get("name", ""))
    have = {key_of(s): s for s in data["sources"]}
    taken = set(by_id(data))
    added = skipped = 0
    for s in items:
        k = key_of(s)
        if k in have:
            skipped += 1
            continue
        s["id"] = new_source_id(s, taken)
        taken.add(s["id"])
        touch(s)
        data["sources"].append(s)
        have[k] = s
        log_put("sources", s)
        added += 1
    return added, skipped


def cmd_import_zotero(path_str):
    path = Path(path_str)
    if not path.exists():
        raise SystemExit(f"Arquivo não existe: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".bib" or text.lstrip().startswith("@"):
        items = sources_from_bibtex(text)
    else:
        raw = json.loads(text)
        if isinstance(raw, dict):
            raw = raw.get("items", [raw])
        items = [source_from_csl(it) for it in raw]
    data = load_json()
    added, skipped = import_sources(items, data)
    write_json(data)
    write_mirror(data)
    print(f"{added} fontes importadas de {path.name}, {skipped} já existiam.")
    return 0


# ================================================================ mapa do corpo
#
# O corpus tem um segundo espelho, em HTML: o mapa do corpo do protótipo
# "Corpus" (o Homem Vitruviano com uma lâmina anatômica por sistema), agora
# alimentado pelos dados reais. É só leitura -- a digitação é na janela --
# e é refeito a cada gravação de medida, como o espelho markdown.

CORPUS_HTML_FILE = BASE / f"{STEM}_corpus.html"

# de que lâmina anatômica cada sistema do corpus se serve, e onde fica o
# marcador na figura. Sistemas fora desta tabela ficam numa fila à parte.
PLATE_OF = {
    "nervoso": "neuro", "sono": "neuro",
    "cardiovascular": "cardio", "respiratório": "cardio",
    "metabólico": "metabolic", "endócrino": "metabolic",
    "renal": "renal", "hepático": "renal", "digestivo": "renal",
    "hematológico": "hema", "imunológico": "hema",
    "musculoesquelético": "musculo", "antropometria": "musculo",
    "atividade": "musculo",
}
MARKER_OF = {"neuro": (100, 38), "cardio": (100, 110), "metabolic": (100, 160),
             "renal": (100, 210), "hema": (50, 108), "musculo": (76, 352)}


def corpus_payload(data):
    """Agrupa as medidas por sistema no formato que a página espera."""
    systems = {}
    for m in data.get("corpus", []):
        sname = m.get("system") or "outro"
        sys_ = systems.setdefault(sname, {"id": slug(sname), "name": sname,
                                          "plate": PLATE_OF.get(sname), "metrics": []})
        hist = []
        for r in m.get("readings", []):
            v = reading_number(r.get("value"))
            if v is None:
                continue
            hist.append([r.get("date", "")[:10], v, r.get("value"), r.get("note", "")])
        lo = reading_number(m.get("ref_low")) if m.get("ref_low") not in ("", None) else None
        hi = reading_number(m.get("ref_high")) if m.get("ref_high") not in ("", None) else None
        src, shown = resolve_source(m.get("source", ""), data)
        sys_["metrics"].append({"id": m["id"], "label": m.get("name", ""),
                                "unit": m.get("unit", ""), "low": lo, "high": hi,
                                "history": sorted(hist), "notes": m.get("notes", ""),
                                "source": shown})
    out = []
    used = {}
    for sname in sorted(systems, key=sort_key):
        s = systems[sname]
        if s["plate"] in MARKER_OF:
            x, y = MARKER_OF[s["plate"]]
            # dois sistemas na mesma lâmina ficam lado a lado, não em cima
            n = used.get(s["plate"], 0)
            used[s["plate"]] = n + 1
            s["marker"] = [x + 16 * n, y]
        out.append(s)
    return out


def write_corpus_html(data):
    payload = json.dumps({"systems": corpus_payload(data), "built": TODAY(),
                          "summary": summary(data)}, ensure_ascii=False)
    html = CORPUS_HTML.replace("/*__DATA__*/null", payload)
    CORPUS_HTML_FILE.write_text(html, encoding="utf-8")


def cmd_corpus(open_it=True):
    data = load_json()
    write_corpus_html(data)
    print(f"{len(data['corpus'])} medidas -> {CORPUS_HTML_FILE.name}")
    if open_it:
        import webbrowser
        webbrowser.open(CORPUS_HTML_FILE.as_uri())
    return 0


CORPUS_HTML = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Corpus</title>
<style>
  :root {
    --paper: #f2ede2; --surface: #fbf8f2; --surface-2: #ede6d5;
    --ink: #201d16; --ink-muted: #6f6754; --ink-faint: #a49b84;
    --line: #d9d0bc; --line-strong: #b5a988;
    --accent: #7a2e2e; --accent-soft: #7a2e2e22;
    --ok: #4a5d3a; --ok-soft: #4a5d3a1c;
    --warn: #8a6a1f; --warn-soft: #8a6a1f1c;
    --focus: #2f5f8a;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --paper: #17150f; --surface: #201d16; --surface-2: #29251b;
      --ink: #eee8d8; --ink-muted: #a89f89; --ink-faint: #6f6754;
      --line: #3a352a; --line-strong: #4d4735;
      --accent: #c98686; --accent-soft: #c9868630;
      --ok: #8fae78; --ok-soft: #8fae7828;
      --warn: #d1a94a; --warn-soft: #d1a94a28;
      --focus: #7fb2de;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--paper); color: var(--ink);
    font-family: ui-monospace, "Cascadia Mono", Consolas, "DejaVu Sans Mono", "Courier New", monospace;
    font-size: 14px; padding: 0 20px 64px; -webkit-font-smoothing: antialiased; }
  .mono { font-variant-numeric: tabular-nums; }
  .bracket::before { content: "["; color: var(--ink-faint); }
  .bracket::after { content: "]"; color: var(--ink-faint); }
  h1, h2, h3 { text-wrap: balance; font-weight: 400; margin: 0; }
  button { font-family: inherit; font-size: inherit; color: inherit; background: var(--surface);
    border: 1px solid var(--line-strong); padding: 6px 12px; cursor: pointer; }
  button:hover { background: var(--surface-2); }
  :focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
  .wrap { max-width: 1180px; margin: 0 auto; }
  .masthead { display: flex; align-items: baseline; justify-content: space-between; gap: 24px;
    padding: 28px 0 14px; border-bottom: 2px solid var(--ink); flex-wrap: wrap; }
  .masthead h1 { font-size: 28px; font-weight: 700; letter-spacing: -0.01em; }
  .masthead .subtitle { font-style: italic; color: var(--ink-muted); font-size: 12.5px; }
  .built { font-size: 10.5px; color: var(--ink-muted); white-space: nowrap; }
  .summary-strip { display: grid; grid-template-columns: repeat(4, 1fr); border-bottom: 1px solid var(--line); }
  .summary-strip .stat { padding: 14px 18px; border-right: 1px solid var(--line); }
  .summary-strip .stat:last-child { border-right: none; }
  .summary-strip .k { font-size: 10.5px; letter-spacing: 0.09em; text-transform: uppercase; color: var(--ink-faint); }
  .summary-strip .v { font-size: 22px; margin-top: 3px; }
  .summary-strip .v.flagged { color: var(--accent); }
  .summary-strip .v.ok { color: var(--ok); }
  .tabs { display: flex; gap: 2px; padding: 18px 0 0; }
  .tab { background: none; border: 1px solid var(--line-strong); border-bottom: none; padding: 7px 14px;
    font-size: 12.5px; color: var(--ink-muted); position: relative; top: 1px; }
  .tab::before { content: "["; color: var(--ink-faint); margin-right: 1px; }
  .tab::after { content: "]"; color: var(--ink-faint); margin-left: 1px; }
  .tab[aria-selected="true"] { background: var(--surface); color: var(--ink); border-bottom: 1px solid var(--surface); }
  .panel { display: none; border-top: 1px solid var(--ink); padding-top: 24px; }
  .panel.active { display: block; }
  .overview-grid { display: grid; grid-template-columns: 230px 1fr 340px; border: 1px solid var(--line); }
  .col { padding: 18px; }
  .col + .col { border-left: 1px solid var(--line); }
  .col-title { font-size: 10.5px; letter-spacing: 0.09em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 12px; }
  .system-list { list-style: none; margin: 0; padding: 0; }
  .system-row { width: 100%; text-align: left; background: none; border: none; border-bottom: 1px solid var(--line);
    padding: 10px 2px; display: flex; flex-direction: column; gap: 4px; }
  .system-row:last-child { border-bottom: none; }
  .system-row:hover { background: var(--surface-2); }
  .system-row[aria-current="true"] { background: var(--surface-2); box-shadow: inset 3px 0 0 var(--ink); }
  .system-row .name { font-size: 14.5px; }
  .system-row .meta { display: flex; align-items: center; gap: 6px; font-size: 10.5px; color: var(--ink-muted); }
  .status-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; background: var(--ink-faint); }
  .status-dot.ok { background: var(--ok); } .status-dot.monitor { background: var(--warn); } .status-dot.flagged { background: var(--accent); }
  .status-tag { font-size: 10px; letter-spacing: 0.02em; padding: 2px 5px; border: 1px solid currentColor; }
  .status-tag.ok { color: var(--ok); background: var(--ok-soft); }
  .status-tag.monitor { color: var(--warn); background: var(--warn-soft); }
  .status-tag.flagged { color: var(--accent); background: var(--accent-soft); }
  .status-tag.unknown { color: var(--ink-faint); }
  .figure-wrap { display: flex; flex-direction: column; align-items: center; }
  .figure-caption { font-style: italic; color: var(--ink-muted); font-size: 12px; margin-top: 10px; text-align: center; }
  svg .body-line { fill: none; stroke: var(--ink-faint); stroke-width: 1.6; }
  svg .marker-hit { fill: transparent; cursor: pointer; }
  svg .marker.selected { stroke-width: 2.4; }
  svg .vitruvian { fill: none; stroke: var(--line-strong); stroke-width: 1; opacity: 0.6; }
  svg .body-line-echo { fill: none; stroke: var(--ink-faint); stroke-width: 1; stroke-dasharray: 3 3; opacity: 0.6; }
  svg .anatomy-layer { fill: none; stroke-width: 1.5; stroke-linecap: round; }
  svg .anatomy-layer.ok { color: var(--ok); } svg .anatomy-layer.monitor { color: var(--warn); }
  svg .anatomy-layer.flagged { color: var(--accent); } svg .anatomy-layer.unknown { color: var(--ink-faint); }
  svg .anatomy-layer .stroke { stroke: currentColor; fill: none; }
  svg .anatomy-layer .dot { stroke: currentColor; fill: var(--surface); }
  svg .anatomy-layer .organ { stroke: currentColor; fill: currentColor; fill-opacity: 0.14; }
  svg .anatomy-layer .bone { stroke: currentColor; fill: var(--surface); }
  svg .marker { fill: var(--surface); stroke: var(--ink); stroke-width: 1.6; cursor: pointer; }
  svg .marker-cross { stroke: var(--ink); stroke-width: 1.2; pointer-events: none; }
  svg .marker.ok, svg .marker-cross.ok { stroke: var(--ok); }
  svg .marker.monitor, svg .marker-cross.monitor { stroke: var(--warn); }
  svg .marker.flagged, svg .marker-cross.flagged { stroke: var(--accent); }
  svg .marker-label { font-size: 8px; fill: var(--ink-muted); }
  .detail-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 4px; }
  .detail-head h3 { font-size: 17px; }
  .detail-sub { font-size: 11.5px; color: var(--ink-muted); margin-bottom: 14px; }
  .trend { border: 1px solid var(--line); padding: 10px 10px 4px; margin-bottom: 14px; }
  .trend-label { font-size: 11px; color: var(--ink-muted); display: flex; justify-content: space-between; margin-bottom: 4px; }
  .trend svg text { fill: var(--ink-muted); font-size: 8.5px; }
  .trend .line { fill: none; stroke: var(--ink); stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
  .trend .grid { stroke: var(--line); stroke-width: 1; }
  .trend .dot { fill: var(--surface); stroke: var(--ink); stroke-width: 2; }
  .trend .dot.flagged { stroke: var(--accent); }
  .trend .range-band { fill: var(--ok-soft); }
  .metric-table { width: 100%; border-collapse: collapse; font-size: 12.5px; margin-bottom: 14px; }
  .metric-table th { text-align: left; font-weight: 400; font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--ink-faint); border-bottom: 1px solid var(--line-strong); padding: 3px 4px 6px; }
  .metric-table td { padding: 6px 4px; border-bottom: 1px solid var(--line); vertical-align: baseline; }
  .metric-table tr.flagged td.value { color: var(--accent); }
  .metric-table tr.monitor td.value { color: var(--warn); }
  .metric-table tr.pick { cursor: pointer; }
  .metric-table tr.pick:hover td { background: var(--surface-2); }
  .metric-table tr.current td.name { text-decoration: underline; text-underline-offset: 3px; }
  .notes { font-size: 12.5px; line-height: 1.5; margin: 0 0 10px; }
  .quote { font-style: italic; font-size: 12px; color: var(--ink-muted); border-left: 2px solid var(--line-strong); padding-left: 10px; margin: 0 0 16px; }
  table.full { width: 100%; border-collapse: collapse; font-size: 13px; }
  table.full th { text-align: left; font-weight: 400; font-size: 10.5px; letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--ink-faint); border-bottom: 2px solid var(--ink); padding: 6px 10px; }
  table.full td { padding: 8px 10px; border-bottom: 1px solid var(--line); }
  table.full tr.flagged td.value { color: var(--accent); }
  table.full tr.monitor td.value { color: var(--warn); }
  .table-scroll { overflow-x: auto; }
  .timeline { list-style: none; margin: 0; padding: 0; }
  .timeline li { display: grid; grid-template-columns: 110px 150px 1fr 110px 1fr 70px; gap: 10px; align-items: baseline;
    padding: 8px 4px; border-bottom: 1px solid var(--line); font-size: 13px; }
  .timeline li.head { font-size: 10.5px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-faint); border-bottom: 2px solid var(--ink); }
  .timeline .value.flagged { color: var(--accent); } .timeline .value.monitor { color: var(--warn); }
  .timeline .note { color: var(--ink-muted); font-size: 12px; }
  .foot-note { margin-top: 26px; font-size: 11.5px; color: var(--ink-muted); }
  .empty { padding: 40px 18px; color: var(--ink-muted); font-style: italic; }
  @media (max-width: 860px) {
    .overview-grid { grid-template-columns: 1fr; }
    .col + .col { border-left: none; border-top: 1px solid var(--line); }
    .summary-strip { grid-template-columns: repeat(2, 1fr); }
    .timeline li { grid-template-columns: 90px 1fr 90px; }
    .timeline li .sys, .timeline li .note, .timeline li .st { display: none; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <div>
      <h1>Corpus</h1>
      <span class="subtitle"># registro pessoal por sistemas</span>
    </div>
    <span class="built" id="built"></span>
  </header>
  <div class="summary-strip">
    <div class="stat"><div class="k">Sistemas</div><div class="v mono" id="statSystems">—</div></div>
    <div class="stat"><div class="k">Fora da referência</div><div class="v mono flagged" id="statFlags">—</div></div>
    <div class="stat"><div class="k">Perto do limite</div><div class="v mono" id="statMonitor">—</div></div>
    <div class="stat"><div class="k">Dentro</div><div class="v mono ok" id="statOk">—</div></div>
  </div>
  <nav class="tabs" role="tablist">
    <button class="tab" role="tab" aria-selected="true" data-panel="overview">visão geral</button>
    <button class="tab" role="tab" aria-selected="false" data-panel="full">painel completo</button>
    <button class="tab" role="tab" aria-selected="false" data-panel="timeline">linha do tempo</button>
  </nav>
  <section class="panel active" id="panel-overview">
    <div class="overview-grid" id="overviewGrid">
      <div class="col">
        <div class="col-title">Sistemas</div>
        <ul class="system-list" id="systemList"></ul>
      </div>
      <div class="col figure-wrap">
        <div class="col-title" style="align-self:flex-start;">Mapa</div>
        <svg viewBox="-140 -20 480 500" width="240" role="img" aria-label="Figura inscrita em círculo e quadrado, à maneira vitruviana, com uma lâmina anatômica por sistema">
          <rect class="vitruvian" x="-100" y="28" width="400" height="400" />
          <circle class="vitruvian" cx="100" cy="228" r="235" />
          <path class="body-line-echo" d="M60,92 C10,72 -30,55 -51,48" />
          <path class="body-line-echo" d="M140,92 C190,72 230,55 251,48" />
          <path class="body-line-echo" d="M76,262 C10,330 -30,375 -51,408" />
          <path class="body-line-echo" d="M124,262 C190,330 230,375 251,408" />
          <path class="body-line" d="M100,64 L100,84" />
          <path class="body-line" d="M60,92 C50,140 55,205 66,262 L134,262 C145,205 150,140 140,92 C128,80 72,80 60,92 Z" />
          <path class="body-line" d="M60,93 C10,90 -50,92 -90,97" />
          <path class="body-line" d="M140,93 C190,90 250,92 290,97" />
          <path class="body-line" d="M74,262 C68,320 64,385 58,444" />
          <path class="body-line" d="M126,262 C132,320 136,385 142,444" />
          <circle class="body-line" cx="100" cy="38" r="26" />
          <g id="anatomyLayer"></g>
          <g id="markers"></g>
        </svg>
        <p class="figure-caption">Segundo o cânone de proporções de Leonardo; a pose de membros abertos, mais tênue, é a segunda exposição. Escolha um sistema para trocar a lâmina.</p>
      </div>
      <div class="col" id="detailCol"></div>
    </div>
  </section>
  <section class="panel" id="panel-full">
    <div class="table-scroll"><table class="full">
      <thead><tr><th>Sistema</th><th>Medida</th><th>Última</th><th>Referência</th><th>Data</th><th>Estado</th></tr></thead>
      <tbody id="fullTableBody"></tbody>
    </table></div>
  </section>
  <section class="panel" id="panel-timeline">
    <ul class="timeline" id="timelineList"></ul>
  </section>
  <div class="foot-note" id="foot"></div>
</div>
<script>
(function () {
  "use strict";
  var DATA = /*__DATA__*/null;
  var data = DATA || { systems: [], built: "", summary: "" };
  var selectedSystemId = null, selectedMetricId = null;

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function fmtDate(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
    if (!m) return iso || "";
    var meses = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
    return m[3] + " " + meses[+m[2] - 1] + " " + m[1];
  }
  function fmtNum(v) { if (Math.abs(v - Math.round(v)) < 0.001) return String(Math.round(v)); return String(Math.round(v * 100) / 100); }
  function rangeText(m) {
    if (m.low == null && m.high == null) return "—";
    return (m.low == null ? "…" : fmtNum(m.low)) + "–" + (m.high == null ? "…" : fmtNum(m.high)) + (m.unit ? " " + m.unit : "");
  }
  function valueStatus(m, v) {
    if (v == null || (m.low == null && m.high == null)) return "unknown";
    if ((m.low != null && v < m.low) || (m.high != null && v > m.high)) return "flagged";
    if (m.low != null && m.high != null) {
      var span = m.high - m.low;
      if (v < m.low + span * 0.08 || v > m.high - span * 0.08) return "monitor";
    }
    return "ok";
  }
  function metricStatus(m) {
    if (!m.history.length) return "unknown";
    if (m.low == null && m.high == null) return "unknown";
    return valueStatus(m, m.history[m.history.length - 1][1]);
  }
  function systemStatus(sys) {
    var worst = "unknown";
    sys.metrics.forEach(function (m) {
      var s = metricStatus(m);
      if (s === "flagged") worst = "flagged";
      else if (s === "monitor" && worst !== "flagged") worst = "monitor";
      else if (s === "ok" && worst === "unknown") worst = "ok";
    });
    return worst;
  }
  function lastDateOf(sys) {
    var latest = null;
    sys.metrics.forEach(function (m) { m.history.forEach(function (h) { if (!latest || h[0] > latest) latest = h[0]; }); });
    return latest;
  }
  function allEntries() {
    var out = [];
    data.systems.forEach(function (sys) { sys.metrics.forEach(function (m) { m.history.forEach(function (h) {
      out.push({ system: sys, metric: m, date: h[0], value: h[1], shown: h[2], note: h[3] }); }); }); });
    out.sort(function (a, b) { return a.date < b.date ? 1 : -1; });
    return out;
  }
  var STATUS_PT = { ok: "dentro", monitor: "perto do limite", flagged: "fora", unknown: "sem referência" };

  function renderSummary() {
    document.getElementById("built").textContent = "espelho de _kustos.json · " + esc(data.built);
    document.getElementById("statSystems").textContent = data.systems.length;
    var f = 0, mo = 0, ok = 0;
    data.systems.forEach(function (s) { s.metrics.forEach(function (m) {
      var st = metricStatus(m); if (st === "flagged") f++; else if (st === "monitor") mo++; else if (st === "ok") ok++; }); });
    document.getElementById("statFlags").textContent = f;
    document.getElementById("statMonitor").textContent = mo;
    document.getElementById("statOk").textContent = ok;
    document.getElementById("foot").textContent = data.summary + " — refeito pelo _kustos.py; edite na janela, não aqui.";
  }

  function renderSystemList() {
    var list = document.getElementById("systemList");
    list.innerHTML = "";
    if (!data.systems.length) { list.innerHTML = '<li class="empty">Nenhuma medida ainda. Use “+ medida” na janela.</li>'; return; }
    data.systems.forEach(function (sys) {
      var st = systemStatus(sys);
      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.className = "system-row";
      btn.setAttribute("aria-current", sys.id === selectedSystemId ? "true" : "false");
      btn.innerHTML = '<span class="name">' + esc(sys.name) + '</span>' +
        '<span class="meta"><span class="status-dot ' + st + '"></span>' + STATUS_PT[st] + ' · ' + sys.metrics.length + ' medida' + (sys.metrics.length === 1 ? '' : 's') + '</span>';
      btn.addEventListener("click", function () { selectSystem(sys.id); });
      li.appendChild(btn);
      list.appendChild(li);
    });
  }

  function renderMarkers() {
    var g = document.getElementById("markers");
    g.innerHTML = "";
    var ns = "http://www.w3.org/2000/svg";
    var unplaced = 0;
    data.systems.forEach(function (sys) {
      var x, y;
      if (sys.marker) { x = sys.marker[0]; y = sys.marker[1]; }
      else { x = -60; y = 440 + unplaced * 16; unplaced++; }
      var st = systemStatus(sys);
      var isSel = sys.id === selectedSystemId;
      var half = isSel ? 6 : 4.5, tick = 3.5;
      var hit = document.createElementNS(ns, "circle");
      hit.setAttribute("class", "marker-hit"); hit.setAttribute("cx", x); hit.setAttribute("cy", y); hit.setAttribute("r", 14);
      hit.addEventListener("click", function () { selectSystem(sys.id); });
      g.appendChild(hit);
      var wrap = document.createElementNS(ns, "g");
      wrap.style.pointerEvents = "none";
      var sq = document.createElementNS(ns, "rect");
      sq.setAttribute("class", "marker " + st + (isSel ? " selected" : ""));
      sq.setAttribute("x", x - half); sq.setAttribute("y", y - half); sq.setAttribute("width", half * 2); sq.setAttribute("height", half * 2);
      wrap.appendChild(sq);
      [[x - half - tick, y, x - half, y], [x + half, y, x + half + tick, y], [x, y - half - tick, x, y - half], [x, y + half, x, y + half + tick]].forEach(function (c) {
        var ln = document.createElementNS(ns, "line");
        ln.setAttribute("class", "marker-cross " + st);
        ln.setAttribute("x1", c[0]); ln.setAttribute("y1", c[1]); ln.setAttribute("x2", c[2]); ln.setAttribute("y2", c[3]);
        wrap.appendChild(ln);
      });
      if (!sys.marker) {
        var t = document.createElementNS(ns, "text");
        t.setAttribute("class", "marker-label"); t.setAttribute("x", x + 12); t.setAttribute("y", y + 3);
        t.textContent = sys.name; wrap.appendChild(t);
      }
      g.appendChild(wrap);
    });
  }

  var ANATOMY_LAYERS = {
    neuro: function () {
      var vertebrae = [90, 120, 150, 180, 210, 240];
      return '<path class="stroke" d="M82,30 Q100,20 118,30"></path><path class="stroke" d="M80,44 Q100,54 120,44"></path>' +
        '<line class="stroke" x1="100" y1="64" x2="100" y2="258"></line>' +
        vertebrae.map(function (y) { return '<circle class="dot" cx="100" cy="' + y + '" r="2"></circle>'; }).join("") +
        '<path class="stroke" d="M100,100 L66,96"></path><path class="stroke" d="M100,100 L134,96"></path>' +
        '<path class="stroke" d="M100,230 L78,258"></path><path class="stroke" d="M100,230 L122,258"></path>';
    },
    cardio: function () {
      return '<path class="organ" d="M100,100 C92,88 74,90 74,107 C74,123 88,133 100,145 C112,133 126,123 126,107 C126,90 108,88 100,100 Z"></path>' +
        '<path class="stroke" d="M100,98 C100,84 112,74 128,78"></path><path class="stroke" d="M100,98 C100,84 88,74 72,78"></path>' +
        '<path class="stroke" d="M128,78 C138,86 138,112 130,144"></path>' +
        '<path class="stroke" d="M128,78 L118,62"></path><path class="stroke" d="M128,78 L144,92"></path>' +
        '<path class="stroke" d="M72,78 L82,62"></path><path class="stroke" d="M72,78 L56,92"></path>';
    },
    metabolic: function () {
      return '<circle class="dot" cx="100" cy="40" r="2"></circle>' +
        '<line class="stroke" x1="100" y1="46" x2="100" y2="167" stroke-dasharray="1 4"></line>' +
        '<ellipse class="organ" cx="91" cy="76" rx="6" ry="4"></ellipse><ellipse class="organ" cx="109" cy="76" rx="6" ry="4"></ellipse>' +
        '<path class="organ" d="M82,168 C95,159 116,159 127,170 C118,178 89,178 82,168 Z"></path>' +
        '<path class="organ" d="M67,196 C64,190 70,186 76,190 C76,196 72,200 67,196 Z"></path>' +
        '<path class="organ" d="M133,196 C136,190 130,186 124,190 C124,196 128,200 133,196 Z"></path>';
    },
    renal: function () {
      return '<path class="organ" d="M104,154 C122,146 143,153 143,171 C143,185 126,191 107,186 C99,180 97,163 104,154 Z"></path>' +
        '<path class="organ" d="M66,196 C60,203 60,218 68,226 C77,222 78,206 72,197 C70,195 68,195 66,196 Z"></path>' +
        '<path class="organ" d="M134,196 C140,203 140,218 132,226 C123,222 122,206 128,197 C130,195 132,195 134,196 Z"></path>' +
        '<path class="stroke" d="M69,222 C78,236 88,246 96,251"></path><path class="stroke" d="M131,222 C122,236 112,246 104,251"></path>' +
        '<ellipse class="organ" cx="100" cy="255" rx="9" ry="7"></ellipse>';
    },
    hema: function () {
      var pts = [[72, 95], [50, 108], [92, 258], [108, 258]];
      var chain = pts.map(function (p, i) { if (i === 0) return ""; var a = pts[i - 1];
        return '<line class="stroke" x1="' + a[0] + '" y1="' + a[1] + '" x2="' + p[0] + '" y2="' + p[1] + '" stroke-dasharray="1 3"></line>'; }).join("");
      return '<ellipse class="organ" cx="100" cy="90" rx="11" ry="6"></ellipse>' +
        '<ellipse class="organ" cx="74" cy="160" rx="7" ry="12" transform="rotate(-12 74 160)"></ellipse>' + chain +
        pts.map(function (p) { return '<circle class="dot" cx="' + p[0] + '" cy="' + p[1] + '" r="3"></circle>'; }).join("");
    },
    musculo: function () {
      var bones = [[60, 92, -15, 93], [-15, 93, -90, 96], [140, 92, 215, 93], [215, 93, 290, 96],
        [76, 262, 66, 352], [66, 352, 58, 440], [124, 262, 132, 352], [132, 352, 142, 440]];
      var joints = [[60, 92], [-15, 93], [-90, 96], [140, 92], [215, 93], [290, 96], [76, 262], [66, 352], [58, 440], [124, 262], [132, 352], [142, 440]];
      var ribs = [["M100,95 C112,96 122,104 124,116", "M100,95 C88,96 78,104 76,116"],
        ["M100,104 C114,105 126,114 128,128", "M100,104 C86,105 74,114 72,128"],
        ["M100,113 C116,114 130,124 130,140", "M100,113 C84,114 70,124 70,140"]];
      return '<path class="stroke" d="M84,54 Q100,64 116,54"></path><line class="stroke" x1="100" y1="64" x2="100" y2="258"></line>' +
        [90, 120, 150, 180, 210, 240].map(function (y) { return '<circle class="dot" cx="100" cy="' + y + '" r="2"></circle>'; }).join("") +
        ribs.map(function (p) { return '<path class="stroke" d="' + p[0] + '"></path><path class="stroke" d="' + p[1] + '"></path>'; }).join("") +
        '<line class="stroke" x1="100" y1="92" x2="100" y2="140"></line>' +
        '<path class="bone" d="M70,254 C64,240 76,226 100,228 C124,226 136,240 130,254 C122,248 108,246 100,248 C92,246 78,248 70,254 Z"></path>' +
        bones.map(function (b) { return '<line class="stroke" x1="' + b[0] + '" y1="' + b[1] + '" x2="' + b[2] + '" y2="' + b[3] + '"></line>'; }).join("") +
        joints.map(function (j) { return '<circle class="dot" cx="' + j[0] + '" cy="' + j[1] + '" r="2.5"></circle>'; }).join("");
    }
  };

  function renderAnatomyLayer() {
    var g = document.getElementById("anatomyLayer");
    var sys = data.systems.filter(function (s) { return s.id === selectedSystemId; })[0];
    if (!sys || !sys.plate || !ANATOMY_LAYERS[sys.plate]) { g.setAttribute("class", "anatomy-layer"); g.innerHTML = ""; return; }
    g.setAttribute("class", "anatomy-layer " + systemStatus(sys));
    g.innerHTML = ANATOMY_LAYERS[sys.plate]();
  }

  function buildTrendSvg(m) {
    var w = 280, h = 84, padL = 30, padR = 10, padT = 10, padB = 16;
    var hist = m.history;
    if (!hist.length) return "<p style='font-size:11px;color:var(--ink-muted)'>Sem leituras.</p>";
    var values = hist.map(function (x) { return x[1]; });
    var lo = m.low != null ? m.low : Math.min.apply(null, values);
    var hi = m.high != null ? m.high : Math.max.apply(null, values);
    var vMin = Math.min(lo, Math.min.apply(null, values)), vMax = Math.max(hi, Math.max.apply(null, values));
    if (vMin === vMax) { vMin -= 1; vMax += 1; }
    var span = vMax - vMin;
    function x(i) { return padL + (i / Math.max(1, hist.length - 1)) * (w - padL - padR); }
    function y(v) { return padT + (1 - (v - vMin) / span) * (h - padT - padB); }
    var band = (m.low != null || m.high != null) ?
      '<rect x="' + padL + '" y="' + y(hi) + '" width="' + (w - padL - padR) + '" height="' + Math.max(0, y(lo) - y(hi)) + '" class="range-band"></rect>' : "";
    var pts = hist.map(function (hh, i) { return x(i) + "," + y(hh[1]); }).join(" ");
    var dots = hist.map(function (hh, i) { return '<circle class="dot' + (valueStatus(m, hh[1]) === "flagged" ? ' flagged' : '') + '" cx="' + x(i) + '" cy="' + y(hh[1]) + '" r="3"><title>' + esc(fmtDate(hh[0]) + ' · ' + hh[2] + (hh[3] ? ' · ' + hh[3] : '')) + '</title></circle>'; }).join("");
    var lx = x(hist.length - 1), ly = Math.max(padT + 8, y(hist[hist.length - 1][1]));
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" width="100%" height="' + h + '" role="img">' + band +
      '<line class="grid" x1="' + padL + '" y1="' + (h - padB) + '" x2="' + (w - padR) + '" y2="' + (h - padB) + '"></line>' +
      '<polyline class="line" points="' + pts + '"></polyline>' + dots +
      '<text x="' + lx + '" y="' + (ly - 8) + '" text-anchor="end">' + esc(hist[hist.length - 1][2]) + '</text>' +
      '<text x="' + padL + '" y="' + (h - 4) + '">' + fmtDate(hist[0][0]) + '</text>' +
      '<text x="' + (w - padR) + '" y="' + (h - 4) + '" text-anchor="end">' + fmtDate(hist[hist.length - 1][0]) + '</text></svg>';
  }

  function renderDetail() {
    var col = document.getElementById("detailCol");
    var sys = data.systems.filter(function (s) { return s.id === selectedSystemId; })[0];
    if (!sys) { col.innerHTML = '<div class="col-title">Registro</div><p class="notes">Escolha um sistema para ver as leituras e a tendência.</p>'; return; }
    var st = systemStatus(sys);
    var primary = sys.metrics.filter(function (m) { return m.id === selectedMetricId; })[0] || sys.metrics[0];
    var rows = sys.metrics.map(function (m) {
      var last = m.history.length ? m.history[m.history.length - 1] : null;
      var mst = last ? metricStatus(m) : "unknown";
      return '<tr class="pick ' + mst + (m === primary ? ' current' : '') + '" data-m="' + esc(m.id) + '"><td class="name">' + esc(m.label) + '</td>' +
        '<td class="value">' + (last ? esc(last[2]) + " " + esc(m.unit) : "—") + '</td><td>' + esc(rangeText(m)) + '</td></tr>';
    }).join("");
    col.innerHTML = '<div class="col-title">Registro</div>' +
      '<div class="detail-head"><h3>' + esc(sys.name) + '</h3><span class="status-tag bracket ' + st + '">' + STATUS_PT[st] + '</span></div>' +
      '<div class="detail-sub">' + sys.metrics.length + ' medida' + (sys.metrics.length === 1 ? "" : "s") + ' — última leitura ' + (lastDateOf(sys) ? fmtDate(lastDateOf(sys)) : "nenhuma") + '</div>' +
      '<div class="trend"><div class="trend-label"><span>' + esc(primary.label) + '</span><span>' + esc(primary.unit) + '</span></div>' + buildTrendSvg(primary) + '</div>' +
      '<table class="metric-table"><thead><tr><th>Medida</th><th>Última</th><th>Referência</th></tr></thead><tbody>' + rows + '</tbody></table>' +
      (primary.notes ? '<p class="notes">' + esc(primary.notes) + '</p>' : '') +
      (primary.source ? '<p class="quote">fonte: ' + esc(primary.source) + '</p>' : '') +
      '<p class="notes" style="color:var(--ink-muted)">' + esc(primary.id) + '</p>';
    col.querySelectorAll("tr.pick").forEach(function (tr) {
      tr.addEventListener("click", function () { selectedMetricId = tr.dataset.m; renderDetail(); });
    });
  }

  function renderFullTable() {
    var rows = [];
    data.systems.forEach(function (sys) { sys.metrics.forEach(function (m) {
      var last = m.history.length ? m.history[m.history.length - 1] : null;
      var st = last ? metricStatus(m) : "unknown";
      rows.push('<tr class="' + st + '"><td>' + esc(sys.name) + '</td><td>' + esc(m.label) + '</td>' +
        '<td class="mono value">' + (last ? esc(last[2]) + " " + esc(m.unit) : "—") + '</td>' +
        '<td class="mono">' + esc(rangeText(m)) + '</td><td class="mono">' + (last ? fmtDate(last[0]) : "—") + '</td>' +
        '<td><span class="status-tag bracket ' + st + '">' + STATUS_PT[st] + '</span></td></tr>');
    }); });
    document.getElementById("fullTableBody").innerHTML = rows.join("") || '<tr><td colspan="6" class="empty">Nenhuma medida.</td></tr>';
  }

  function renderTimeline() {
    var rows = allEntries().map(function (e) {
      var st = valueStatus(e.metric, e.value);
      return '<li><span class="mono">' + fmtDate(e.date) + '</span><span class="sys">' + esc(e.system.name) + '</span><span>' + esc(e.metric.label) + '</span>' +
        '<span class="mono value ' + st + '">' + esc(e.shown) + ' ' + esc(e.metric.unit) + '</span><span class="note">' + esc(e.note) + '</span><span class="st">' + STATUS_PT[st] + '</span></li>';
    });
    document.getElementById("timelineList").innerHTML =
      '<li class="head"><span>Data</span><span class="sys">Sistema</span><span>Medida</span><span>Valor</span><span class="note">Obs.</span><span class="st">Estado</span></li>' + rows.join("");
  }

  function selectSystem(id) { selectedSystemId = id; selectedMetricId = null; renderSystemList(); renderMarkers(); renderAnatomyLayer(); renderDetail(); }
  function renderAll() { renderSummary(); renderSystemList(); renderMarkers(); renderAnatomyLayer(); renderDetail(); renderFullTable(); renderTimeline(); }
  document.querySelectorAll(".tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".tab").forEach(function (t) { t.setAttribute("aria-selected", "false"); });
      tab.setAttribute("aria-selected", "true");
      document.querySelectorAll(".panel").forEach(function (p) { p.classList.remove("active"); });
      document.getElementById("panel-" + tab.dataset.panel).classList.add("active");
    });
  });
  if (data.systems.length) selectedSystemId = data.systems[0].id;
  renderAll();
})();
</script>
</body>
</html>
"""


# ================================================================ temas

THEMES = {
    "paper": dict(dark=False, label="Paper", mono_only=False,
                  card="#f7f6f2", shell="#e8e6df", rule="#cdc7b8",
                  ink="#1b1a17", soft="#66635c", faint="#757167",
                  stamp="#1f4e5f", oxide="#9c3f2b",
                  selbg="#efece4", selfg="#1b1a17", caret=2),
    "green": dict(dark=True, label="Green phosphor", mono_only=True,
                  card="#0c120c", shell="#070b07", rule="#27512f",
                  ink="#33ff66", soft="#1fa347", faint="#1b8e3f",
                  stamp="#9dffc4", oxide="#c9ffdd",
                  selbg="#33ff66", selfg="#070b07", caret=8),
    "amber": dict(dark=True, label="Amber phosphor", mono_only=True,
                  card="#14100a", shell="#0e0b06", rule="#5e4206",
                  ink="#ffb000", soft="#b97f05", faint="#a67205",
                  stamp="#ffd48a", oxide="#ffe9c0",
                  selbg="#ffb000", selfg="#14100a", caret=8),
    "vt": dict(dark=True, label="Monochrome VT", mono_only=True,
               card="#101215", shell="#0a0c0e", rule="#3a424b",
               ink="#d6dee6", soft="#8c98a4", faint="#707e8b",
               stamp="#ffffff", oxide="#9fd0ff",
               selbg="#d6dee6", selfg="#0a0c0e", caret=8),
}
PAL = dict(THEMES["paper"])
PAPER = SHELL = RULE = INK = SOFT = FAINT = STAMP = OXIDE = SELBG = SELFG = ""
CARET = 2
tk = tkfont = ttk = None


def load_palette(name):
    global PAL, PAPER, SHELL, RULE, INK, SOFT, FAINT, STAMP, OXIDE
    global SELBG, SELFG, CARET
    PAL = dict(THEMES.get(name, THEMES["paper"]))
    PAPER, SHELL, RULE = PAL["card"], PAL["shell"], PAL["rule"]
    INK, SOFT, FAINT = PAL["ink"], PAL["soft"], PAL["faint"]
    STAMP, OXIDE = PAL["stamp"], PAL["oxide"]
    SELBG, SELFG, CARET = PAL["selbg"], PAL["selfg"], PAL["caret"]


def paint_frame(win):
    """No Windows a barra de título é do sistema; pede ao DWM para combinar
    com o tema. Silencioso em qualquer outra plataforma."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        dwm = ctypes.windll.dwmapi

        def send(attr, value):
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), 4)

        def colorref(hexcolor):
            r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
            return ctypes.c_int((b << 16) | (g << 8) | r)

        dark = ctypes.c_int(1 if PAL["dark"] else 0)
        for attr in (20, 19):
            send(attr, dark)
        send(35, colorref(PAL["shell"]))
        send(36, colorref(PAL["ink"]))
        send(34, colorref(PAL["rule"]))
    except Exception:
        pass


# ================================================================ cartões

class PersonCard:
    """O cartão de pessoa: campos, tarefas, log, círculos."""

    def __init__(self, app, parent):
        self.app = app
        self.frame = tk.Frame(parent, bg=PAPER)
        self.build()

    def build(self):
        app, shell = self.app, self.frame
        pad = dict(padx=22)
        foot = tk.Frame(shell, bg=PAPER)
        foot.pack(fill="x", side="bottom", pady=12, **pad)
        ttk.Button(foot, text="Salvar", command=app.save).pack(side="left")
        ttk.Button(foot, text="Salvar e nova", style="Quiet.TButton",
                   command=app.save_and_new).pack(side="left", padx=(8, 0))
        self.msg = tk.Label(foot, text="", bg=PAPER, fg=OXIDE, font=app.f_meta)
        self.msg.pack(side="left", padx=14)
        ttk.Button(foot, text="Apagar", style="Quiet.TButton",
                   command=app.delete).pack(side="right")
        tk.Frame(shell, bg=RULE, height=1).pack(fill="x", side="bottom")

        c = app.scroll_area(shell)
        head = tk.Frame(c, bg=PAPER)
        head.pack(fill="x", pady=(11, 0), **pad)
        self.e_name = tk.Entry(head, width=1, font=app.f_name, bg=PAPER, fg=INK,
                               relief="flat", insertbackground=INK, insertwidth=2,
                               highlightthickness=0, disabledbackground=PAPER,
                               disabledforeground=FAINT)
        self.e_name.pack(side="left", fill="x", expand=True)
        self.stamp = tk.Label(head, text="", bg=PAPER, fg=FAINT, font=app.f_meta,
                              justify="right")
        self.stamp.pack(side="right")
        tk.Frame(c, bg=STAMP, height=2).pack(fill="x", pady=(6, 0), **pad)

        self.e_tags = app.field(c, "TAGS", app.f_meta, pad)
        self.t_notes = app.textfield(c, "NOTAS", 3, app.f_body, pad)
        self.e_place = app.field(c, "DOMICILIUM", app.f_body, pad)
        self.e_source = app.source_field(c, pad)
        self.circles = self.circle_panel(c, pad)
        self.t_alias = app.textfield(c, "TAMBÉM CONHECIDO COMO", 2, app.f_meta, pad)
        self.t_links = app.textfield(c, "LINKS", 2, app.f_meta, pad)
        self.t_tasks = app.textfield(c, "TAREFAS", 3, app.f_meta, pad)
        self.t_tasks.bind("<space>", self.space_cycle)
        self.t_tasks.bind("<Control-space>", self.cycle_task_state)
        self.t_tasks.bind("<Return>", self.new_task_line)

        app.label(c, "CITADO POR  (duplo clique abre)", pad)
        self.inbox = tk.Listbox(c, height=2, width=1, font=app.f_meta,
                                bg=PAPER, fg=INK, relief="flat",
                                highlightthickness=0, selectbackground=SELBG,
                                selectforeground=SELFG, activestyle="none")
        self.inbox.pack(fill="x", **pad)
        self.inbox.bind("<Double-Button-1>", self.jump_in)
        tk.Frame(c, bg=RULE, height=1).pack(fill="x", pady=(4, 0), **pad)
        self.in_ids = []

        tk.Label(c, text="LOG", bg=PAPER, fg=FAINT, font=app.f_label,
                 anchor="w").pack(fill="x", pady=(6, 2), **pad)
        self.t_log = tk.Text(c, height=2, width=1, font=app.f_meta,
                             bg=PAPER, fg=INK, relief="flat", wrap="word",
                             insertbackground=INK, highlightthickness=0,
                             padx=0, spacing1=1, spacing3=3,
                             undo=True, autoseparators=True, maxundo=-1)
        app.block_caret(self.t_log, app.f_meta)
        app.bind_undo(self.t_log, text=True)
        self.t_log.pack(fill="x", **pad)
        app.autogrow(self.t_log, minrows=2)
        addrow = tk.Frame(c, bg=PAPER)
        addrow.pack(fill="x", pady=(3, 14), **pad)
        self.e_log = tk.Entry(addrow, width=1, font=app.f_body, bg=PAPER, fg=INK,
                              relief="flat", highlightthickness=1,
                              highlightbackground=RULE, highlightcolor=STAMP,
                              disabledbackground=PAPER, disabledforeground=FAINT)
        self.e_log.pack(side="left", fill="x", expand=True, ipady=2)
        self.e_log.bind("<Return>", lambda e: self.add_log())
        ttk.Button(addrow, text="+ log", command=self.add_log
                   ).pack(side="left", padx=(8, 0))

        for w in (self.e_name, self.e_tags, self.e_place, self.e_log):
            app.bind_undo(w)
        for w in (self.e_name, self.e_tags, self.e_place, self.e_source, self.t_notes,
                  self.t_links, self.t_alias, self.t_tasks, self.t_log):
            for ev in ("<KeyRelease>", "<<Paste>>", "<<Cut>>"):
                w.bind(ev, app.mark_dirty, add="+")

    def circle_panel(self, parent, pad, height=172):
        """Os quatro círculos de Covey, encaixados, clicáveis."""
        app = self.app
        tk.Label(parent, text="CÍRCULOS", bg=PAPER, fg=FAINT,
                 font=app.f_label, anchor="w").pack(fill="x", pady=(6, 2), **pad)
        cv = tk.Canvas(parent, height=height, bg=PAPER, highlightthickness=0, bd=0)
        cv.pack(fill="x", **pad)
        state = {"on": set(), "hot": None, "enabled": True}
        FRACTIONS = (1.0, 0.76, 0.52, 0.28)

        def geometry():
            big = (height - 14) / 2.0
            cx, base = big + 4, height - 7
            rings, rows = [], []
            for name, f in zip(CIRCLES, FRACTIONS):
                r = big * f
                rings.append((name, cx, base - r, r))
                rows.append((name, base - 2 * r + 9))
            return rings, rows

        def label_x():
            return (height - 14) + 24

        def draw(_e=None):
            if not cv.winfo_exists():
                return
            cv.delete("all")
            rings, rows = geometry()
            for name, cx, cy, r in rings:
                chosen = name in state["on"]
                hot = (state["hot"] == name and state["enabled"])
                cv.create_oval(cx - r, cy - r, cx + r, cy + r,
                               fill=RULE if chosen else PAPER,
                               outline=INK if (chosen or hot) else SOFT,
                               width=2 if (chosen or hot) else 1)
            lx = label_x()
            for name, ly in rows:
                chosen = name in state["on"]
                hot = (state["hot"] == name and state["enabled"])
                cv.create_text(lx, ly, anchor="w",
                               text=("[x] " if chosen else "[ ] ") + name,
                               font=app.f_meta,
                               fill=INK if (chosen or hot) else FAINT)

        def hit(x, y):
            rings, rows = geometry()
            if x >= label_x() - 8:
                for name, ly in rows:
                    if abs(y - ly) <= 10:
                        return name
                return None
            for name, cx, cy, r in reversed(rings):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    return name
            return None

        def clicked(e):
            if not state["enabled"]:
                return
            name = hit(e.x, e.y)
            if not name:
                return
            state["on"].symmetric_difference_update({name})
            draw()
            app.mark_dirty()
            self.msg.configure(text=", ".join(parse_circles(state["on"]))
                               or "nenhum círculo")

        def moved(e):
            if not state["enabled"]:
                return
            name = hit(e.x, e.y)
            if name != state["hot"]:
                state["hot"] = name
                cv.configure(cursor="hand2" if name else "")
                draw()

        def left(_e=None):
            if state["hot"] is not None:
                state["hot"] = None
                cv.configure(cursor="")
                draw()

        cv.bind("<Configure>", draw)
        cv.bind("<Button-1>", clicked)
        cv.bind("<Motion>", moved)
        cv.bind("<Leave>", left)
        cv.get_circles = lambda: parse_circles(state["on"])

        def set_value(value):
            state["on"] = set(parse_circles(value))
            draw()

        def enable(flag):
            state["enabled"] = flag
            if not flag:
                state["hot"] = None
            draw()

        cv.set_circles, cv.enable_circles = set_value, enable
        return cv

    # ---- tarefas
    def cycle_task_state(self, _event=None):
        t = self.t_tasks
        line = t.index("insert").split(".")[0]
        body = t.get(f"{line}.0", f"{line}.end")
        if not body.strip():
            return "break"
        m = TASK_RE.match(body)
        if m:
            current = TASK_MARK.get(m.group(1).lower(), "todo")
            rest = body[m.end(1) + 1:].lstrip()
            nxt = TASK_CYCLE[(TASK_CYCLE.index(current) + 1) % len(TASK_CYCLE)] \
                if current in TASK_CYCLE else "todo"
        else:
            rest, nxt = body.strip(), "doing"
        t.delete(f"{line}.0", f"{line}.end")
        t.insert(f"{line}.0", f"[{MARK_OF[nxt]}] {rest}")
        t.mark_set("insert", f"{line}.1")
        self.app.mark_dirty()
        self.msg.configure(text=nxt + (" — vai para o log ao salvar"
                                       if nxt == "done" else ""))
        return "break"

    def space_cycle(self, event):
        col = int(self.t_tasks.index("insert").split(".")[1])
        line = self.t_tasks.index("insert").split(".")[0]
        body = self.t_tasks.get(f"{line}.0", f"{line}.end")
        if col <= 3 and TASK_RE.match(body):
            return self.cycle_task_state(event)
        return None

    def new_task_line(self, _event=None):
        self.t_tasks.insert("insert", "\n[ ] ")
        self.app.mark_dirty()
        return "break"

    # ---- estado
    def enable(self, on):
        state = "normal" if on else "disabled"
        for w in (self.e_name, self.e_tags, self.e_place, self.e_log, self.e_source):
            w.configure(state=state)
        for w in (self.t_notes, self.t_links, self.t_alias, self.t_tasks,
                  self.t_log):
            w.configure(state=state)
        self.circles.enable_circles(on)

    def clear(self):
        for w in (self.e_name, self.e_tags, self.e_place, self.e_source):
            w.delete(0, "end")
        self.app.update_source_hint(self.e_source)
        for t in (self.t_notes, self.t_alias, self.t_links, self.t_tasks,
                  self.t_log):
            t.delete("1.0", "end")
        self.inbox.delete(0, "end")
        self.circles.set_circles([])
        self.stamp.configure(text="")
        self.msg.configure(text="")

    def open(self, p):
        self.enable(True)
        self.e_name.delete(0, "end")
        self.e_name.insert(0, p["name"])
        self.e_tags.delete(0, "end")
        self.e_tags.insert(0, ", ".join(p.get("tags", [])))
        self.t_notes.delete("1.0", "end")
        self.t_notes.insert("1.0", p.get("notes_raw", ""))
        self.e_place.delete(0, "end")
        self.e_place.insert(0, p.get("place", ""))
        self.e_source.delete(0, "end")
        self.e_source.insert(0, p.get("source", ""))
        self.app.update_source_hint(self.e_source)
        self.t_alias.delete("1.0", "end")
        self.t_alias.insert("1.0", format_aliases(p.get("aliases", [])))
        self.t_links.delete("1.0", "end")
        self.t_links.insert("1.0", "\n".join(p.get("links", [])))
        self.t_tasks.delete("1.0", "end")
        self.t_tasks.insert("1.0", format_tasks(p.get("tasks", [])))
        self.circles.set_circles(p.get("circles", []))
        self.t_log.delete("1.0", "end")
        self.t_log.insert("1.0", format_log(p.get("interactions", [])))
        self.refresh_citing(p)
        bits = [p["id"] if not p["id"].startswith("__") else "rascunho"]
        if p.get("met"):
            bits.append("met " + p["met"])
        if p.get("updated"):
            bits.append("edit " + p["updated"])
        self.stamp.configure(text="\n".join(bits))
        self.msg.configure(text="")

    def refresh_citing(self, p):
        data, idx = self.app.data, by_id(self.app.data)
        self.inbox.delete(0, "end")
        self.in_ids = []
        for a in edges_to(data, p["id"]):
            src = idx.get(a["from"])
            self.inbox.insert("end", f"{label_any(src, data):28} {rel_label(a['rel'])}")
            self.in_ids.append(a["from"])
        self.inbox.configure(height=max(2, min(8, self.inbox.size())))

    def jump_in(self, _e=None):
        sel = self.inbox.curselection()
        if sel and sel[0] < len(self.in_ids):
            self.app.goto(self.in_ids[sel[0]])

    def gather(self, p):
        out = dict(p)
        out.update({
            "name": self.e_name.get().strip(),
            "tags": [t.strip() for t in self.e_tags.get().split(",") if t.strip()],
            "notes_raw": self.t_notes.get("1.0", "end-1c"),
            "links": [l.strip() for l in
                      self.t_links.get("1.0", "end-1c").split("\n") if l.strip()],
            "place": self.e_place.get().strip(),
            "source": self.e_source.get().strip(),
            "aliases": parse_aliases(self.t_alias.get("1.0", "end-1c")),
            "interactions": parse_log(self.t_log.get("1.0", "end-1c")),
            "tasks": parse_tasks(self.t_tasks.get("1.0", "end-1c")),
            "circles": self.circles.get_circles(),
            "followup": None,
            "met": p.get("met"),
        })
        return out

    def add_log(self):
        text = self.e_log.get().strip()
        if not self.app.current() or not text:
            return
        existing = self.t_log.get("1.0", "end-1c").rstrip()
        line = f"{TODAY()}   {text}"
        self.t_log.delete("1.0", "end")
        self.t_log.insert("1.0", (existing + "\n" + line) if existing else line)
        self.e_log.delete(0, "end")
        self.app.mark_dirty()
        self.app.refit_card()
        self.app.save()


class EntryCard:
    """O cartão de verbete: glosa, linha de forma, domínios, ligações."""

    def __init__(self, app, parent):
        self.app = app
        self.frame = tk.Frame(parent, bg=PAPER)
        self.layout = parse_layout((app.data.get("ui") or {}).get("card_fields"))
        self.out_ids, self.in_ids = [], []
        self.build()

    def build(self):
        app, shell = self.app, self.frame
        pad = dict(padx=22)
        foot = tk.Frame(shell, bg=PAPER)
        foot.pack(fill="x", side="bottom", pady=12, **pad)
        ttk.Button(foot, text="Salvar", command=app.save).pack(side="left")
        self.msg = tk.Label(foot, text="", bg=PAPER, fg=OXIDE, font=app.f_meta)
        self.msg.pack(side="left", padx=14)
        ttk.Button(foot, text="Apagar", style="Quiet.TButton",
                   command=app.delete).pack(side="right")
        tk.Frame(shell, bg=RULE, height=1).pack(fill="x", side="bottom")

        c = app.scroll_area(shell)
        head = tk.Frame(c, bg=PAPER)
        head.pack(fill="x", pady=(11, 0), **pad)
        self.e_name = tk.Entry(head, width=1, font=app.f_name, bg=PAPER, fg=INK,
                               relief="flat", insertbackground=INK, insertwidth=2,
                               highlightthickness=0, disabledbackground=PAPER,
                               disabledforeground=FAINT)
        self.e_name.pack(side="left", fill="x", expand=True)
        self.stamp = tk.Label(head, text="", bg=PAPER, fg=FAINT, font=app.f_meta,
                              justify="right")
        self.stamp.pack(side="right")
        tk.Frame(c, bg=STAMP, height=2).pack(fill="x", pady=(6, 0), **pad)

        # Cada campo vive no seu quadro; apply_layout empacota na ordem
        # guardada, o que permite reordenar e ocultar sem refazer a janela.
        self.blocks = {}

        def block(fid):
            f = tk.Frame(c, bg=PAPER)
            self.blocks[fid] = f
            return f

        self.t_gloss = app.textfield(block("gloss"), "GLOSA", 2, app.f_body, pad)

        self.form_row = block("form_row")
        for title, width, attr in (("LÍNGUA", 8, "e_lang"),
                                   ("ROMANIZAÇÃO", 16, "e_roman"),
                                   ("ATESTADA", 12, "e_attested")):
            col = tk.Frame(self.form_row, bg=PAPER)
            col.pack(side="left", fill="x", expand=True)
            tk.Label(col, text=title, bg=PAPER, fg=FAINT, font=app.f_label,
                     anchor="w").pack(fill="x", pady=(8, 2))
            ent = tk.Entry(col, width=width, font=app.f_meta, bg=PAPER, fg=INK,
                           insertbackground=INK, relief="flat",
                           highlightthickness=0, disabledbackground=PAPER,
                           disabledforeground=FAINT)
            ent.pack(anchor="w")
            app.bind_undo(ent)
            setattr(self, attr, ent)
        statf = tk.Frame(self.form_row, bg=PAPER)
        statf.pack(side="left", fill="x", expand=True)
        tk.Label(statf, text="STATUS", bg=PAPER, fg=FAINT, font=app.f_label,
                 anchor="w").pack(fill="x", pady=(8, 2))
        self.v_status = tk.StringVar(value="attested")
        self.e_status = ttk.Combobox(statf, textvariable=self.v_status,
                                     values=["attested", "reconstructed"],
                                     state="readonly", width=14, font=app.f_meta)
        self.e_status.pack(anchor="w")
        self.e_status.bind("<<ComboboxSelected>>", app.mark_dirty)

        self.e_domains = app.field(block("domains"), "DOMÍNIOS", app.f_meta, pad)
        self.e_tags = app.field(block("tags"), "TAGS", app.f_meta, pad)
        self.e_source = app.source_field(block("source"), pad)
        self.t_notes = app.textfield(block("notes"), "NOTAS", 3, app.f_body, pad)

        b = block("edges")
        app.label(b, "LIGAÇÕES", pad)
        tk.Label(b, text="rel  alvo  [intervalo]  — razão  # fonte     "
                         "(alvo pode ser p_… de uma pessoa)",
                 bg=PAPER, fg=FAINT, font=app.f_label, anchor="w"
                 ).pack(fill="x", pady=(0, 3), **pad)
        self.t_edges = tk.Text(b, height=3, width=1, font=app.f_meta,
                               bg=PAPER, fg=INK, insertbackground=INK,
                               relief="flat", wrap="word", highlightthickness=0,
                               padx=0, spacing1=1, spacing3=3, undo=True,
                               autoseparators=True, maxundo=-1)
        app.block_caret(self.t_edges, app.f_meta)
        app.bind_undo(self.t_edges, text=True)
        self.t_edges.pack(fill="x", **pad)
        app.autogrow(self.t_edges, minrows=3)
        tk.Frame(b, bg=RULE, height=1).pack(fill="x", pady=(4, 0), **pad)

        b = block("out")
        app.label(b, "LIGAÇÕES RESOLVIDAS  (duplo clique abre)", pad)
        self.outbox = self._listbox(b, pad)
        self.outbox.bind("<Double-Button-1>", self.jump_out)
        b = block("inb")
        app.label(b, "CITADO POR  (duplo clique abre)", pad)
        self.inbox = self._listbox(b, pad)
        self.inbox.bind("<Double-Button-1>", self.jump_in)

        self.t_links = app.textfield(block("links"), "LINKS", 2, app.f_meta, pad)
        self.tail = tk.Frame(c, bg=PAPER, height=12)

        for w in (self.e_name, self.e_lang, self.e_roman, self.e_attested,
                  self.e_domains, self.e_tags, self.e_source):
            for ev in ("<KeyRelease>", "<<Paste>>", "<<Cut>>"):
                w.bind(ev, app.mark_dirty, add="+")
        app.bind_undo(self.e_name)
        for w in (self.t_gloss, self.t_notes, self.t_edges, self.t_links):
            for ev in ("<KeyRelease>", "<<Paste>>", "<<Cut>>"):
                w.bind(ev, app.mark_dirty, add="+")
        self.kind = "concept"
        self.apply_layout()

    def _listbox(self, parent, pad):
        lb = tk.Listbox(parent, height=3, width=1, font=self.app.f_meta,
                        bg=PAPER, fg=INK, relief="flat", highlightthickness=0,
                        selectbackground=SELBG, selectforeground=SELFG,
                        activestyle="none")
        lb.pack(fill="x", **pad)
        tk.Frame(parent, bg=RULE, height=1).pack(fill="x", pady=(4, 0), **pad)
        return lb

    def apply_layout(self):
        for f in self.blocks.values():
            f.pack_forget()
        self.tail.pack_forget()
        for fid, on in self.layout:
            if not on or fid not in self.blocks:
                continue
            if fid == "form_row" and self.kind == "concept":
                continue
            self.blocks[fid].pack(fill="x", padx=22 if fid == "form_row" else 0)
        self.tail.pack(fill="x")

    def enable(self, on):
        state = "normal" if on else "disabled"
        for w in (self.e_name, self.e_lang, self.e_roman, self.e_attested,
                  self.e_domains, self.e_tags, self.e_source):
            w.configure(state=state)
        for t in (self.t_gloss, self.t_notes, self.t_links, self.t_edges):
            t.configure(state=state)
        self.e_status.configure(state="readonly" if on else "disabled")

    def clear(self):
        for w in (self.e_name, self.e_lang, self.e_roman, self.e_attested,
                  self.e_domains, self.e_tags, self.e_source):
            w.delete(0, "end")
        for t in (self.t_gloss, self.t_notes, self.t_links, self.t_edges):
            t.delete("1.0", "end")
        self.outbox.delete(0, "end")
        self.inbox.delete(0, "end")
        self.stamp.configure(text="")
        self.msg.configure(text="")
        self.app.update_source_hint(self.e_source)

    def open(self, e):
        self.enable(True)
        self.kind = e.get("kind", "concept")
        self.e_name.delete(0, "end")
        self.e_name.insert(0, e.get("name", ""))
        self.t_gloss.delete("1.0", "end")
        self.t_gloss.insert("1.0", e.get("gloss", ""))
        self.e_lang.delete(0, "end")
        self.e_lang.insert(0, e.get("lang", ""))
        self.e_roman.delete(0, "end")
        self.e_roman.insert(0, e.get("roman", ""))
        self.e_attested.delete(0, "end")
        self.e_attested.insert(0, e.get("attested", ""))
        self.v_status.set(e.get("status", "attested"))
        self.e_domains.delete(0, "end")
        self.e_domains.insert(0, ", ".join(e.get("domains", [])))
        self.e_tags.delete(0, "end")
        self.e_tags.insert(0, ", ".join(e.get("tags", [])))
        self.e_source.delete(0, "end")
        self.e_source.insert(0, e.get("source", ""))
        self.app.update_source_hint(self.e_source)
        self.t_notes.delete("1.0", "end")
        self.t_notes.insert("1.0", e.get("notes", ""))
        self.t_links.delete("1.0", "end")
        self.t_links.insert("1.0", "\n".join(e.get("links", [])))
        self.t_edges.delete("1.0", "end")
        texto = format_edges(edges_from(self.app.data, e["id"]))
        if e.get("edge_drafts"):
            texto = "\n".join(filter(None, [texto] + e["edge_drafts"]))
        self.t_edges.insert("1.0", texto)
        rid = e["id"] if not e["id"].startswith("__") else "rascunho"
        self.stamp.configure(text=f"{rid}\n{self.kind}  {e.get('updated', '')}")
        self.msg.configure(text="")
        self.apply_layout()
        self.refresh_neighbours(e["id"])

    def refresh_neighbours(self, eid):
        data, idx = self.app.data, by_id(self.app.data)
        self.outbox.delete(0, "end")
        self.out_ids = []
        for a in sorted(edges_from(data, eid), key=lambda x: year_of(x.get("when"))):
            alvo = idx.get(a["to"])
            shown = label_any(alvo, data) if alvo else f"{a['to']}  (alvo inexistente)"
            when = f"  {a['when']}" if a.get("when") else ""
            self.outbox.insert("end", f"{rel_label(a['rel']):16} {shown}{when}")
            self.out_ids.append(a["to"])
        self.inbox.delete(0, "end")
        self.in_ids = []
        for a in sorted(edges_to(data, eid), key=lambda x: year_of(x.get("when"))):
            src = idx.get(a["from"])
            when = f"  {a['when']}" if a.get("when") else ""
            self.inbox.insert("end", f"{label_any(src, data):28} "
                                     f"{rel_label(a['rel'])}{when}")
            self.in_ids.append(a["from"])
        self.outbox.configure(height=max(3, min(10, self.outbox.size())))
        self.inbox.configure(height=max(3, min(10, self.inbox.size())))

    def jump_out(self, _e=None):
        sel = self.outbox.curselection()
        if sel and sel[0] < len(self.out_ids):
            self.app.goto(self.out_ids[sel[0]])

    def jump_in(self, _e=None):
        sel = self.inbox.curselection()
        if sel and sel[0] < len(self.in_ids):
            self.app.goto(self.in_ids[sel[0]])

    def gather(self, e):
        kind = e.get("kind", "concept")
        out = {k: v for k, v in e.items() if not k.startswith("_")}
        out.update({
            "kind": kind,
            "name": self.e_name.get().strip(),
            "gloss": self.t_gloss.get("1.0", "end-1c").strip(),
            "tags": [t.strip() for t in self.e_tags.get().split(",") if t.strip()],
            "notes": self.t_notes.get("1.0", "end-1c").strip(),
            "source": self.e_source.get().strip(),
            "links": [l.strip() for l in
                      self.t_links.get("1.0", "end-1c").splitlines() if l.strip()],
            "domains": [d.strip() for d in self.e_domains.get().split(",")
                        if d.strip()],
        })
        if kind == "form":
            out.update({"lang": self.e_lang.get().strip(),
                        "roman": self.e_roman.get().strip(),
                        "attested": self.e_attested.get().strip(),
                        "status": self.v_status.get()})
        return out

    def edges_text(self):
        return self.t_edges.get("1.0", "end-1c")


# ================================================================ mapa do corpo (Tk)
#
# O mesmo Vitruviano e as mesmas lâminas do espelho HTML, desenhados no
# Canvas do Tk: monocromáticos, no tom do tema, sem preenchimento além de um
# tramado leve. Os caminhos SVG são convertidos em polilinhas por um
# interpretador mínimo (M, L, C, Q, Z, absolutos), que é tudo que as lâminas
# usam.

# (id da lâmina, título) -> lista de primitivas ("path", d) | ("circle", cx, cy, r)
#   | ("ellipse", cx, cy, rx, ry, ângulo) | ("line", x1, y1, x2, y2, dash) | ("organ", d)
PLATES = {
    "neuro": [
        ("path", "M82,30 Q100,20 118,30"), ("path", "M80,44 Q100,54 120,44"),
        ("line", 100, 64, 100, 258, None),
    ] + [("circle", 100, y, 2) for y in (90, 120, 150, 180, 210, 240)] + [
        ("path", "M100,100 L66,96"), ("path", "M100,100 L134,96"),
        ("path", "M100,230 L78,258"), ("path", "M100,230 L122,258"),
    ],
    "cardio": [
        ("organ", "M100,100 C92,88 74,90 74,107 C74,123 88,133 100,145 C112,133 126,123 "
                  "126,107 C126,90 108,88 100,100 Z"),
        ("path", "M100,98 C100,84 112,74 128,78"), ("path", "M100,98 C100,84 88,74 72,78"),
        ("path", "M128,78 C138,86 138,112 130,144"),
        ("path", "M128,78 L118,62"), ("path", "M128,78 L144,92"),
        ("path", "M72,78 L82,62"), ("path", "M72,78 L56,92"),
    ],
    "metabolic": [
        ("circle", 100, 40, 2), ("line", 100, 46, 100, 167, (1, 4)),
        ("ellipse", 91, 76, 6, 4, 0), ("ellipse", 109, 76, 6, 4, 0),
        ("organ", "M82,168 C95,159 116,159 127,170 C118,178 89,178 82,168 Z"),
        ("organ", "M67,196 C64,190 70,186 76,190 C76,196 72,200 67,196 Z"),
        ("organ", "M133,196 C136,190 130,186 124,190 C124,196 128,200 133,196 Z"),
    ],
    "renal": [
        ("organ", "M104,154 C122,146 143,153 143,171 C143,185 126,191 107,186 C99,180 97,163 104,154 Z"),
        ("organ", "M66,196 C60,203 60,218 68,226 C77,222 78,206 72,197 C70,195 68,195 66,196 Z"),
        ("organ", "M134,196 C140,203 140,218 132,226 C123,222 122,206 128,197 C130,195 132,195 134,196 Z"),
        ("path", "M69,222 C78,236 88,246 96,251"), ("path", "M131,222 C122,236 112,246 104,251"),
        ("ellipse", 100, 255, 9, 7, 0),
    ],
    "hema": [
        ("ellipse", 100, 90, 11, 6, 0), ("ellipse", 74, 160, 7, 12, -12),
        ("line", 72, 95, 50, 108, (1, 3)), ("line", 50, 108, 92, 258, (1, 3)),
        ("line", 92, 258, 108, 258, (1, 3)),
    ] + [("circle", x, y, 3) for x, y in ((72, 95), (50, 108), (92, 258), (108, 258))],
    "musculo": [
        ("path", "M84,54 Q100,64 116,54"), ("line", 100, 64, 100, 258, None),
    ] + [("circle", 100, y, 2) for y in (90, 120, 150, 180, 210, 240)] + [
        ("path", "M100,95 C112,96 122,104 124,116"), ("path", "M100,95 C88,96 78,104 76,116"),
        ("path", "M100,104 C114,105 126,114 128,128"), ("path", "M100,104 C86,105 74,114 72,128"),
        ("path", "M100,113 C116,114 130,124 130,140"), ("path", "M100,113 C84,114 70,124 70,140"),
        ("line", 100, 92, 100, 140, None),
        ("organ", "M70,254 C64,240 76,226 100,228 C124,226 136,240 130,254 C122,248 108,246 "
                  "100,248 C92,246 78,248 70,254 Z"),
    ] + [("line", a, b, c, d, None) for a, b, c, d in
         ((60, 92, -15, 93), (-15, 93, -90, 96), (140, 92, 215, 93), (215, 93, 290, 96),
          (76, 262, 66, 352), (66, 352, 58, 440), (124, 262, 132, 352), (132, 352, 142, 440))]
      + [("circle", x, y, 2.5) for x, y in
         ((60, 92), (-15, 93), (-90, 96), (140, 92), (215, 93), (290, 96), (76, 262),
          (66, 352), (58, 440), (124, 262), (132, 352), (142, 440))],
}
# a figura de base: o quadrado e o círculo, a pose aberta em tracejado, o
# corpo em traço cheio
FIGURE = [
    ("rect", -100, 28, 400, 400), ("circle", 100, 228, 235),
    ("echo", "M60,92 C10,72 -30,55 -51,48"), ("echo", "M140,92 C190,72 230,55 251,48"),
    ("echo", "M76,262 C10,330 -30,375 -51,408"), ("echo", "M124,262 C190,330 230,375 251,408"),
    ("body", "M100,64 L100,84"),
    ("body", "M60,92 C50,140 55,205 66,262 L134,262 C145,205 150,140 140,92 C128,80 72,80 60,92 Z"),
    ("body", "M60,93 C10,90 -50,92 -90,97"), ("body", "M140,93 C190,90 250,92 290,97"),
    ("body", "M74,262 C68,320 64,385 58,444"), ("body", "M126,262 C132,320 136,385 142,444"),
    ("bodycircle", 100, 38, 26),
]
VIEWBOX = (-140, -20, 480, 500)


def svg_path_points(d, steps=10):
    """Caminho SVG (M/L/C/Q/Z absolutos) -> lista de polilinhas [(x,y),...]."""
    tokens = re.findall(r"[MLCQZ]|-?\d*\.?\d+", d)
    polys, cur, pos, start = [], [], (0.0, 0.0), (0.0, 0.0)
    i = 0

    def nums(n):
        nonlocal i
        vals = [float(tokens[i + k]) for k in range(n)]
        i += n
        return vals

    while i < len(tokens):
        t = tokens[i]
        i += 1
        if t == "M":
            if len(cur) > 1:
                polys.append(cur)
            x, y = nums(2)
            pos = start = (x, y)
            cur = [pos]
        elif t == "L":
            x, y = nums(2)
            pos = (x, y)
            cur.append(pos)
        elif t == "C":
            x1, y1, x2, y2, x, y = nums(6)
            x0, y0 = pos
            for k in range(1, steps + 1):
                u = k / steps
                cur.append((
                    (1 - u) ** 3 * x0 + 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u * u * x2 + u ** 3 * x,
                    (1 - u) ** 3 * y0 + 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u * u * y2 + u ** 3 * y))
            pos = (x, y)
        elif t == "Q":
            x1, y1, x, y = nums(4)
            x0, y0 = pos
            for k in range(1, steps + 1):
                u = k / steps
                cur.append(((1 - u) ** 2 * x0 + 2 * (1 - u) * u * x1 + u * u * x,
                            (1 - u) ** 2 * y0 + 2 * (1 - u) * u * y1 + u * u * y))
            pos = (x, y)
        elif t == "Z":
            cur.append(start)
            pos = start
    if len(cur) > 1:
        polys.append(cur)
    return polys


def ellipse_points(cx, cy, rx, ry, angle=0, n=24):
    import math
    a = math.radians(angle)
    out = []
    for k in range(n):
        t = 2 * math.pi * k / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
    return out


class BodyMap:
    """O Vitruviano no cartão de medida. Marcadores por sistema presente no
    corpus; clique filtra a lista por aquele sistema; a lâmina do sistema
    da medida aberta é desenhada por cima do contorno."""

    def __init__(self, app, parent, pad, height=360):
        self.app = app
        self.height = height
        self.scale = height / VIEWBOX[3]
        self.width = int(VIEWBOX[2] * self.scale)
        self.current = None          # sistema em destaque
        self.hot = None
        self.hits = []               # (x, y, sistema)
        self.toggle = tk.Label(parent, text="", bg=PAPER, fg=FAINT, font=app.f_label,
                               anchor="w", cursor="hand2")
        self.toggle.pack(fill="x", pady=(6, 0), **pad)
        self.toggle.bind("<Button-1>", lambda e: self.set_open(not self.open))
        self.wrap = tk.Frame(parent, bg=PAPER)
        self.pad = pad
        self.cv = tk.Canvas(self.wrap, height=height, width=self.width, bg=PAPER,
                            highlightthickness=0, bd=0)
        self.cv.pack(side="left")
        self.legend = tk.Frame(self.wrap, bg=PAPER)
        self.legend.pack(side="left", fill="both", expand=True, padx=(16, 0))
        self.open = bool((app.data.get("ui") or {}).get("map_open", True))
        self.set_open(self.open, save=False)
        self.cv.bind("<Button-1>", self.clicked)
        self.cv.bind("<Motion>", self.moved)
        self.cv.bind("<Leave>", lambda e: self.cv.configure(cursor=""))
        tk.Frame(parent, bg=RULE, height=1).pack(fill="x", pady=(6, 0), **pad)

    def set_open(self, on, save=True):
        self.open = on
        self.toggle.configure(text=("[−] mapa do corpo" if on else "[+] mapa do corpo"))
        if on:
            self.wrap.pack(fill="x", after=self.toggle, **self.pad)
            self.redraw()
        else:
            self.wrap.pack_forget()
        if save:
            self.app.data = save_ui({"map_open": on})

    # ---- geometria
    def P(self, x, y):
        return ((x - VIEWBOX[0]) * self.scale, (y - VIEWBOX[1]) * self.scale)

    def flat(self, pts):
        out = []
        for x, y in pts:
            out.extend(self.P(x, y))
        return out

    def draw_prims(self, prims, color, width=1.0, dash=None):
        cv = self.cv
        for prim in prims:
            kind = prim[0]
            if kind in ("path", "echo", "body"):
                for poly in svg_path_points(prim[1]):
                    cv.create_line(*self.flat(poly), fill=color, width=width, dash=dash,
                                   joinstyle="round", capstyle="round")
            elif kind == "organ":
                for poly in svg_path_points(prim[1]):
                    cv.create_polygon(*self.flat(poly), outline=color, fill=color,
                                      stipple="gray12", width=width)
            elif kind in ("circle", "bodycircle"):
                _, cx, cy, r = prim
                x0, y0 = self.P(cx - r, cy - r)
                x1, y1 = self.P(cx + r, cy + r)
                cv.create_oval(x0, y0, x1, y1, outline=color, width=width, fill=PAPER
                               if kind == "circle" and r <= 3 else "")
            elif kind == "ellipse":
                _, cx, cy, rx, ry, ang = prim
                cv.create_polygon(*self.flat(ellipse_points(cx, cy, rx, ry, ang)),
                                  outline=color, fill=color, stipple="gray12", width=width)
            elif kind == "line":
                _, x1, y1, x2, y2, d = prim
                cv.create_line(*self.P(x1, y1), *self.P(x2, y2), fill=color, width=width,
                               dash=d, capstyle="round")
            elif kind == "rect":
                _, x, y, w, h = prim
                cv.create_rectangle(*self.P(x, y), *self.P(x + w, y + h), outline=color,
                                    width=width)

    # ---- dados
    def systems(self):
        """{sistema: (n medidas, alguma fora da referência?)}"""
        out = {}
        for m in self.app.data.get("corpus", []):
            s = m.get("system") or "outro"
            n, bad = out.get(s, (0, False))
            lr = last_reading(m)
            out[s] = (n + 1, bad or bool(lr and out_of_range(m, lr)))
        return out

    def redraw(self):
        cv = self.cv
        if not cv.winfo_exists() or not self.open:
            return
        cv.delete("all")
        self.hits = []
        # a moldura em tom apagado, a pose aberta tracejada, o corpo em traço
        self.draw_prims([p for p in FIGURE if p[0] in ("rect", "circle")], RULE, 1.0)
        self.draw_prims([p for p in FIGURE if p[0] == "echo"], FAINT, 1.0, (3, 3))
        self.draw_prims([p for p in FIGURE if p[0] in ("body", "bodycircle")], SOFT, 1.4)
        systems = self.systems()
        # lâmina do sistema em destaque
        plate = PLATE_OF.get(self.current or "")
        if plate in PLATES:
            self.draw_prims(PLATES[plate], INK, 1.2)
        # marcadores: um quadrado por sistema presente, deslocado se a lâmina é
        # partilhada; cheio quando a última leitura está fora da referência
        used, unplaced = {}, 0
        for sname in sorted(systems, key=sort_key):
            n, bad = systems[sname]
            pl = PLATE_OF.get(sname)
            if pl in MARKER_OF:
                x, y = MARKER_OF[pl]
                k = used.get(pl, 0)
                used[pl] = k + 1
                x += 16 * k
            else:
                x, y = -110, 450 + unplaced * 16
                unplaced += 1
            px, py = self.P(x, y)
            half = 5 if sname == self.current else 3.5
            cv.create_rectangle(px - half, py - half, px + half, py + half,
                                outline=INK, width=1.6 if sname == self.current else 1.2,
                                fill=INK if bad else PAPER)
            for a, b, c, d in ((px - half - 3, py, px - half, py), (px + half, py, px + half + 3, py),
                               (px, py - half - 3, px, py - half), (px, py + half, px, py + half + 3)):
                cv.create_line(a, b, c, d, fill=INK)
            if pl not in MARKER_OF:
                cv.create_text(px + 10, py, text=sname, anchor="w", fill=FAINT,
                               font=self.app.f_label)
            self.hits.append((px, py, sname))
        # legenda
        ui = self.app.data.get("ui") or {}
        subject = ui.get("corpus_subject") or ""
        cv.create_text(6, 6, text=("corpus · " + subject) if subject else "corpus",
                       anchor="nw", fill=FAINT, font=self.app.f_label)
        for w in self.legend.winfo_children():
            w.destroy()
        tk.Label(self.legend, text="SISTEMAS", bg=PAPER, fg=FAINT, font=self.app.f_label,
                 anchor="w").pack(fill="x", pady=(2, 4))
        if not systems:
            tk.Label(self.legend, text="nenhuma medida ainda", bg=PAPER, fg=FAINT,
                     font=self.app.f_meta, anchor="w").pack(fill="x")
        for sname in sorted(systems, key=sort_key):
            n, bad = systems[sname]
            on = sname == self.current
            mark = "[x]" if on else "[ ]"
            row = tk.Label(self.legend, text=f"{mark} {sname}  {n}" + ("  (!)" if bad else ""),
                           bg=PAPER, fg=INK if on else SOFT, font=self.app.f_meta,
                           anchor="w", cursor="hand2")
            row.pack(fill="x")
            row.bind("<Button-1>", lambda e, s=sname: self.pick(s))
        tk.Label(self.legend, text="clique filtra a lista; (!) fora da referência",
                 bg=PAPER, fg=FAINT, font=self.app.f_label, anchor="w",
                 justify="left").pack(fill="x", pady=(8, 0))

    def hit(self, x, y):
        for px, py, s in self.hits:
            if abs(x - px) <= 9 and abs(y - py) <= 9:
                return s
        return None

    def moved(self, e):
        s = self.hit(e.x, e.y)
        if s != self.hot:
            self.hot = s
            self.cv.configure(cursor="hand2" if s else "")

    def clicked(self, e):
        s = self.hit(e.x, e.y)
        if s:
            self.pick(s)

    def pick(self, sname):
        self.app.filter_system(sname)

    def set_current(self, sname):
        self.current = sname
        self.redraw()


class SourceCard:
    """O cartão de fonte: os campos do tipo, a citação pronta para copiar."""

    def __init__(self, app, parent):
        self.app = app
        self.frame = tk.Frame(parent, bg=PAPER)
        self.stype = "outro"
        self.in_ids, self.out_ids, self.use_ids = [], [], []
        self.build()

    def build(self):
        app, shell = self.app, self.frame
        pad = dict(padx=22)
        foot = tk.Frame(shell, bg=PAPER)
        foot.pack(fill="x", side="bottom", pady=12, **pad)
        ttk.Button(foot, text="Salvar", command=app.save).pack(side="left")
        ttk.Button(foot, text="Salvar e nova", style="Quiet.TButton",
                   command=app.save_and_new).pack(side="left", padx=(8, 0))
        self.msg = tk.Label(foot, text="", bg=PAPER, fg=OXIDE, font=app.f_meta)
        self.msg.pack(side="left", padx=14)
        ttk.Button(foot, text="Apagar", style="Quiet.TButton",
                   command=app.delete).pack(side="right")
        tk.Frame(shell, bg=RULE, height=1).pack(fill="x", side="bottom")

        c = app.scroll_area(shell)
        head = tk.Frame(c, bg=PAPER)
        head.pack(fill="x", pady=(11, 0), **pad)
        self.e_name = tk.Entry(head, width=1, font=app.f_name, bg=PAPER, fg=INK,
                               relief="flat", insertbackground=INK, insertwidth=2,
                               highlightthickness=0, disabledbackground=PAPER,
                               disabledforeground=FAINT)
        self.e_name.pack(side="left", fill="x", expand=True)
        self.stamp = tk.Label(head, text="", bg=PAPER, fg=FAINT, font=app.f_meta,
                              justify="right")
        self.stamp.pack(side="right")
        tk.Frame(c, bg=STAMP, height=2).pack(fill="x", pady=(6, 0), **pad)

        # tipo: combobox editável -- a lista sugere, você decide
        trow = tk.Frame(c, bg=PAPER)
        trow.pack(fill="x", **pad)
        tcol = tk.Frame(trow, bg=PAPER)
        tcol.pack(side="left")
        tk.Label(tcol, text="TIPO", bg=PAPER, fg=FAINT, font=app.f_label,
                 anchor="w").pack(fill="x", pady=(8, 2))
        self.v_type = tk.StringVar(value="outro")
        self.e_type = ttk.Combobox(tcol, textvariable=self.v_type, values=SOURCE_TYPES,
                                   width=18, font=app.f_meta)
        self.e_type.pack(anchor="w")
        self.e_type.bind("<<ComboboxSelected>>", self.type_changed)
        self.e_type.bind("<KeyRelease>", self.type_changed)
        tk.Label(trow, text="  mudar o tipo só muda os campos visíveis; nada se perde",
                 bg=PAPER, fg=FAINT, font=app.f_label).pack(side="left", pady=(22, 0))

        self.blocks = {}
        self.widgets = {}

        def block(fid):
            f = tk.Frame(c, bg=PAPER)
            self.blocks[fid] = f
            return f

        self.widgets["authors"] = app.textfield(block("authors"), SOURCE_FIELD_PT["authors"],
                                                2, app.f_meta, pad)
        self.widgets["date"] = app.field(block("date"), SOURCE_FIELD_PT["date"], app.f_meta, pad)
        self.widgets["container"] = app.field(block("container"), SOURCE_FIELD_PT["container"],
                                              app.f_body, pad)
        self.widgets["publisher"] = app.field(block("publisher"), SOURCE_FIELD_PT["publisher"],
                                              app.f_meta, pad)
        self.widgets["place"] = app.field(block("place"), SOURCE_FIELD_PT["place"], app.f_meta, pad)
        # edição · volume · número · páginas numa linha só
        row = block("numbers")
        for fid in ("edition", "volume", "issue", "pages"):
            col = tk.Frame(row, bg=PAPER)
            col.pack(side="left", fill="x", expand=True, padx=(0, 10))
            tk.Label(col, text=SOURCE_FIELD_PT[fid], bg=PAPER, fg=FAINT, font=app.f_label,
                     anchor="w").pack(fill="x", pady=(8, 2))
            ent = tk.Entry(col, width=8, font=app.f_meta, bg=PAPER, fg=INK,
                           insertbackground=INK, relief="flat", highlightthickness=0,
                           disabledbackground=PAPER, disabledforeground=FAINT)
            ent.pack(fill="x")
            tk.Frame(col, bg=RULE, height=1).pack(fill="x", pady=(4, 0))
            app.bind_undo(ent)
            self.widgets[fid] = ent
        row2 = block("ids")
        for fid in ("doi", "isbn", "accessed", "lang"):
            col = tk.Frame(row2, bg=PAPER)
            col.pack(side="left", fill="x", expand=True, padx=(0, 10))
            tk.Label(col, text=SOURCE_FIELD_PT[fid], bg=PAPER, fg=FAINT, font=app.f_label,
                     anchor="w").pack(fill="x", pady=(8, 2))
            ent = tk.Entry(col, width=10, font=app.f_meta, bg=PAPER, fg=INK,
                           insertbackground=INK, relief="flat", highlightthickness=0,
                           disabledbackground=PAPER, disabledforeground=FAINT)
            ent.pack(fill="x")
            tk.Frame(col, bg=RULE, height=1).pack(fill="x", pady=(4, 0))
            app.bind_undo(ent)
            self.widgets[fid] = ent
        self.widgets["url"] = app.field(block("url"), SOURCE_FIELD_PT["url"], app.f_meta, pad)
        self.widgets["extra"] = app.textfield(block("extra"), SOURCE_FIELD_PT["extra"], 2,
                                              app.f_meta, pad)
        self.e_tags = app.field(block("tags"), "TAGS", app.f_meta, pad)
        self.t_notes = app.textfield(block("notes"), "NOTAS", 3, app.f_body, pad)

        b = block("cite")
        crow = tk.Frame(b, bg=PAPER)
        crow.pack(fill="x", pady=(6, 2), **pad)
        tk.Label(crow, text="CITAÇÃO", bg=PAPER, fg=FAINT, font=app.f_label,
                 anchor="w").pack(side="left")
        self.v_style = tk.StringVar(value=(app.data.get("ui") or {}).get("cite_style", "abnt"))
        sb = ttk.Combobox(crow, textvariable=self.v_style, values=list(CITE_STYLES),
                          state="readonly", width=15, font=app.f_meta)
        sb.pack(side="left", padx=(10, 0))
        sb.bind("<<ComboboxSelected>>", lambda e: self.refresh_cite())
        ttk.Button(crow, text="copiar", style="Quiet.TButton",
                   command=self.copy_cite).pack(side="left", padx=(8, 0))
        self.t_cite = tk.Text(b, height=3, width=1, font=app.f_meta, bg=SHELL, fg=INK,
                              relief="flat", wrap="word", highlightthickness=0,
                              padx=8, pady=6)
        self.t_cite.pack(fill="x", **pad)
        app.autogrow(self.t_cite, minrows=2)

        b = block("edges")
        app.label(b, "LIGAÇÕES  (rel  alvo  [intervalo]  — razão  # fonte)", pad)
        self.t_edges = tk.Text(b, height=2, width=1, font=app.f_meta, bg=PAPER, fg=INK,
                               insertbackground=INK, relief="flat", wrap="word",
                               highlightthickness=0, padx=0, spacing1=1, spacing3=3,
                               undo=True, autoseparators=True, maxundo=-1)
        app.block_caret(self.t_edges, app.f_meta)
        app.bind_undo(self.t_edges, text=True)
        self.t_edges.pack(fill="x", **pad)
        app.autogrow(self.t_edges, minrows=2)
        tk.Frame(b, bg=RULE, height=1).pack(fill="x", pady=(4, 0), **pad)

        b = block("out")
        app.label(b, "LIGAÇÕES RESOLVIDAS  (duplo clique abre)", pad)
        self.outbox = app.listbox(b, pad)
        self.outbox.bind("<Double-Button-1>", lambda e: app.jump(self.outbox, self.out_ids))
        b = block("inb")
        app.label(b, "CITADO POR  (duplo clique abre)", pad)
        self.inbox = app.listbox(b, pad)
        self.inbox.bind("<Double-Button-1>", lambda e: app.jump(self.inbox, self.in_ids))
        b = block("uses")
        app.label(b, "FONTE DE  (registros cujo campo FONTE aponta para cá; duplo clique abre)", pad)
        self.usebox = app.listbox(b, pad)
        self.usebox.bind("<Double-Button-1>", lambda e: app.jump(self.usebox, self.use_ids))
        self.t_links = app.textfield(block("links"), "LINKS", 2, app.f_meta, pad)
        self.tail = tk.Frame(c, bg=PAPER, height=12)

        self.entries = [self.e_name, self.e_tags] + [w for k, w in self.widgets.items()
                                                       if k not in ("authors", "extra")]
        self.texts = [self.widgets["authors"], self.widgets["extra"], self.t_notes,
                      self.t_edges, self.t_links]
        app.bind_undo(self.e_name)
        for w in self.entries + self.texts:
            for ev in ("<KeyRelease>", "<<Paste>>", "<<Cut>>"):
                w.bind(ev, app.mark_dirty, add="+")
                w.bind(ev, lambda e: self.app.root.after(300, self.refresh_cite), add="+")
        self.apply_layout()

    ORDER = ["authors", "date", "container", "publisher", "place", "numbers", "ids",
             "url", "extra", "tags", "notes", "cite", "edges", "out", "inb", "uses", "links"]

    def apply_layout(self):
        show = set(source_fields_for(self.stype))
        for f in self.blocks.values():
            f.pack_forget()
        self.tail.pack_forget()
        for fid in self.ORDER:
            if fid == "numbers" and not show & {"edition", "volume", "issue", "pages"}:
                continue
            if fid == "ids" and not show & {"doi", "isbn", "accessed", "lang"}:
                continue
            if fid in SOURCE_FIELD_PT and fid not in show:
                continue
            self.blocks[fid].pack(fill="x", padx=22 if fid in ("numbers", "ids") else 0)
        self.tail.pack(fill="x")

    def type_changed(self, _e=None):
        self.stype = self.v_type.get().strip().lower() or "outro"
        self.apply_layout()
        self.app.mark_dirty()
        self.refresh_cite()

    def enable(self, on):
        state = "normal" if on else "disabled"
        for w in self.entries + self.texts:
            w.configure(state=state)
        self.e_type.configure(state="normal" if on else "disabled")

    def clear(self):
        for w in self.entries:
            w.delete(0, "end")
        for t in self.texts:
            t.delete("1.0", "end")
        for lb in (self.outbox, self.inbox, self.usebox):
            lb.delete(0, "end")
        self.t_cite.configure(state="normal")
        self.t_cite.delete("1.0", "end")
        self.t_cite.configure(state="disabled")
        self.stamp.configure(text="")
        self.msg.configure(text="")

    def open(self, s):
        self.enable(True)
        self.stype = (s.get("type") or "outro").lower()
        self.v_type.set(s.get("type") or "outro")
        self.e_name.delete(0, "end")
        self.e_name.insert(0, s.get("name", ""))
        for k, w in self.widgets.items():
            if k in ("authors", "extra"):
                w.delete("1.0", "end")
                w.insert("1.0", "\n".join(s.get(k, [])))
            else:
                w.delete(0, "end")
                w.insert(0, s.get(k, ""))
        self.e_tags.delete(0, "end")
        self.e_tags.insert(0, ", ".join(s.get("tags", [])))
        self.t_notes.delete("1.0", "end")
        self.t_notes.insert("1.0", s.get("notes", ""))
        self.t_links.delete("1.0", "end")
        self.t_links.insert("1.0", "\n".join(s.get("links", [])))
        self.t_edges.delete("1.0", "end")
        texto = format_edges(edges_from(self.app.data, s["id"]))
        if s.get("edge_drafts"):
            texto = "\n".join(filter(None, [texto] + s["edge_drafts"]))
        self.t_edges.insert("1.0", texto)
        rid = s["id"] if not s["id"].startswith("__") else "rascunho"
        self.stamp.configure(text=f"{rid}\n{s.get('updated', '')}"
                             + ("\n[texto bruto guardado]" if s.get("raw") else ""))
        self.msg.configure(text="")
        self.apply_layout()
        self.refresh_neighbours(s["id"])
        self.refresh_cite()

    def refresh_neighbours(self, sid):
        app = self.app
        data, idx = app.data, by_id(app.data)
        self.outbox.delete(0, "end")
        self.out_ids = []
        for a in edges_from(data, sid):
            alvo = idx.get(a["to"])
            self.outbox.insert("end", f"{rel_label(a['rel']):18} "
                                      f"{label_any(alvo, data) if alvo else a['to'] + '  (inexistente)'}")
            self.out_ids.append(a["to"])
        self.inbox.delete(0, "end")
        self.in_ids = []
        for a in edges_to(data, sid):
            src = idx.get(a["from"])
            self.inbox.insert("end", f"{label_any(src, data):30} {rel_label(a['rel'])}")
            self.in_ids.append(a["from"])
        self.usebox.delete(0, "end")
        self.use_ids = []
        for coll in ("people", "entries", "corpus"):
            for r in data[coll]:
                if r.get("source") == sid:
                    self.usebox.insert("end", f"{COLL_PT[coll]:8} {label_any(r, data)}")
                    self.use_ids.append(r["id"])
        for lb in (self.outbox, self.inbox, self.usebox):
            lb.configure(height=max(2, min(10, lb.size())))

    def gather(self, s):
        out = {k: v for k, v in s.items() if not k.startswith("_")}
        out["type"] = self.v_type.get().strip().lower() or "outro"
        out["name"] = self.e_name.get().strip()
        for k, w in self.widgets.items():
            if k in ("authors", "extra"):
                out[k] = [l.strip() for l in w.get("1.0", "end-1c").splitlines() if l.strip()]
            else:
                out[k] = w.get().strip()
        out["tags"] = [t.strip() for t in self.e_tags.get().split(",") if t.strip()]
        out["notes"] = self.t_notes.get("1.0", "end-1c").strip()
        out["links"] = [l.strip() for l in self.t_links.get("1.0", "end-1c").splitlines()
                        if l.strip()]
        return out

    def edges_text(self):
        return self.t_edges.get("1.0", "end-1c")

    def refresh_cite(self):
        if self.app.shown != "source" or not self.app.sel:
            return
        try:
            s = self.gather(self.app.current() or {})
            text = cite(s, self.v_style.get(), self.app.data)
        except Exception as err:      # a citação nunca pode derrubar o cartão
            text = f"(não consegui montar a citação: {err})"
        self.t_cite.configure(state="normal")
        self.t_cite.delete("1.0", "end")
        self.t_cite.insert("1.0", text)
        self.t_cite.configure(state="disabled")

    def copy_cite(self):
        text = self.t_cite.get("1.0", "end-1c")
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(text)
        save_ui({"cite_style": self.v_style.get()})
        self.msg.configure(text="Citação copiada.")


class MetricCard:
    """O cartão de medida: unidade, referência, leituras ao longo do tempo."""

    def __init__(self, app, parent):
        self.app = app
        self.frame = tk.Frame(parent, bg=PAPER)
        self.in_ids, self.out_ids = [], []
        self.build()

    def build(self):
        app, shell = self.app, self.frame
        pad = dict(padx=22)
        foot = tk.Frame(shell, bg=PAPER)
        foot.pack(fill="x", side="bottom", pady=12, **pad)
        ttk.Button(foot, text="Salvar", command=app.save).pack(side="left")
        ttk.Button(foot, text="Salvar e nova", style="Quiet.TButton",
                   command=app.save_and_new).pack(side="left", padx=(8, 0))
        ttk.Button(foot, text="mapa do corpo", style="Quiet.TButton",
                   command=app.do_corpus).pack(side="left", padx=(8, 0))
        self.msg = tk.Label(foot, text="", bg=PAPER, fg=OXIDE, font=app.f_meta)
        self.msg.pack(side="left", padx=14)
        ttk.Button(foot, text="Apagar", style="Quiet.TButton",
                   command=app.delete).pack(side="right")
        tk.Frame(shell, bg=RULE, height=1).pack(fill="x", side="bottom")

        c = app.scroll_area(shell)
        head = tk.Frame(c, bg=PAPER)
        head.pack(fill="x", pady=(11, 0), **pad)
        self.e_name = tk.Entry(head, width=1, font=app.f_name, bg=PAPER, fg=INK,
                               relief="flat", insertbackground=INK, insertwidth=2,
                               highlightthickness=0, disabledbackground=PAPER,
                               disabledforeground=FAINT)
        self.e_name.pack(side="left", fill="x", expand=True)
        self.stamp = tk.Label(head, text="", bg=PAPER, fg=FAINT, font=app.f_meta,
                              justify="right")
        self.stamp.pack(side="right")
        tk.Frame(c, bg=STAMP, height=2).pack(fill="x", pady=(6, 0), **pad)

        self.map = BodyMap(app, c, pad)

        row = tk.Frame(c, bg=PAPER)
        row.pack(fill="x", **pad)
        scol = tk.Frame(row, bg=PAPER)
        scol.pack(side="left", padx=(0, 14))
        tk.Label(scol, text="SISTEMA", bg=PAPER, fg=FAINT, font=app.f_label,
                 anchor="w").pack(fill="x", pady=(8, 2))
        self.v_system = tk.StringVar()
        self.e_system = ttk.Combobox(scol, textvariable=self.v_system, values=SYSTEMS,
                                     width=20, font=app.f_meta)
        self.e_system.pack(anchor="w")
        self.e_system.bind("<<ComboboxSelected>>", app.mark_dirty)
        for title, attr in (("UNIDADE", "e_unit"), ("REF. MÍN.", "e_lo"),
                            ("REF. MÁX.", "e_hi")):
            col = tk.Frame(row, bg=PAPER)
            col.pack(side="left", fill="x", expand=True, padx=(0, 10))
            tk.Label(col, text=title, bg=PAPER, fg=FAINT, font=app.f_label,
                     anchor="w").pack(fill="x", pady=(8, 2))
            ent = tk.Entry(col, width=8, font=app.f_meta, bg=PAPER, fg=INK,
                           insertbackground=INK, relief="flat", highlightthickness=0,
                           disabledbackground=PAPER, disabledforeground=FAINT)
            ent.pack(fill="x")
            tk.Frame(col, bg=RULE, height=1).pack(fill="x", pady=(4, 0))
            app.bind_undo(ent)
            setattr(self, attr, ent)

        self.e_source = app.source_field(c, pad)
        self.e_tags = app.field(c, "TAGS", app.f_meta, pad)
        self.t_notes = app.textfield(c, "NOTAS", 2, app.f_body, pad)

        app.label(c, "LEITURAS  (uma por linha:  2026-09-01 [10:30]  valor  observação)", pad)
        self.t_read = app.textfield_bare(c, 3, pad)
        self.summary = tk.Label(c, text="", bg=PAPER, fg=SOFT, font=app.f_meta, anchor="w")
        self.summary.pack(fill="x", pady=(2, 0), **pad)
        self.trend = tk.Canvas(c, height=96, bg=PAPER, highlightthickness=0, bd=0)
        self.trend.pack(fill="x", pady=(6, 0), **pad)
        self.trend.bind("<Configure>", lambda e: self.draw_trend())
        addrow = tk.Frame(c, bg=PAPER)
        addrow.pack(fill="x", pady=(3, 10), **pad)
        self.e_new = tk.Entry(addrow, width=1, font=app.f_body, bg=PAPER, fg=INK,
                              relief="flat", highlightthickness=1,
                              highlightbackground=RULE, highlightcolor=STAMP,
                              disabledbackground=PAPER, disabledforeground=FAINT)
        self.e_new.pack(side="left", fill="x", expand=True, ipady=2)
        self.e_new.bind("<Return>", lambda e: self.add_reading())
        ttk.Button(addrow, text="+ leitura de hoje", command=self.add_reading
                   ).pack(side="left", padx=(8, 0))

        b = tk.Frame(c, bg=PAPER)
        b.pack(fill="x")
        app.label(b, "LIGAÇÕES  (rel  alvo  — razão)", pad)
        self.t_edges = tk.Text(b, height=2, width=1, font=app.f_meta, bg=PAPER, fg=INK,
                               insertbackground=INK, relief="flat", wrap="word",
                               highlightthickness=0, padx=0, spacing1=1, spacing3=3,
                               undo=True, autoseparators=True, maxundo=-1)
        app.block_caret(self.t_edges, app.f_meta)
        app.bind_undo(self.t_edges, text=True)
        self.t_edges.pack(fill="x", **pad)
        app.autogrow(self.t_edges, minrows=2)
        tk.Frame(b, bg=RULE, height=1).pack(fill="x", pady=(4, 0), **pad)
        app.label(c, "LIGAÇÕES RESOLVIDAS  (duplo clique abre)", pad)
        self.outbox = app.listbox(c, pad)
        self.outbox.bind("<Double-Button-1>", lambda e: app.jump(self.outbox, self.out_ids))
        app.label(c, "CITADO POR  (duplo clique abre)", pad)
        self.inbox = app.listbox(c, pad)
        self.inbox.bind("<Double-Button-1>", lambda e: app.jump(self.inbox, self.in_ids))
        self.t_links = app.textfield(c, "LINKS", 2, app.f_meta, pad)
        tk.Frame(c, bg=PAPER, height=12).pack(fill="x")

        self.entries = [self.e_name, self.e_unit, self.e_lo, self.e_hi, self.e_source,
                        self.e_tags, self.e_new]
        self.texts = [self.t_notes, self.t_read, self.t_edges, self.t_links]
        app.bind_undo(self.e_name)
        for w in self.entries + self.texts:
            for ev in ("<KeyRelease>", "<<Paste>>", "<<Cut>>"):
                w.bind(ev, app.mark_dirty, add="+")
        self.t_read.bind("<KeyRelease>", lambda e: self.refresh_summary(), add="+")
        for w in (self.e_lo, self.e_hi):
            w.bind("<KeyRelease>", lambda e: self.refresh_summary(), add="+")

    def enable(self, on):
        state = "normal" if on else "disabled"
        for w in self.entries + self.texts:
            w.configure(state=state)
        self.e_system.configure(state="normal" if on else "disabled")

    def clear(self):
        for w in self.entries:
            w.delete(0, "end")
        for t in self.texts:
            t.delete("1.0", "end")
        self.v_system.set("")
        self.outbox.delete(0, "end")
        self.inbox.delete(0, "end")
        self.summary.configure(text="")
        self.map.set_current(None)
        self.stamp.configure(text="")
        self.msg.configure(text="")

    def open(self, m):
        self.enable(True)
        self.e_name.delete(0, "end")
        self.e_name.insert(0, m.get("name", ""))
        self.v_system.set(m.get("system", ""))
        for w, k in ((self.e_unit, "unit"), (self.e_lo, "ref_low"), (self.e_hi, "ref_high"),
                     (self.e_source, "source")):
            w.delete(0, "end")
            w.insert(0, str(m.get(k, "") or ""))
        self.app.update_source_hint(self.e_source)
        self.e_tags.delete(0, "end")
        self.e_tags.insert(0, ", ".join(m.get("tags", [])))
        self.t_notes.delete("1.0", "end")
        self.t_notes.insert("1.0", m.get("notes", ""))
        self.t_read.delete("1.0", "end")
        self.t_read.insert("1.0", format_readings(m.get("readings", [])))
        self.t_links.delete("1.0", "end")
        self.t_links.insert("1.0", "\n".join(m.get("links", [])))
        self.t_edges.delete("1.0", "end")
        texto = format_edges(edges_from(self.app.data, m["id"]))
        if m.get("edge_drafts"):
            texto = "\n".join(filter(None, [texto] + m["edge_drafts"]))
        self.t_edges.insert("1.0", texto)
        rid = m["id"] if not m["id"].startswith("__") else "rascunho"
        self.stamp.configure(text=f"{rid}\n{m.get('updated', '')}")
        self.msg.configure(text="")
        self.refresh_summary()
        self.refresh_neighbours(m["id"])
        self.map.set_current(m.get("system") or "outro")

    def draw_trend(self):
        """A curva das leituras, em traço, com a faixa de referência tramada.
        Mede a partir do que está digitado, então acompanha a edição."""
        cv = self.trend
        if not cv.winfo_exists():
            return
        cv.delete("all")
        W, H = cv.winfo_width(), int(cv.cget("height"))
        if W < 60:
            return
        m = {"ref_low": self.e_lo.get().strip(), "ref_high": self.e_hi.get().strip()}
        rs = [r for r in parse_readings(self.t_read.get("1.0", "end-1c"))
              if reading_number(r["value"]) is not None]
        if not rs:
            cv.create_text(0, H // 2, text="(sem leituras numéricas)", anchor="w",
                           fill=FAINT, font=self.app.f_label)
            return
        vals = [reading_number(r["value"]) for r in rs]
        lo = reading_number(m["ref_low"]) if m["ref_low"] else None
        hi = reading_number(m["ref_high"]) if m["ref_high"] else None
        vmin = min(vals + [v for v in (lo, hi) if v is not None])
        vmax = max(vals + [v for v in (lo, hi) if v is not None])
        if vmin == vmax:
            vmin, vmax = vmin - 1, vmax + 1
        padL, padR, padT, padB = 4, 40, 10, 16

        def X(i):
            return padL + (i / max(1, len(rs) - 1)) * (W - padL - padR)

        def Y(v):
            return padT + (1 - (v - vmin) / (vmax - vmin)) * (H - padT - padB)

        if lo is not None or hi is not None:
            y0 = Y(hi) if hi is not None else padT
            y1 = Y(lo) if lo is not None else H - padB
            cv.create_rectangle(padL, y0, W - padR, y1, outline="", fill=RULE,
                                stipple="gray25")
        cv.create_line(padL, H - padB, W - padR, H - padB, fill=RULE)
        pts = []
        for i, v in enumerate(vals):
            pts.extend((X(i), Y(v)))
        if len(rs) > 1:
            cv.create_line(*pts, fill=INK, width=1.6, joinstyle="round", capstyle="round")
        for i, (r, v) in enumerate(zip(rs, vals)):
            fora = out_of_range(m, r)
            cv.create_oval(X(i) - 3, Y(v) - 3, X(i) + 3, Y(v) + 3, outline=INK,
                           fill=INK if fora else PAPER, width=1.4)
        cv.create_text(X(len(rs) - 1) + 8, Y(vals[-1]), text=rs[-1]["value"], anchor="w",
                       fill=INK, font=self.app.f_label)
        cv.create_text(padL, H - 2, text=rs[0]["date"][:10], anchor="sw", fill=FAINT,
                       font=self.app.f_label)
        if len(rs) > 1:
            cv.create_text(W - padR, H - 2, text=rs[-1]["date"][:10], anchor="se",
                           fill=FAINT, font=self.app.f_label)
        if hi is not None:
            cv.create_text(W - padR + 8, Y(hi), text=f"{hi:g}", anchor="w", fill=FAINT,
                           font=self.app.f_label)
        if lo is not None:
            cv.create_text(W - padR + 8, Y(lo), text=f"{lo:g}", anchor="w", fill=FAINT,
                           font=self.app.f_label)

    def refresh_summary(self):
        self.draw_trend()
        m = {"ref_low": self.e_lo.get().strip(), "ref_high": self.e_hi.get().strip()}
        rs = parse_readings(self.t_read.get("1.0", "end-1c"))
        if not rs:
            self.summary.configure(text="sem leituras")
            return
        nums = [reading_number(r["value"]) for r in rs]
        nums = [n for n in nums if n is not None]
        fora = sum(1 for r in rs if out_of_range(m, r))
        txt = f"{len(rs)} leituras · última {rs[-1]['date']} = {rs[-1]['value']}"
        if nums:
            txt += f" · mín {min(nums):g} · máx {max(nums):g} · média {sum(nums)/len(nums):.2f}"
        if fora:
            txt += f" · {fora} fora da referência"
        self.summary.configure(text=txt)

    def refresh_neighbours(self, mid):
        app = self.app
        data, idx = app.data, by_id(app.data)
        self.outbox.delete(0, "end")
        self.out_ids = []
        for a in edges_from(data, mid):
            alvo = idx.get(a["to"])
            self.outbox.insert("end", f"{rel_label(a['rel']):18} "
                                      f"{label_any(alvo, data) if alvo else a['to']}")
            self.out_ids.append(a["to"])
        self.inbox.delete(0, "end")
        self.in_ids = []
        for a in edges_to(data, mid):
            src = idx.get(a["from"])
            self.inbox.insert("end", f"{label_any(src, data):30} {rel_label(a['rel'])}")
            self.in_ids.append(a["from"])
        for lb in (self.outbox, self.inbox):
            lb.configure(height=max(2, min(8, lb.size())))

    def gather(self, m):
        out = {k: v for k, v in m.items() if not k.startswith("_")}
        out.update({
            "name": self.e_name.get().strip(),
            "system": self.v_system.get().strip().lower(),
            "unit": self.e_unit.get().strip(),
            "ref_low": self.e_lo.get().strip().replace(",", "."),
            "ref_high": self.e_hi.get().strip().replace(",", "."),
            "source": self.e_source.get().strip(),
            "tags": [t.strip() for t in self.e_tags.get().split(",") if t.strip()],
            "notes": self.t_notes.get("1.0", "end-1c").strip(),
            "readings": parse_readings(self.t_read.get("1.0", "end-1c")),
            "links": [l.strip() for l in self.t_links.get("1.0", "end-1c").splitlines()
                      if l.strip()],
        })
        return out

    def edges_text(self):
        return self.t_edges.get("1.0", "end-1c")

    def add_reading(self):
        text = self.e_new.get().strip()
        if not self.app.current() or not text:
            return
        existing = self.t_read.get("1.0", "end-1c").rstrip()
        line = text if READING_RE.match(text) else f"{TODAY()}   {text}"
        self.t_read.delete("1.0", "end")
        self.t_read.insert("1.0", (existing + "\n" + line) if existing else line)
        self.e_new.delete(0, "end")
        self.app.mark_dirty()
        self.app.refit_card()
        self.app.save()


# ================================================================ janela

class App:
    def __init__(self, root, theme, notices):
        self.root = root
        self.theme = theme
        self.restart_theme = None
        self.data = load_json()
        self.sel = None
        self.scope = None          # None | "people" | "entries"
        self.tag = self.viewmode = self.date = None           # filtros pessoa
        self.view_kind = self.view_lang = self.view_domain = None  # filtros verba
        self.view_stype = None                                # filtro fonte
        self.view_system = None                               # filtro corpus
        self.source_hints = []
        self.draft = None
        self.dirty = False
        self.loading = False
        self.busy = False
        self.undo_resets = []
        self.carets = []
        self.pendings = []
        self.fits = []
        self.shown = None
        self.mode = "livro"        # "livro" (folhas por número) | "indicador" (busca)
        self.folha = None          # folha corrida aberta no livro; None = a última
        self.page = 0              # página do indicador
        self.page_sig = None       # o filtro mudou? então o indicador volta à página 1
        ui = self.data.get("ui") or {}
        self.max_rows = int(ui.get("max_rows") or 10)
        self.locked_panes = bool(ui.get("panes_locked"))
        self.locked_var = tk.BooleanVar(value=self.locked_panes)

        serif = self.pick(["Times New Roman", "Liberation Serif",
                           "DejaVu Serif", "Georgia"], "Times")
        mono = self.pick(["Consolas", "Cascadia Mono", "Lucida Console",
                          "DejaVu Sans Mono", "Courier New"], "Courier")
        wanted = ui.get("font_mono")
        self.font_warning = ""
        if wanted:
            ok, why = self.usable_mono(wanted)
            if ok:
                mono = wanted
            else:
                self.font_warning = f'Tipo "{wanted}" {why}; usando {mono}.'
        body = mono if PAL["mono_only"] else serif
        self.f_name = (body, 15 if PAL["mono_only"] else 17)
        self.f_body = (body, 11)
        self.f_row = (body, 11)
        self.f_meta = (mono, 9)
        self.f_label = (mono, 8)

        root.title("Index")
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w, h = min(1180, sw - 80), min(740, sh - 120)
        root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
        root.minsize(760, 470)
        root.configure(bg=SHELL)

        st = ttk.Style(root)
        st.theme_use("clam")
        st.configure("TFrame", background=SHELL)
        st.configure("TPanedwindow", background=RULE)
        st.configure("Treeview", background=SHELL, fieldbackground=SHELL,
                     foreground=INK, borderwidth=0, rowheight=24, font=self.f_row)
        st.map("Treeview", background=[("selected", SELBG)],
               foreground=[("selected", SELFG)])
        st.configure("TScrollbar", background=RULE, troughcolor=SHELL,
                     bordercolor=SHELL, arrowcolor=SOFT, borderwidth=0,
                     gripcount=0, relief="flat", arrowsize=11)
        st.map("TScrollbar", background=[("active", SOFT)])
        st.configure("Sash", gripcount=0, sashthickness=4, background=RULE,
                     bordercolor=RULE, lightcolor=RULE, darkcolor=RULE)
        st.configure("Tag.Treeview", font=self.f_meta, rowheight=19)
        st.configure("TButton", background=PAPER, foreground=STAMP,
                     font=self.f_meta, borderwidth=1, focuscolor=STAMP,
                     padding=(9, 3), bordercolor=RULE, lightcolor=RULE,
                     darkcolor=RULE, relief="solid")
        st.map("TButton", background=[("active", SELBG)])
        st.configure("Quiet.TButton", foreground=SOFT)

        self.build_bar()
        self.build_body()
        self.build_status()
        self.build_menu()
        self.bind_keys()
        self.reload()
        paint_frame(root)
        if notices:
            self.root.after(500, lambda: self.say(" · ".join(notices)))
        elif self.font_warning:
            self.root.after(600, lambda: self.say(self.font_warning))

    def pick(self, names, fallback):
        have = set(tkfont.families(self.root))
        for n in names:
            if n in have:
                return n
        return fallback

    # ------------------------------------------------------------ chrome
    def build_bar(self):
        bar = tk.Frame(self.root, bg=PAPER, highlightthickness=0)
        bar.pack(fill="x")
        tk.Frame(self.root, bg=RULE, height=1).pack(fill="x")
        tk.Label(bar, text="INDEX", bg=PAPER, fg=STAMP,
                 font=(self.f_meta[0], 10)).pack(side="left", padx=(14, 16), pady=9)
        self.q = tk.StringVar()
        self._q_job = None
        self.q.trace_add("write", lambda *_: self.refresh_list_soon())
        self.entry = tk.Entry(bar, textvariable=self.q, font=(self.f_body[0], 13),
                              bg=PAPER, fg=INK, relief="flat", insertbackground=INK,
                              highlightthickness=1, highlightbackground=RULE,
                              highlightcolor=STAMP)
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.count = tk.Label(bar, text="", bg=PAPER, fg=OXIDE, font=self.f_meta)
        self.count.pack(side="left", padx=14)
        ttk.Button(bar, text="entrada rápida", command=self.quick_add
                   ).pack(side="right", padx=(4, 12))
        ttk.Button(bar, text="+ medida", command=self.new_metric
                   ).pack(side="right", padx=(4, 0))
        ttk.Button(bar, text="+ fonte", command=self.new_source
                   ).pack(side="right", padx=(4, 0))
        ttk.Button(bar, text="+ forma", command=lambda: self.new_entry("form")
                   ).pack(side="right", padx=(4, 0))
        ttk.Button(bar, text="+ conceito", command=lambda: self.new_entry("concept")
                   ).pack(side="right", padx=(4, 0))
        ttk.Button(bar, text="+ pessoa", command=self.new_person).pack(side="right")

    def build_body(self):
        pw = ttk.Panedwindow(self.root, orient="horizontal")
        pw.pack(fill="both", expand=True)

        rail = tk.Frame(pw, bg=SHELL)
        self.rail = ttk.Treeview(rail, columns=("n",), show="tree",
                                 style="Tag.Treeview", selectmode="browse")
        self.rail.column("#0", width=168, stretch=True)
        self.rail.column("n", width=38, anchor="e", stretch=False)
        rsb = ttk.Scrollbar(rail, orient="vertical", command=self.rail.yview)
        self.rail.configure(yscrollcommand=rsb.set)
        rsb.pack(side="right", fill="y")
        self.rail.pack(fill="both", expand=True)
        self.rail.tag_configure("head", foreground=FAINT, font=self.f_label)
        self.rail.tag_configure("on", foreground=OXIDE)
        self.rail.tag_configure("late", foreground=OXIDE)
        self.rail.tag_configure("today", foreground=STAMP)
        self.rail.tag_configure("scope", foreground=STAMP)
        self.rail.bind("<<TreeviewSelect>>", self.on_rail)
        pw.add(rail, weight=0)

        mid = tk.Frame(pw, bg=SHELL)
        head = tk.Frame(mid, bg=SHELL)
        head.pack(fill="x")
        self.page_lbl = tk.Label(head, text="", bg=SHELL, fg=STAMP, font=self.f_label,
                                 anchor="w")
        self.page_lbl.pack(side="left", fill="x", expand=True, padx=(8, 0))
        ttk.Button(head, text="›", width=2, style="Quiet.TButton",
                   command=lambda: self.turn(1)).pack(side="right", padx=(2, 4), pady=3)
        ttk.Button(head, text="‹", width=2, style="Quiet.TButton",
                   command=lambda: self.turn(-1)).pack(side="right", pady=3)
        tk.Frame(mid, bg=RULE, height=1).pack(fill="x")
        self.list = ttk.Treeview(mid, columns=("sub", "loc"), show="tree",
                                 selectmode="browse")
        self.list.column("#0", width=215, stretch=True)
        self.list.column("sub", width=165, stretch=True)
        self.list.column("loc", width=96, anchor="e", stretch=False)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.list.pack(fill="both", expand=True)
        self.list.tag_configure("sub", foreground=FAINT, font=self.f_meta)
        self.list.tag_configure("cancel", foreground=FAINT, font=self.f_meta)
        self.list.bind("<<TreeviewSelect>>", self.on_pick)
        pw.add(mid, weight=1)

        self.cardbox = tk.Frame(pw, bg=PAPER)
        self.locus = tk.Label(self.cardbox, text="", bg=PAPER, fg=FAINT,
                              font=self.f_label, anchor="w", padx=22)
        self.locus.pack(fill="x", pady=(8, 0))
        pw.add(self.cardbox, weight=2)
        self.pw = pw
        self.apply_pane_lock()
        self.pc = PersonCard(self, self.cardbox)
        self.vc = EntryCard(self, self.cardbox)
        self.sc = SourceCard(self, self.cardbox)
        self.mc = MetricCard(self, self.cardbox)
        self.cards = {"person": self.pc, "entry": self.vc, "source": self.sc,
                      "metric": self.mc}
        self.show_card("person")
        for c in self.cards.values():
            c.enable(False)
        self.laid_out = False
        pw.bind("<Configure>", self.first_layout)

    def show_card(self, kind):
        if self.shown == kind:
            return
        for c in self.cards.values():
            c.frame.pack_forget()
        self.cards[kind].frame.pack(fill="both", expand=True)
        self.shown = kind

    @property
    def card(self):
        return self.cards[self.shown or "person"]

    # ---- pedaços compartilhados pelos cartões
    def listbox(self, parent, pad):
        lb = tk.Listbox(parent, height=2, width=1, font=self.f_meta, bg=PAPER, fg=INK,
                        relief="flat", highlightthickness=0, selectbackground=SELBG,
                        selectforeground=SELFG, activestyle="none")
        lb.pack(fill="x", **pad)
        tk.Frame(parent, bg=RULE, height=1).pack(fill="x", pady=(4, 0), **pad)
        return lb

    def jump(self, lb, ids):
        sel = lb.curselection()
        if sel and sel[0] < len(ids):
            self.goto(ids[sel[0]])

    def textfield_bare(self, parent, rows, pad):
        t = tk.Text(parent, height=rows, width=1, font=self.f_meta, bg=PAPER, fg=INK,
                    relief="flat", wrap="word", insertbackground=INK,
                    highlightthickness=0, padx=0, spacing1=1, spacing3=3,
                    undo=True, autoseparators=True, maxundo=-1)
        self.block_caret(t, self.f_meta)
        self.bind_undo(t, text=True)
        t.pack(fill="x", **pad)
        self.autogrow(t, minrows=rows)
        return t

    def source_field(self, parent, pad):
        """O campo FONTE comum a todos os cartões: aceita o id de uma fonte
        (s_…) ou texto livre. Abaixo, o nome resolvido e um botão que abre."""
        self.label(parent, "FONTE  (s_… de uma fonte, ou texto livre)", pad)
        row = tk.Frame(parent, bg=PAPER)
        row.pack(fill="x", **pad)
        e = tk.Entry(row, width=1, font=self.f_meta, bg=PAPER, fg=INK, relief="flat",
                     insertbackground=INK, highlightthickness=0,
                     disabledbackground=PAPER, disabledforeground=FAINT)
        e.pack(side="left", fill="x", expand=True)
        btn = ttk.Button(row, text="abrir", style="Quiet.TButton", width=6,
                         command=lambda: self.goto(e.get().strip()))
        btn.pack(side="right")
        hint = tk.Label(parent, text="", bg=PAPER, fg=SOFT, font=self.f_label, anchor="w")
        hint.pack(fill="x", **pad)
        tk.Frame(parent, bg=RULE, height=1).pack(fill="x", pady=(2, 0), **pad)
        self.bind_undo(e)
        e.bind("<KeyRelease>", lambda ev: self.update_source_hint(e), add="+")
        self.source_hints.append((e, hint, btn))
        return e

    def update_source_hint(self, entry):
        for e, hint, btn in self.source_hints:
            if e is not entry:
                continue
            text = entry.get().strip()
            if text.startswith("s_"):
                s, shown = resolve_source(text, self.data)
                hint.configure(text=("→ " + shown) if s else shown,
                               fg=SOFT if s else OXIDE)
                btn.configure(state="normal" if s else "disabled")
            else:
                hint.configure(text="texto livre (use + fonte para virar registro)"
                               if text else "", fg=FAINT)
                btn.configure(state="disabled")

    def flash(self, text):
        self.card.msg.configure(text=text)

    def first_layout(self, _event=None):
        if self.laid_out:
            return
        width = self.pw.winfo_width()
        if width < 200:
            return
        self.laid_out = True
        saved = (self.data.get("ui") or {}).get("panes")
        if saved and self.apply_panes(saved, width):
            return
        self.reset_layout()

    def apply_panes(self, saved, width):
        try:
            a, b = float(saved[0]), float(saved[1])
        except (TypeError, ValueError, IndexError):
            return False
        if not (0.05 < a < b < 0.95):
            return False
        try:
            self.pw.sashpos(0, int(width * a))
            self.pw.sashpos(1, int(width * b))
            return True
        except Exception:
            return False

    def remember_panes(self):
        width = self.pw.winfo_width()
        if width < 200 or self.locked_panes:
            return
        try:
            a = self.pw.sashpos(0) / width
            b = self.pw.sashpos(1) / width
        except Exception:
            return
        if not (0.05 < a < b < 0.95):
            return
        self.data = save_ui({"panes": [round(a, 4), round(b, 4)]})

    def lock_panes(self):
        self.locked_panes = bool(self.locked_var.get())
        self.data = save_ui({"panes_locked": self.locked_panes})
        self.apply_pane_lock()
        self.say("Larguras travadas." if self.locked_panes else "Larguras livres.")

    def apply_pane_lock(self):
        for seq in ("<Button-1>", "<B1-Motion>", "<ButtonRelease-1>"):
            if self.locked_panes:
                self.pw.bind(seq, lambda e: "break")
            else:
                self.pw.unbind(seq)
        if not self.locked_panes:
            self.pw.bind("<ButtonRelease-1>", lambda e: self.remember_panes(), add="+")

    def reset_layout(self):
        width = max(self.pw.winfo_width(), 700)
        rail = max(150, min(210, int(width * 0.17)))
        listw = max(230, int(width * 0.30))
        try:
            self.pw.sashpos(0, rail)
            self.pw.sashpos(1, rail + listw)
        except Exception:
            pass

    def build_status(self):
        tk.Frame(self.root, bg=RULE, height=1).pack(fill="x")
        row = tk.Frame(self.root, bg=PAPER)
        row.pack(fill="x")
        self.status = tk.Label(row, text="", bg=PAPER, fg=SOFT, font=self.f_meta,
                               anchor="w")
        self.status.pack(side="left", padx=12, pady=4)
        tk.Label(row, text=f"{HOST}  ·  {BASE}", bg=PAPER, fg=FAINT,
                 font=self.f_meta).pack(side="right", padx=12)

    def menu(self, parent):
        return tk.Menu(parent, tearoff=0, bg=PAPER, fg=INK, activebackground=SELBG,
                       activeforeground=SELFG, borderwidth=1, font=self.f_meta)

    def build_menu(self):
        m = self.menu(self.root)
        f = self.menu(m)
        f.add_command(label="Nova pessoa", accelerator="Ctrl+N", command=self.new_person)
        f.add_command(label="Novo conceito", command=lambda: self.new_entry("concept"))
        f.add_command(label="Nova forma", command=lambda: self.new_entry("form"))
        f.add_command(label="Nova fonte", command=self.new_source)
        f.add_command(label="Nova medida (corpus)", command=self.new_metric)
        f.add_command(label="Entrada rápida…", accelerator="Ctrl+Q", command=self.quick_add)
        f.add_separator()
        f.add_command(label="Salvar", accelerator="Ctrl+S", command=self.save)
        f.add_command(label="Recarregar do disco", accelerator="F5", command=self.reload)
        f.add_separator()
        f.add_command(label="Sair", command=self.on_close)
        m.add_cascade(label="Arquivo", menu=f)

        b = self.menu(m)
        b.add_command(label="Refazer espelho markdown", command=self.do_mirror)
        b.add_command(label="Abrir mapa do corpo (corpus, HTML)", command=self.do_corpus)
        b.add_command(label="Verificar estrutura", command=self.do_doctor)
        b.add_command(label="Normalizar #tags inline (pessoas)", command=self.do_normalize)
        b.add_separator()
        b.add_command(label="Absorver conflitos de sincronização", command=self.do_merge)
        b.add_command(label="Histórico do registro aberto", command=self.do_history)
        b.add_separator()
        b.add_command(label="Importar fontes do Zotero (CSL-JSON ou BibTeX)…",
                      command=self.do_import_zotero)
        b.add_command(label="Exportar fontes (BibTeX)", command=lambda: self.do_export("bibtex"))
        b.add_command(label="Exportar fontes (CSL-JSON)", command=lambda: self.do_export("csl"))
        b.add_command(label="Exportar fontes (ABNT, texto)", command=lambda: self.do_export("abnt"))
        m.add_cascade(label="Base", menu=b)

        v = self.menu(m)
        v.add_command(label="Tipo de letra do terminal…", command=self.choose_typeface)
        v.add_command(label="Campos do verbete…", command=self.card_layout_dialog)
        v.add_command(label="Redefinir larguras", command=self.reset_layout)
        v.add_checkbutton(label="Travar larguras", onvalue=True, offvalue=False,
                          variable=self.locked_var, command=self.lock_panes)
        v.add_separator()
        for key, spec in THEMES.items():
            v.add_command(label=("• " if key == self.theme else "   ") + spec["label"],
                          command=lambda k=key: self.switch_theme(k))
        m.add_cascade(label="Ver", menu=v)

        h = self.menu(m)
        h.add_command(label="Atalhos", command=self.do_help)
        m.add_cascade(label="Ajuda", menu=h)
        self.root.config(menu=m)

    def bind_keys(self):
        r = self.root
        r.bind("<Control-f>", lambda e: (self.entry.focus_set(),
                                         self.entry.select_range(0, "end")))
        r.bind("<Control-s>", lambda e: self.save())
        r.bind("<Control-n>", lambda e: self.new_person())
        r.bind("<Control-q>", lambda e: self.quick_add())
        r.bind("<Control-Return>", lambda e: self.save_and_new())
        r.bind("<F5>", lambda e: self.reload())
        r.bind("<Escape>", lambda e: self.list.focus_set())
        r.bind("<Control-j>", lambda e: self.step_record(1))
        r.bind("<Control-k>", lambda e: self.step_record(-1))
        r.bind("<Control-g>", lambda e: self.goto_dialog())
        r.bind("<Control-Key-0>", lambda e: self.set_scope(None))
        for n, key in enumerate(("people", "entries", "sources", "corpus"), 1):
            r.bind(f"<Control-Key-{n}>", lambda e, k=key: self.set_scope(k))
        self.entry.bind("<Down>", lambda e: self.focus_list())
        self.entry.bind("<Return>", lambda e: self.focus_list())
        self.list.bind("<slash>", lambda e: (self.entry.focus_set(),
                                             self.entry.select_range(0, "end"), "break")[2])
        self.list.bind("<Return>", lambda e: self.focus_card())
        self.list.bind("<Home>", lambda e: self.jump_list(0))
        self.list.bind("<End>", lambda e: self.jump_list(-1))
        self.list.bind("<Prior>", lambda e: self.turn(-1))
        self.list.bind("<Next>", lambda e: self.turn(1))
        r.bind("<Control-Prior>", lambda e: self.turn(-1))
        r.bind("<Control-Next>", lambda e: self.turn(1))
        r.bind("<Control-l>", lambda e: self.to_book())

    def jump_list(self, i):
        kids = self.list.get_children()
        if kids:
            self.list.selection_set(kids[i])
            self.list.see(kids[i])
        return "break"

    def focus_card(self):
        if self.sel:
            self.card.e_name.focus_set()
        return "break"

    def step_record(self, delta):
        """Ctrl+J / Ctrl+K: próximo / anterior na lista, de qualquer lugar."""
        kids = self.list.get_children()
        if not kids:
            return "break"
        cur = self.list.selection()
        cur = cur[0] if cur else self.sel
        if cur in kids:
            i = kids.index(cur) + delta
        else:
            i = 0 if delta > 0 else len(kids) - 1
        if not 0 <= i < len(kids):
            # passou da borda: vira a folha
            before = (self.folha, self.page)
            self.turn(delta)
            if (self.folha, self.page) == before:
                return "break"
            kids = self.list.get_children()
            if not kids:
                return "break"
            i = 0 if delta > 0 else len(kids) - 1
        self.list.selection_set(kids[i])
        self.list.see(kids[i])
        return "break"

    def turn(self, delta):
        """Vira a folha do livro, ou a página do indicador."""
        if self.mode == "livro":
            self.folha = max(1, (self.folha or 1) + delta)
        else:
            self.page = max(0, self.page + delta)
        self.refresh_list()
        kids = self.list.get_children()
        if kids:
            self.list.focus(kids[0])
            self.list.yview_moveto(0)
        return "break"

    def to_book(self, folha=None):
        """Ctrl+L: sai da busca e dos filtros e abre o livro na folha do
        registro aberto (ou na folha pedida)."""
        self.commit_if_dirty()
        rec = self.current()
        self.clear_filters()
        self.scope = None
        if folha:
            self.folha = folha
        elif rec and rec.get("reg_n"):
            self.folha = folha_of(rec["reg_n"])
        self.q.set("")
        if self._q_job:          # a busca vazia já vai ser desenhada agora
            try:
                self.root.after_cancel(self._q_job)
            except tk.TclError:
                pass
            self._q_job = None
        self.refresh_rail()
        self.refresh_list()
        if self.sel and self.list.exists(self.sel):
            self.list.see(self.sel)
        self.list.focus_set()
        return "break"

    def set_scope(self, key):
        self.commit_if_dirty()
        self.clear_filters()
        self.scope = key
        self.refresh_rail()
        self.refresh_list()
        if key == "corpus" and (self.sel is None or self.rec_kind(self.current()) != "metric"):
            self.show_corpus_blank()
        return "break"

    def goto_dialog(self):
        """Ctrl+G: ir para um registro pelo id ou pelo nome exato."""
        win = self.dialog("Ir para", 520, 130)
        tk.Label(win, text="IR PARA  (nº, fl. 37, carimbo, id ou nome)", bg=PAPER,
                 fg=FAINT, font=self.f_label).pack(anchor="w", padx=18, pady=(14, 2))
        e = tk.Entry(win, font=self.f_body, bg=PAPER, fg=INK, insertbackground=INK,
                     relief="flat", highlightthickness=1, highlightbackground=RULE,
                     highlightcolor=STAMP)
        e.pack(fill="x", padx=18, ipady=3)

        def go(_ev=None):
            key = e.get().strip()
            win.destroy()
            if not key:
                return
            idx = by_id(self.data)
            if key in idx:
                self.goto(key)
                return
            m = re.fullmatch(r"(?i)\s*(?:g-?(\d+)\s*[·,]?\s*)?(?:fl|folha|f)\.?\s*(\d+)\s*", key)
            if m:
                vol, fl = int(m.group(1) or 1), int(m.group(2))
                self.to_book(folha=(vol - 1) * FOLHAS_POR_LIVRO + max(1, fl))
                return
            m = re.fullmatch(r"(?i)\s*(?:g|n[ºo°.]?)?\s*-?\s*(\d+)\s*", key)
            if m:
                r = find_by_reg(self.data, m.group(1))
                if r and r.get("id") in idx:
                    self.goto(r["id"])
                elif r:
                    self.to_book(folha=folha_of(r["reg_n"]))
                    iid = f"x:{r['reg_n']}"
                    if self.list.exists(iid):
                        self.list.selection_set(iid)
                        self.list.see(iid)
                else:
                    self.say(f"Nenhum registro com nº ou carimbo {m.group(1)}.")
                return
            low = key.lower()
            hits = [r for r in idx.values() if r.get("name", "").lower() == low]
            if not hits:
                hits = [r for r in idx.values() if low in r.get("name", "").lower()]
            if len(hits) == 1:
                self.goto(hits[0]["id"])
            elif hits:
                self.q.set(key)
                self.say(f"{len(hits)} registros com esse nome; escolha na lista.")
            else:
                self.say(f"Nada chamado {key}.")

        e.bind("<Return>", go)
        win.bind("<Escape>", lambda ev: win.destroy())
        e.focus_set()
        return "break"

    # ------------------------------------------------------------ widgets
    def label(self, parent, text, pad):
        tk.Label(parent, text=text, bg=PAPER, fg=FAINT, font=self.f_label,
                 anchor="w").pack(fill="x", pady=(6, 2), **pad)

    def field(self, parent, text, font, pad):
        self.label(parent, text, pad)
        e = tk.Entry(parent, width=1, font=font, bg=PAPER, fg=INK, relief="flat",
                     insertbackground=INK, highlightthickness=0,
                     disabledbackground=PAPER, disabledforeground=FAINT)
        e.pack(fill="x", **pad)
        tk.Frame(parent, bg=RULE, height=1).pack(fill="x", pady=(4, 0), **pad)
        self.bind_undo(e)
        return e

    def textfield(self, parent, text, rows, font, pad):
        self.label(parent, text, pad)
        box = tk.Frame(parent, bg=PAPER)
        box.pack(fill="x", **pad)
        t = tk.Text(box, height=rows, width=1, font=font, bg=PAPER, fg=INK,
                    relief="flat", wrap="word", insertbackground=INK,
                    highlightthickness=0, padx=0, spacing1=1, spacing3=3,
                    undo=True, autoseparators=True, maxundo=-1)
        self.block_caret(t, font)
        self.bind_undo(t, text=True)
        t.pack(side="left", fill="both", expand=True)
        self.autogrow(t, minrows=rows)
        tk.Frame(parent, bg=RULE, height=1).pack(fill="x", pady=(4, 0), **pad)
        return t

    def scroll_area(self, parent):
        """O cartão inteiro rola; os campos dentro dele não."""
        canvas = tk.Canvas(parent, bg=PAPER, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=PAPER)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        pending = {"job": None}

        def apply_region():
            pending["job"] = None
            try:
                if canvas.winfo_exists():
                    canvas.configure(scrollregion=canvas.bbox("all"))
            except tk.TclError:
                pass

        def resized(_e=None):
            if pending["job"]:
                try:
                    canvas.after_cancel(pending["job"])
                except tk.TclError:
                    pass
            pending["job"] = canvas.after(45, apply_region)

        inner.bind("<Configure>", resized)
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))

        def wheel(e):
            if not canvas.winfo_exists():
                return
            step = 1 if (getattr(e, "num", 0) == 5 or e.delta < 0) else -1
            w = e.widget
            if isinstance(w, tk.Text):
                first, last_ = w.yview()
                if not (first <= 0.0 and last_ >= 1.0):
                    w.yview_scroll(step * 2, "units")
                    return
            canvas.yview_scroll(step * 3, "units")

        def claim(_e=None):
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                canvas.bind_all(seq, wheel)

        def release(_e=None):
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                canvas.unbind_all(seq)

        canvas.bind("<Enter>", claim)
        canvas.bind("<Leave>", release)
        self.canvases = getattr(self, "canvases", []) + [canvas]
        self.pendings.append((canvas, pending))
        return inner

    def autogrow(self, t, minrows=2):
        """Tantas linhas quantas o texto precisar, medindo a quebra na fonte
        do próprio widget (perguntar ao Tk não funciona: ele só conta até a
        altura atual)."""
        last = {"n": None, "w": None, "job": None}
        CAP = self.max_rows

        def rows_needed():
            width = t.winfo_width()
            if width <= 1:
                return None
            if len(t.get("1.0", "end-1c")) > 3000:
                return None        # texto longo: contar linhas basta, e não trava
            try:
                f = tkfont.Font(font=t.cget("font"))
            except tk.TclError:
                return None
            space = f.measure(" ")
            rows = 0
            for line in t.get("1.0", "end-1c").split("\n"):
                if not line:
                    rows += 1
                    continue
                used, n = 0, 1
                for word in line.split(" "):
                    w = f.measure(word)
                    if used and used + space + w > width:
                        n += 1
                        used = w
                    else:
                        used += (space if used else 0) + w
                rows += n
            return rows

        def fit(_e=None):
            if not t.winfo_exists():
                return
            n = rows_needed()
            if n is None:
                n = int(t.index("end-1c").split(".")[0])
            n = min(CAP, max(minrows, n))
            if n != last["n"]:
                last["n"] = n
                t.configure(height=n)
            if n < CAP:
                t.yview_moveto(0)

        def later(_e=None):
            if last["job"]:
                try:
                    t.after_cancel(last["job"])
                except tk.TclError:
                    pass
            last["job"] = t.after(45, fit)

        def on_configure(e):
            if e.width == last["w"]:
                return
            last["w"] = e.width
            later()

        t.bind("<KeyRelease>", later, add="+")
        t.bind("<Configure>", on_configure, add="+")
        for seq in ("<<Paste>>", "<<Cut>>", "<<Undo>>", "<<Redo>>"):
            t.bind(seq, later, add="+")
        self.fits.append(fit)
        self.pendings.append((t, last))
        return fit

    def refit_card(self):
        for fit in self.fits:
            fit()
        for canvas in getattr(self, "canvases", []):
            if canvas.winfo_exists():
                canvas.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas.yview_moveto(0)

    def bind_undo(self, widget, text=False):
        """Ctrl+Z / Ctrl+Y em tudo. Text tem pilha própria; Entry ganha uma."""
        if text:
            def undo(_e=None):
                try:
                    widget.edit_undo()
                except tk.TclError:
                    pass
                self.mark_dirty()
                return "break"

            def redo(_e=None):
                try:
                    widget.edit_redo()
                except tk.TclError:
                    pass
                self.mark_dirty()
                return "break"

            self.undo_resets.append(
                lambda w=widget: (w.edit_reset(), w.edit_modified(False)))
        else:
            import time as _time
            hist = {"stack": [""], "pos": 0, "when": 0.0}

            def commit():
                val = widget.get()
                if hist["stack"][hist["pos"]] == val:
                    return
                del hist["stack"][hist["pos"] + 1:]
                hist["stack"].append(val)
                hist["pos"] = len(hist["stack"]) - 1
                if len(hist["stack"]) > 200:
                    hist["stack"].pop(0)
                    hist["pos"] -= 1

            def snapshot(event=None):
                now = _time.monotonic()
                boundary = event is not None and getattr(
                    event, "char", "") in (" ", ",", ".", ";", ":", "-", "/")
                if boundary or now - hist["when"] > 0.7:
                    commit()
                hist["when"] = now

            def restore(val):
                widget.delete(0, "end")
                widget.insert(0, val)
                widget.icursor("end")

            def undo(_e=None):
                commit()
                if hist["pos"] > 0:
                    hist["pos"] -= 1
                    restore(hist["stack"][hist["pos"]])
                    self.mark_dirty()
                return "break"

            def redo(_e=None):
                if hist["pos"] < len(hist["stack"]) - 1:
                    hist["pos"] += 1
                    restore(hist["stack"][hist["pos"]])
                    self.mark_dirty()
                return "break"

            def reset(w=widget):
                hist["stack"] = [w.get()]
                hist["pos"] = 0
                hist["when"] = 0.0

            widget.bind("<KeyRelease>", snapshot, add="+")
            widget.bind("<<Paste>>", lambda e: widget.after(1, commit), add="+")
            self.undo_resets.append(reset)

        for seq in ("<Control-z>", "<Control-Z>"):
            widget.bind(seq, undo)
        for seq in ("<Control-y>", "<Control-Y>", "<Control-Shift-Z>",
                    "<Control-Shift-z>"):
            widget.bind(seq, redo)

    def char_width(self, font):
        try:
            return max(2, tkfont.Font(family=font[0], size=font[1]).measure("M"))
        except Exception:
            return 8

    def stop_carets(self):
        """Cancela todo temporizador antes de a janela ser destruída."""
        for t, state in self.carets + self.pendings:
            try:
                if state.get("job"):
                    t.after_cancel(state["job"])
                    state["job"] = None
            except Exception:
                pass
        self.carets = []

    def block_caret(self, t, font):
        """Cursor em bloco, invertendo o caractere sob ele."""
        cw = self.char_width(font)
        t.configure(insertwidth=0, insertbackground=INK)
        t.tag_configure("caret", background=INK, foreground=PAPER)
        try:
            t.tag_lower("caret", "sel")
        except tk.TclError:
            pass
        state = {"on": True, "job": None, "focus": False}

        def paint():
            if not t.winfo_exists():
                return
            t.tag_remove("caret", "1.0", "end")
            if not state["focus"] or not state["on"] or t.tag_ranges("sel"):
                t.configure(insertwidth=0)
                return
            i = t.index("insert")
            if t.compare(i, ">=", i.split(".")[0] + ".end"):
                t.configure(insertwidth=cw)
            else:
                t.configure(insertwidth=0)
                t.tag_add("caret", i, i + "+1c")

        def blink():
            if not t.winfo_exists():
                return
            state["on"] = not state["on"]
            paint()
            state["job"] = t.after(530, blink)

        def wake(_e=None):
            state["on"] = True
            paint()

        def gained(_e=None):
            state["focus"] = True
            wake()

        def lost(_e=None):
            state["focus"] = False
            paint()

        t.bind("<FocusIn>", gained, add="+")
        t.bind("<FocusOut>", lost, add="+")
        for ev in ("<KeyRelease>", "<ButtonRelease-1>", "<<Selection>>", "<B1-Motion>"):
            t.bind(ev, wake, add="+")
        state["job"] = t.after(530, blink)
        self.carets.append((t, state))
        paint()

    def usable_mono(self, family):
        try:
            if family not in tkfont.families(self.root):
                return False, "não instalado"
            f = tkfont.Font(family=family, size=11)
            widths = {f.measure(ch) for ch in "imMW1."}
            if len(widths) != 1:
                return False, "não é monoespaçado"
            if f.measure("M") < 3:
                return False, "sem métricas"
        except tk.TclError:
            return False, "ilegível"
        return True, ""

    def mono_families(self):
        out = []
        for fam in sorted(set(tkfont.families(self.root))):
            if fam.startswith("@"):
                continue
            ok, _ = self.usable_mono(fam)
            if ok:
                out.append(fam)
        return out

    # ------------------------------------------------------------ dados
    def reload(self):
        self.data = load_json()
        for p in self.data["people"]:
            p["_h"] = haystack_person(p)
        for e in self.data["entries"]:
            e["_h"] = haystack_entry(e, self.data)
        for s in self.data["sources"]:
            s["_h"] = haystack_source(s, self.data)
        for m in self.data["corpus"]:
            m["_h"] = haystack_metric(m, self.data)
        if self.draft:
            self.data[coll_of(self.draft["id"])].append(self.draft)
        self.refresh_rail()
        self.refresh_list()
        if getattr(self, "mc", None) and self.shown == "metric":
            self.mc.map.redraw()
        self.say(summary(self.data))

    def say(self, text):
        self.status.configure(text=text)

    def current(self):
        if not self.sel:
            return None
        return by_id(self.data).get(self.sel)

    def rec_kind(self, rec):
        return {"people": "person", "entries": "entry", "sources": "source",
                "corpus": "metric"}[coll_of((rec or {}).get("id", ""))]

    def refresh_list_soon(self):
        """A lista redesenha 150 ms depois da última tecla, não a cada uma."""
        if self._q_job:
            try:
                self.root.after_cancel(self._q_job)
            except tk.TclError:
                pass
        self._q_job = self.root.after(150, self.refresh_list)

    def parse_query(self):
        """Operadores da busca:
             p: v: f: c:      restringe ao acervo (pessoas, verba, fontes, corpus)
             ^texto           só o começo do nome
             tag:x lang:de type:livro sys:renal dom:direito id:c_medida
           O resto são termos literais, todos obrigatórios."""
        q = self.q.get().strip().lower()
        scope, prefix, fields, terms = None, None, {}, []
        for tok in q.split():
            if tok in ("p:", "v:", "f:", "c:"):
                scope = {"p:": "people", "v:": "entries", "f:": "sources",
                         "c:": "corpus"}[tok]
            elif tok.startswith("^") and len(tok) > 1:
                prefix = tok[1:]
            elif ":" in tok and tok.split(":", 1)[0] in ("tag", "lang", "type", "sys",
                                                          "dom", "id") and tok.split(":", 1)[1]:
                k, v = tok.split(":", 1)
                fields[k] = v
            else:
                terms.append(tok)
        return scope, prefix, fields, terms

    def field_ok(self, r, fields):
        for k, v in fields.items():
            if k == "tag" and not any(v in t.lower() for t in r.get("tags", [])):
                return False
            if k == "lang" and (r.get("lang") or "").lower() != v:
                return False
            if k == "type" and v not in (r.get("type") or "").lower():
                return False
            if k == "sys" and v not in (r.get("system") or "").lower():
                return False
            if k == "dom" and not any(v in d.lower() for d in r.get("domains", [])):
                return False
            if k == "id" and not r.get("id", "").lower().startswith(v):
                return False
        return True

    def matches(self):
        qscope, prefix, fields, terms = self.parse_query()
        scope = qscope or self.scope
        out = []

        def base_ok(r):
            if terms and not all(t in r.get("_h", "") for t in terms):
                return False
            if prefix and not sort_key(r.get("name", ""))[0].startswith(
                    sort_key(prefix)[0]):
                return False
            return self.field_ok(r, fields) if fields else True

        if scope in (None, "people"):
            for p in self.data["people"]:
                if not base_ok(p):
                    continue
                if self.tag and self.tag not in p.get("tags", []):
                    continue
                if self.viewmode in ("todo", "doing", "waiting") and \
                        not open_tasks(p, self.viewmode):
                    continue
                if self.viewmode == "untagged" and p.get("tags"):
                    continue
                if self.date and not any(t["due"] == self.date for t in dated_tasks(p)):
                    continue
                out.append(p)
        if scope in (None, "entries"):
            for e in self.data["entries"]:
                if not base_ok(e):
                    continue
                if self.view_kind and e["kind"] != self.view_kind:
                    continue
                if self.view_lang and e.get("lang") != self.view_lang:
                    continue
                if self.view_domain and self.view_domain not in e.get("domains", []):
                    continue
                out.append(e)
        if scope in (None, "sources"):
            for s in self.data["sources"]:
                if not base_ok(s):
                    continue
                if self.view_stype and (s.get("type") or "outro") != self.view_stype:
                    continue
                out.append(s)
        if scope in (None, "corpus"):
            for m in self.data["corpus"]:
                if not base_ok(m):
                    continue
                if self.view_system is not None and (m.get("system") or "") != self.view_system:
                    continue
                out.append(m)
        out.sort(key=lambda r: sort_key(label_any(r, self.data) if coll_of(r["id"]) == "sources"
                                        else r["name"]))
        return out

    def row_text(self, r):
        """(título, subtítulo) de um registro na lista."""
        kind = self.rec_kind(r)
        if kind == "entry":
            sub = ("conceito" if r["kind"] == "concept" else "forma") \
                + " · " + (r.get("gloss") or "")
            return label_of(r), sub
        if kind == "source":
            au = author_names(r, self.data)
            sub = (r.get("type") or "outro") + " · " + ", ".join(
                a.split(",")[0] for a in au[:2]) + (f" · {year_of_source(r)}"
                                                    if year_of_source(r) else "")
            return r.get("name") or r.get("raw", ""), sub
        if kind == "metric":
            lr = last_reading(r)
            sub = (r.get("system") or "") + (f" · {lr['date']} = {lr['value']} "
                                             f"{r.get('unit', '')}" if lr else " · sem leituras")
            if lr and out_of_range(r, lr):
                sub += "  (!)"
            return r["name"], sub
        p = r
        live = open_tasks(p)
        dated = sorted(dated_tasks(p), key=lambda t: due_label(t))
        if self.date:
            live = [t for t in dated if t["due"] == self.date] or live
        elif dated:
            live = dated + [t for t in live if t not in dated]
        if live:
            when = due_label(live[0])
            sub = "[{}] {}".format(MARK_OF.get(live[0].get("state"), " "),
                                   live[0].get("text", ""))
            if when:
                sub = when + "  " + sub
            if len(live) > 1:
                sub += f"  (+{len(live) - 1})"
        else:
            plain = [t for t in p.get("tags", []) if ":" not in t]
            sub = " · ".join(plain) or one_liner(p.get("notes_raw", ""), 70)
        return p["name"], sub

    def insert_row(self, r, loc):
        text, sub = self.row_text(r)
        self.list.insert("", "end", iid=r["id"], text=one_liner(text, 60),
                         values=(one_liner(sub, 60), loc), tags=("sub",))

    def filter_sig(self):
        return (self.q.get().strip(), self.scope, self.tag, self.viewmode, self.date,
                self.view_kind, self.view_lang, self.view_domain, self.view_stype,
                self.view_system)

    def refresh_list(self):
        """Sem busca nem filtro, a lista é o LIVRO: uma folha de FOLHA números
        de cada vez, na ordem de registro, com os cancelados no lugar. Com
        busca ou filtro, é o INDICADOR: o que bate, em ordem alfabética,
        paginado do mesmo tamanho, cada linha com seu endereço no livro."""
        self._q_job = None
        sig = self.filter_sig()
        if sig != self.page_sig:
            self.page_sig = sig
            self.page = 0
        filtered = bool(any(sig[:-1]) or self.view_system is not None)
        self.list.delete(*self.list.get_children())
        total = sum(len(self.data[c]) for c in COLLS)
        if filtered:
            self.mode = "indicador"
            self.view = self.matches()
            pages = max(1, -(-len(self.view) // FOLHA))
            self.page = min(self.page, pages - 1)
            for r in self.view[self.page * FOLHA:(self.page + 1) * FOLHA]:
                n = r.get("reg_n")
                if n:
                    vol, fl = locus(n)
                    loc = (f"{BOOK}-{vol} " if vol > 1 else "") + f"fl. {fl} · nº {n}"
                else:
                    loc = "novo"
                self.insert_row(r, loc)
            self.page_lbl.configure(
                text=f"INDICADOR · FOLHA {self.page + 1} DE {pages}")
            self.count.configure(text=f"{len(self.view)} de {total}")
        else:
            self.mode = "livro"
            book, gone, loose = {}, {}, []
            for c in COLLS:
                for r in self.data[c]:
                    if r.get("reg_n"):
                        book[r["reg_n"]] = r
                    else:
                        loose.append(r)
            for d in self.data.get("deleted", []):
                if d.get("reg_n") and d["reg_n"] not in book:
                    gone[d["reg_n"]] = d
            top = max(list(book) + list(gone), default=0)
            last = folha_of(top) if top else 1
            if loose and top and top % FOLHA == 0:
                last += 1          # o rascunho abre a folha seguinte
            if self.folha is None or self.folha > last:
                self.folha = last
            self.view = [book[n] for n in sorted(book)] + loose
            first = (self.folha - 1) * FOLHA + 1
            for n in range(first, first + FOLHA):
                if n in book:
                    self.insert_row(book[n], f"nº {n}")
                elif n in gone:
                    d = gone[n]
                    self.list.insert("", "end", iid=f"x:{n}",
                                     text=f"cancelado · {one_liner(d.get('name', ''), 40)}",
                                     values=(f"em {(d.get('at') or '')[:10]}", f"nº {n}"),
                                     tags=("cancel",))
            if self.folha == last:
                for r in loose:
                    self.insert_row(r, "novo")
            self.page_lbl.configure(text=f"{folha_label(self.folha)}  ·  {self.folha} / {last}")
            self.count.configure(text=f"{total} registros")
        if self.sel and self.list.exists(self.sel):
            self.list.selection_set(self.sel)

    def show_in_list(self, rid):
        """Leva a lista à folha (ou página) onde o registro está."""
        rec = by_id(self.data).get(rid)
        if not rec or self.list.exists(rid):
            return
        if self.mode == "livro":
            self.folha = folha_of(rec["reg_n"]) if rec.get("reg_n") else None
            self.refresh_list()
        elif rec in self.view:
            self.page = self.view.index(rec) // FOLHA
            self.refresh_list()

    def set_locus(self, rec):
        if not rec:
            self.locus.configure(text="")
            return
        n = rec.get("reg_n")
        if not n:
            self.locus.configure(text="SEM REGISTRO · RECEBE NÚMERO NO LIVRO AO SALVAR")
            return
        text = f"LIVRO {locus_label(n).upper()}    REGISTRADO {stamp_label(rec.get('reg'))}"
        if rec.get("reg_origem"):
            text += f"  (inferido: {REG_ORIGEM.get(rec['reg_origem'], rec['reg_origem'])})"
        if rec.get("reg_n_anterior"):
            text += f"  · antes nº {rec['reg_n_anterior']}"
        self.locus.configure(text=text)

    def refresh_rail(self):
        r = self.rail
        r.delete(*r.get_children())
        people, entries = self.data["people"], self.data["entries"]
        r.insert("", "end", iid="h0", text="ACERVO", tags=("head",))
        r.insert("", "end", iid="s:people", text="  pessoas", values=(len(people),),
                 tags=("on",) if self.scope == "people" else ("scope",))
        r.insert("", "end", iid="s:entries", text="  verba", values=(len(entries),),
                 tags=("on",) if self.scope == "entries" else ("scope",))
        r.insert("", "end", iid="s:sources", text="  fontes", values=(len(self.data["sources"]),),
                 tags=("on",) if self.scope == "sources" else ("scope",))
        r.insert("", "end", iid="s:corpus", text="  corpus", values=(len(self.data["corpus"]),),
                 tags=("on",) if self.scope == "corpus" else ("scope",))

        if self.scope in (None, "people"):
            counts = {k: sum(1 for p in people if open_tasks(p, k))
                      for k in ("todo", "doing", "waiting")}
            untag = sum(1 for p in people if not p.get("tags"))
            r.insert("", "end", iid="h1", text="", tags=("head",))
            r.insert("", "end", iid="h1b", text="TRABALHO", tags=("head",))
            for key, lab, n in (("todo", "a fazer", counts["todo"]),
                                ("doing", "em curso", counts["doing"]),
                                ("waiting", "esperando", counts["waiting"]),
                                ("untagged", "sem tag", untag)):
                r.insert("", "end", iid="v:" + key, text="  " + lab, values=(n,),
                         tags=("on",) if self.viewmode == key else ())
            tags = {}
            for p in people:
                for t in p.get("tags", []):
                    if ":" not in t:
                        tags[t] = tags.get(t, 0) + 1
            if tags:
                r.insert("", "end", iid="h2", text="", tags=("head",))
                r.insert("", "end", iid="h2b", text="TAGS", tags=("head",))
                for t in sorted(tags, key=sort_key):
                    r.insert("", "end", iid="t:" + t, text="  " + t, values=(tags[t],),
                             tags=("on",) if self.tag == t else ())
            days = {}
            for p in people:
                for t in dated_tasks(p):
                    days[t["due"]] = days.get(t["due"], 0) + 1
            if days:
                r.insert("", "end", iid="h3", text="", tags=("head",))
                r.insert("", "end", iid="h3b", text="CALENDÁRIO", tags=("head",))
                today = TODAY()
                for day in sorted(days):
                    if day < today:
                        mark, flag = ("late",), "! "
                    elif day == today:
                        mark, flag = ("today",), "> "
                    else:
                        mark, flag = (), "  "
                    if self.date == day:
                        mark = ("on",)
                    r.insert("", "end", iid="d:" + day, text=flag + day,
                             values=(days[day],), tags=mark)

        if self.scope in (None, "entries"):
            n_c = sum(1 for e in entries if e["kind"] == "concept")
            n_f = sum(1 for e in entries if e["kind"] == "form")
            r.insert("", "end", iid="h4", text="", tags=("head",))
            r.insert("", "end", iid="h4b", text="TIPO", tags=("head",))
            for key, lab, n in (("concept", "conceitos", n_c), ("form", "formas", n_f)):
                r.insert("", "end", iid="k:" + key, text="  " + lab, values=(n,),
                         tags=("on",) if self.view_kind == key else ())
            langs = {}
            for e in entries:
                if e["kind"] == "form" and e.get("lang"):
                    langs[e["lang"]] = langs.get(e["lang"], 0) + 1
            if langs:
                r.insert("", "end", iid="h5", text="", tags=("head",))
                r.insert("", "end", iid="h5b", text="LÍNGUA", tags=("head",))
                for lang in sorted(langs, key=sort_key):
                    r.insert("", "end", iid="l:" + lang, text="  " + lang,
                             values=(langs[lang],),
                             tags=("on",) if self.view_lang == lang else ())
            doms = {}
            for e in entries:
                for d in e.get("domains", []):
                    doms[d] = doms.get(d, 0) + 1
            if doms:
                r.insert("", "end", iid="h6", text="", tags=("head",))
                r.insert("", "end", iid="h6b", text="DOMÍNIO", tags=("head",))
                for d in sorted(doms, key=sort_key):
                    r.insert("", "end", iid="m:" + d, text="  " + d, values=(doms[d],),
                             tags=("on",) if self.view_domain == d else ())

        if self.scope in (None, "sources") and self.data["sources"]:
            types = {}
            for s in self.data["sources"]:
                t = s.get("type") or "outro"
                types[t] = types.get(t, 0) + 1
            r.insert("", "end", iid="h7", text="", tags=("head",))
            r.insert("", "end", iid="h7b", text="TIPO DE FONTE", tags=("head",))
            for t in sorted(types, key=sort_key):
                r.insert("", "end", iid="y:" + t, text="  " + t, values=(types[t],),
                         tags=("on",) if self.view_stype == t else ())
        if self.scope in (None, "corpus") and self.data["corpus"]:
            systems = {}
            for m in self.data["corpus"]:
                sname = m.get("system") or ""
                systems[sname] = systems.get(sname, 0) + 1
            r.insert("", "end", iid="h8", text="", tags=("head",))
            r.insert("", "end", iid="h8b", text="SISTEMA", tags=("head",))
            for sname in sorted(systems, key=sort_key):
                r.insert("", "end", iid="z:" + sname, text="  " + (sname or "(sem sistema)"),
                         values=(systems[sname],),
                         tags=("on",) if self.view_system == sname else ())

    def filter_system(self, sname):
        """Clique no mapa: filtra a lista pelo sistema (de novo, tira o filtro)."""
        self.commit_if_dirty()
        was = self.view_system
        self.clear_filters()
        self.view_system = None if was == sname else sname
        self.scope = "corpus"
        self.refresh_rail()
        self.refresh_list()
        if self.sel is None or self.rec_kind(self.current()) != "metric":
            self.show_corpus_blank()
        else:
            self.mc.map.set_current(self.view_system)

    def show_corpus_blank(self):
        """Sem medida aberta, o cartão de corpus mostra só o mapa."""
        self.blank_card()
        self.show_card("metric")
        self.mc.map.set_current(self.view_system)

    def clear_filters(self):
        self.tag = self.viewmode = self.date = None
        self.view_kind = self.view_lang = self.view_domain = None
        self.view_stype = self.view_system = None

    def on_rail(self, _event):
        sel = self.rail.selection()
        if not sel:
            return
        self.commit_if_dirty()
        iid = sel[0]
        key = iid[2:]
        if iid.startswith("s:"):
            self.clear_filters()
            self.scope = None if self.scope == key else key
        elif iid.startswith("v:"):
            was = self.viewmode
            self.clear_filters()
            self.viewmode = None if was == key else key
            self.scope = "people"
        elif iid.startswith("t:"):
            was = self.tag
            self.clear_filters()
            self.tag = None if was == key else key
            self.scope = "people"
        elif iid.startswith("d:"):
            was = self.date
            self.clear_filters()
            self.date = None if was == key else key
            self.scope = "people"
        elif iid.startswith("k:"):
            was = self.view_kind
            self.clear_filters()
            self.view_kind = None if was == key else key
            self.scope = "entries"
        elif iid.startswith("l:"):
            was = self.view_lang
            self.clear_filters()
            self.view_lang = None if was == key else key
            self.scope = "entries"
        elif iid.startswith("m:"):
            was = self.view_domain
            self.clear_filters()
            self.view_domain = None if was == key else key
            self.scope = "entries"
        elif iid.startswith("y:"):
            was = self.view_stype
            self.clear_filters()
            self.view_stype = None if was == key else key
            self.scope = "sources"
        elif iid.startswith("z:"):
            was = self.view_system
            self.clear_filters()
            self.view_system = None if was == key else key
            self.scope = "corpus"
        else:
            return
        self.rail.selection_remove(*self.rail.selection())
        self.refresh_rail()
        self.refresh_list()
        if self.scope == "corpus" and (self.sel is None
                                       or self.rec_kind(self.current()) != "metric"):
            self.show_corpus_blank()
        elif self.scope == "corpus":
            self.mc.map.set_current(self.view_system or (self.current() or {}).get("system"))

    def focus_list(self):
        self.list.focus_set()
        kids = self.list.get_children()
        if kids and not self.list.selection():
            self.list.selection_set(kids[0])

    def on_pick(self, _event):
        if self.busy:
            return
        sel = self.list.selection()
        if not sel or sel[0] == self.sel:
            return
        rid = sel[0]
        self.busy = True
        try:
            self.commit_if_dirty()
            if rid.startswith("x:"):
                self.show_cancelled(int(rid[2:]))
            elif self.list.exists(rid):
                self.open_record(rid)
            else:
                self.blank_card()
        finally:
            self.busy = False

    def blank_card(self):
        self.loading = True
        for c in self.cards.values():
            c.clear()
            c.enable(False)
        self.loading = False
        self.dirty = False
        self.sel = None
        self.set_locus(None)

    def show_cancelled(self, n):
        """Linha cancelada do livro: o cartão fica vazio e o cabeçalho diz
        o que ocupava o número."""
        d = next((d for d in self.data.get("deleted", []) if d.get("reg_n") == n), None)
        self.blank_card()
        if d:
            self.locus.configure(
                text=f"LIVRO {locus_label(n).upper()}    CANCELADO EM "
                     f"{(d.get('at') or '').replace('T', ' ')}  ·  "
                     f"{d.get('name', '')}  ({d.get('id', '')})")
            self.say("Registro cancelado: o histórico está no log (Base › Histórico).")

    def open_record(self, rid):
        rec = by_id(self.data).get(rid)
        if not rec:
            return
        self.sel = rid
        self.loading = True
        kind = self.rec_kind(rec)
        self.show_card(kind)
        self.card.open(rec)
        self.set_locus(rec)
        for reset in self.undo_resets:
            try:
                reset()
            except Exception:
                pass
        self.show_in_list(rid)
        if self.list.exists(rid):
            self.list.selection_set(rid)
            self.list.see(rid)
        self.loading = False
        self.dirty = False
        self.refit_card()

    def goto(self, rid):
        if rid not in by_id(self.data):
            self.say(f"{rid} não existe.")
            return
        self.commit_if_dirty()
        self.busy = True
        try:
            self.open_record(rid)
        finally:
            self.busy = False

    def mark_dirty(self, _event=None):
        if not self.loading:
            self.dirty = True
            self.flash("")

    # ------------------------------------------------------------ escrita
    def new_person(self):
        self.commit_if_dirty()
        self.draft = blank_person(self.q.get().strip())
        self.draft["id"] = "__draft_p__"
        self.draft["_h"] = ""
        self.data["people"].append(self.draft)
        self.refresh_list()
        self.open_record("__draft_p__")
        self.pc.e_name.focus_set()
        self.say("Pessoa nova. Só vai ao disco quando salvar.")

    def new_entry(self, kind):
        self.commit_if_dirty()
        self.draft = {"id": "__draft_e__", "kind": kind, "name": "", "gloss": "",
                      "tags": [], "notes": "", "source": "", "links": [],
                      "domains": [], "updated": None, "_h": ""}
        if kind == "form":
            self.draft.update({"lang": "", "roman": "", "attested": "",
                               "status": "attested"})
        self.data["entries"].append(self.draft)
        self.refresh_list()
        self.open_record("__draft_e__")
        self.vc.e_name.focus_set()
        self.say("Verbete novo. O id é gerado ao salvar com nome.")

    def new_source(self):
        self.commit_if_dirty()
        raw = self.q.get().strip()
        self.draft = source_from_raw(raw) if raw else fix_source({"type": "livro"})
        self.draft["id"] = "__draft_s__"
        self.draft["_h"] = ""
        self.data["sources"].append(self.draft)
        self.refresh_list()
        self.open_record("__draft_s__")
        self.sc.e_name.focus_set()
        self.say("Fonte nova. O id é gerado ao salvar com título.")

    def new_metric(self):
        self.commit_if_dirty()
        self.draft = fix_metric({"id": "__draft_h__", "name": self.q.get().strip(),
                                 "system": self.view_system or ""})
        self.draft["_h"] = ""
        self.data["corpus"].append(self.draft)
        self.refresh_list()
        self.open_record("__draft_h__")
        self.mc.e_name.focus_set()
        self.say("Medida nova. O id é gerado ao salvar com nome.")

    def _save_linked(self, coll, card, rec, auto, make_id_fn, what):
        """Fontes e medidas: registro + ligações que saem dele, como verba."""
        out = card.gather(rec)
        if not out["name"]:
            if not auto:
                self.flash(f"{what} precisa de nome.")
            return None
        if out["id"].startswith("__"):
            out["id"] = make_id_fn(out, set(by_id(load_json())))
        novas = parse_edges(card.edges_text(), out["id"])
        ruins = [a["to"] for a in novas if a.get("_bad")]
        novas = [a for a in novas if not a.get("_bad")]
        if ruins:
            out["edge_drafts"] = ruins
        else:
            out.pop("edge_drafts", None)
        touch(out)
        self.data = save_record(coll, out, edges=novas)
        self.safe_mirror(self.data)
        if ruins:
            self.say(f"{len(ruins)} linha(s) de ligação não entendidas ficaram como rascunho.")
        elif auto:
            self.say(f'Salvo "{one_liner(out["name"], 40)}" automaticamente.')
        return out["id"]

    def save(self, reopen=True, auto=False):
        if not self.sel:
            return None
        rec = self.current()
        if not rec:
            return None
        kind = self.rec_kind(rec)
        try:
            if kind == "person":
                new_id = self._save_person(rec, auto)
            elif kind == "entry":
                new_id = self._save_entry(rec, auto)
            elif kind == "source":
                new_id = self._save_linked("sources", self.sc, rec, auto,
                                           new_source_id, "Uma fonte")
            else:
                new_id = self._save_linked("corpus", self.mc, rec, auto,
                                           new_metric_id, "Uma medida")
        except SystemExit as exc:
            self.notify("Não salvo", str(exc))
            return None
        if new_id is None:
            return None
        self.draft = None
        self.dirty = False
        self.sel = new_id
        self.reload()
        if reopen:
            self.open_record(new_id)
            self.flash("Salvo " + TODAY())
        return new_id

    def _save_person(self, p, auto):
        rec = self.pc.gather(p)
        if not rec["name"]:
            if not auto:
                self.flash("Uma pessoa precisa de nome.")
            return None
        filed = fold_finished_tasks(rec)
        if rec["id"].startswith("__"):
            rec["met"] = rec.get("met") or TODAY()
            rec["id"] = make_id(rec["name"], set(by_id(load_json())))
        touch(rec)
        self.data = save_record("people", rec)
        self.safe_mirror(self.data)
        if filed:
            self.say(f"{filed} tarefa(s) concluída(s) foram para o log.")
        elif auto:
            self.say(f'Salvo "{one_liner(rec["name"], 40)}" automaticamente.')
        return rec["id"]

    def _save_entry(self, e, auto):
        rec = self.vc.gather(e)
        if not rec["name"]:
            if not auto:
                self.flash("Um verbete precisa de nome.")
            return None
        old = rec["id"]
        if old.startswith("__"):
            rec["id"] = new_id(rec["kind"], rec["name"], set(by_id(load_json())))
        novas = parse_edges(self.vc.edges_text(), rec["id"])
        ruins = [a["to"] for a in novas if a.get("_bad")]
        novas = [a for a in novas if not a.get("_bad")]
        if ruins:
            rec["edge_drafts"] = ruins
        else:
            rec.pop("edge_drafts", None)
        touch(rec)
        self.data = save_record("entries", rec, edges=novas)
        self.safe_mirror(self.data)
        if ruins:
            self.say(f"{len(ruins)} linha(s) de ligação não entendidas ficaram "
                     "como rascunho.")
        elif auto:
            self.say(f'Salvo "{one_liner(rec["name"], 40)}" automaticamente.')
        return rec["id"]

    def commit_if_dirty(self):
        if not self.dirty or not self.sel:
            return
        if not self.card.e_name.get().strip():
            self.dirty = False
            if self.sel.startswith("__"):
                self.draft = None
            return
        self.save(reopen=False, auto=True)

    def save_and_new(self):
        rec = self.current()
        kind = self.rec_kind(rec)
        ekind = (rec or {}).get("kind", "concept")
        if self.save() is not None:
            {"person": self.new_person, "source": self.new_source,
             "metric": self.new_metric,
             "entry": lambda: self.new_entry(ekind)}[kind]()

    def delete(self):
        rec = self.current()
        if not rec:
            return
        if rec["id"].startswith("__"):
            self.draft = None
            self.sel = None
            self.reload()
            self.blank_card()
            return
        n = len(edges_from(self.data, rec["id"])) + len(edges_to(self.data, rec["id"]))
        msg = f'Apagar "{label_any(rec, self.data)}"?'
        if n:
            msg += f"\n\n{n} ligação(ões) envolvendo este registro também somem."
        msg += "\n\nO log guarda a versão anterior (menu Base › Histórico)."
        if not self.confirm("Apagar", msg, yes="Apagar"):
            return
        coll = coll_of(rec["id"])
        self.data, _ = delete_record(coll, rec["id"], rec.get("name", ""))
        self.safe_mirror(self.data)
        self.sel = None
        self.reload()
        self.blank_card()
        self.say("Apagado. A versão anterior está no log.")

    def known_langs(self):
        langs = {e.get("lang") for e in self.data["entries"]
                 if e.get("kind") == "form" and e.get("lang")}
        return sorted(langs, key=sort_key)

    def quick_add(self):
        """Várias entradas de uma vez, uma por linha."""
        self.commit_if_dirty()
        win = self.dialog("Entrada rápida", 640, 520)
        tk.Label(win, text="ENTRADA RÁPIDA", bg=PAPER, fg=FAINT,
                 font=self.f_label).pack(anchor="w", padx=20, pady=(16, 2))
        hint = tk.Label(win, text="", bg=PAPER, fg=SOFT, font=self.f_meta,
                        justify="left")
        hint.pack(anchor="w", padx=20, pady=(0, 10))
        row = tk.Frame(win, bg=PAPER)
        row.pack(fill="x", padx=20)

        def col(title, width, pad):
            c = tk.Frame(row, bg=PAPER)
            c.pack(side="left", padx=pad, fill="x" if width is None else None,
                   expand=width is None)
            tk.Label(c, text=title, bg=PAPER, fg=FAINT, font=self.f_label,
                     anchor="w").pack(fill="x", pady=(0, 2))
            return c

        v_kind = tk.StringVar(value="person")
        kb = ttk.Combobox(col("TIPO", 10, 0), textvariable=v_kind, state="readonly",
                          values=["person", "form", "concept", "source"], width=10,
                          font=self.f_meta)
        kb.pack()
        v_lang = tk.StringVar(value="")
        lang_box = ttk.Combobox(col("LÍNGUA", 12, (14, 0)), textvariable=v_lang,
                                values=self.known_langs(), width=12, font=self.f_meta)
        lang_box.pack()
        e_source = tk.Entry(col("FONTE", None, (14, 0)), font=self.f_meta, bg=PAPER,
                            fg=INK, insertbackground=INK, relief="flat",
                            highlightthickness=1, highlightbackground=RULE,
                            highlightcolor=STAMP)
        e_source.pack(fill="x", ipady=2)

        def toggle(*_a):
            k = v_kind.get()
            lang_box.configure(state="normal" if k == "form" else "disabled")
            e_source.configure(state="normal" if k != "person" else "disabled")
            hint.configure(text={"person": "Uma por linha:  - Nome. Notas sobre a pessoa.",
                                 "source": "Uma referência por linha, como você a escreveria "
                                           "(SOBRENOME, Nome. Título. Local: Editora, ano)."
                                 }.get(k, "Uma por linha:  nome. glosa"))

        v_kind.trace_add("write", toggle)
        toggle()
        tk.Label(win, text="", bg=PAPER).pack(pady=2)
        box = tk.Text(win, height=10, font=self.f_meta, bg=SHELL, fg=INK,
                      insertbackground=INK, relief="flat", wrap="word",
                      highlightthickness=1, highlightbackground=RULE,
                      highlightcolor=STAMP, padx=8, pady=6, undo=True)
        self.bind_undo(box, text=True)
        box.pack(fill="both", expand=True, padx=20)

        def add():
            kind = v_kind.get()
            text = box.get("1.0", "end-1c")
            if not text.strip():
                win.destroy()
                return
            if kind == "person":
                if not text.lstrip().startswith(("- ", "* ", "## ")):
                    text = "\n".join("- " + l.strip() for l in text.splitlines()
                                     if l.strip())
                data = load_json()
                added, merged, identical, names = ingest(text, data)
                write_json(data)
                self.safe_mirror(data)
                win.destroy()
                self.reload()
                bits = []
                if added:
                    bits.append(f"{added} adicionadas")
                if merged:
                    bits.append(f"{merged} receberam addendum: "
                                + ", ".join(one_liner(n, 28) for n in names[:3]))
                if identical:
                    bits.append(f"{identical} já constavam")
                self.say(" · ".join(bits) or "Nada a adicionar.")
                return
            if kind == "source":
                items = [source_from_raw(l) for l in text.splitlines() if l.strip()]
                data = load_json()
                added, skipped = import_sources(items, data)
                write_json(data)
                self.safe_mirror(data)
                win.destroy()
                self.reload()
                self.say(f"{added} fonte(s) adicionadas, {skipped} já existiam.")
                return
            lang = v_lang.get().strip()
            src = e_source.get().strip()
            if kind == "form" and not lang:
                hint.configure(text="Uma forma precisa de língua.")
                return
            data = load_json()
            taken = set(by_id(data))
            feitos = 0
            for line in text.splitlines():
                line = line.strip()
                if line[:2] in ("- ", "* "):
                    line = line[2:].strip()
                if not line:
                    continue
                name, gloss = (line.split(". ", 1) if ". " in line else (line, ""))
                name, gloss = name.strip(), gloss.strip()
                if not name:
                    continue
                eid = new_id(kind, name, taken)
                taken.add(eid)
                rec = fix_entry({"id": eid, "kind": kind, "name": name, "gloss": gloss,
                                 "source": src})
                if kind == "form":
                    rec.update({"lang": lang,
                                "status": "reconstructed" if name.startswith("*")
                                else "attested"})
                touch(rec)
                data["entries"].append(rec)
                log_put("entries", rec)
                feitos += 1
            if feitos:
                write_json(data)
                self.safe_mirror(data)
            win.destroy()
            self.reload()
            self.say(f"{feitos} verbete(s) adicionados."
                     + (" Conceitos sem glosa aparecem em Verificar estrutura."
                        if kind == "concept" and feitos else ""))

        foot = tk.Frame(win, bg=PAPER)
        foot.pack(fill="x", padx=20, pady=14)
        ttk.Button(foot, text="Adicionar", command=add).pack(side="left")
        ttk.Button(foot, text="Cancelar", style="Quiet.TButton",
                   command=win.destroy).pack(side="left", padx=(8, 0))
        win.bind("<Escape>", lambda e: win.destroy())
        box.focus_set()

    # ------------------------------------------------------------ base
    def safe_mirror(self, data):
        try:
            write_mirror(data)
        except SystemExit as exc:
            self.notify("Espelho não refeito", str(exc))
        try:
            write_corpus_html(data)
        except OSError:
            pass

    def do_corpus(self):
        self.commit_if_dirty()
        import io
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_corpus(open_it=True)
        self.say(f"Mapa do corpo refeito e aberto: {CORPUS_HTML_FILE.name}")

    def do_mirror(self):
        self.commit_if_dirty()
        self.safe_mirror(load_json())
        self.say(f"Espelho refeito: {MIRROR_FILE.name}")

    def do_doctor(self):
        self.commit_if_dirty()
        errors, warnings = check(self.data)
        body = summary(self.data) + f"\n{len(errors)} erros, {len(warnings)} avisos.\n\n"
        body += "\n".join(errors[:20]) if errors else "Nenhum erro de estrutura."
        if warnings:
            body += "\n\n" + "\n".join(warnings[:20])
        others = other_locks()
        if others:
            body += "\n\nAberto também em: " + ", ".join(
                f"{o.get('host')} desde {o.get('since')}" for o in others)
        self.show_text("Estrutura", body)

    def do_normalize(self):
        self.commit_if_dirty()
        if not self.confirm("Normalizar tags inline",
                            "Mover #hashtags e datas escritas nos nomes e notas das "
                            "pessoas para o campo de tags?", yes="Normalizar"):
            return
        import io
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_normalize()
        self.reload()
        self.say("Normalizado.")

    def do_merge(self):
        self.commit_if_dirty()
        reports = absorb_conflicts()
        if not reports:
            self.say("Nenhum arquivo de conflito na pasta.")
            return
        self.safe_mirror(load_json())
        self.reload()
        body = []
        for name, r in reports:
            body.append(name)
            for coll, rid, nm in r["added"]:
                body.append(f"  + {nm}  ({rid})")
            for coll, rid, nm in r["replaced"]:
                body.append(f"  ~ {nm}  ({rid})")
            for coll, rid, nm in r["skipped_deleted"]:
                body.append(f"  - {nm}  ({rid}, apagado)")
            body.append(f"  {r['kept']} mantidos\n")
        self.show_text("Conflitos absorvidos", "\n".join(body))

    def do_history(self):
        rec = self.current()
        if not rec or rec["id"].startswith("__"):
            self.say("Abra um registro salvo primeiro.")
            return
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_history(rec["id"])
        self.show_text(f"Histórico · {label_any(rec)}", buf.getvalue())

    def do_import_zotero(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Export do Zotero (CSL-JSON ou BibTeX)",
            filetypes=[("CSL-JSON / BibTeX", "*.json *.bib"), ("Todos", "*.*")])
        if not path:
            return
        import io
        import contextlib
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                cmd_import_zotero(path)
        except (SystemExit, ValueError, json.JSONDecodeError) as exc:
            self.notify("Importação", str(exc))
            return
        self.reload()
        self.say(buf.getvalue().strip())

    def do_export(self, fmt):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_export(fmt)
        self.say(buf.getvalue().strip() + f"  (em {BASE})")

    def card_layout_dialog(self):
        win = self.dialog("Campos do verbete", 460, 480)
        tk.Label(win, text="CAMPOS DO VERBETE", bg=PAPER, fg=FAINT,
                 font=self.f_label).pack(anchor="w", padx=18, pady=(16, 2))
        tk.Label(win, text="Espaço mostra ou esconde. As setas movem.",
                 bg=PAPER, fg=SOFT, font=self.f_meta).pack(anchor="w", padx=18,
                                                          pady=(0, 8))
        box = tk.Listbox(win, height=11, font=self.f_meta, bg=PAPER, fg=INK,
                         relief="flat", highlightthickness=0, selectbackground=SELBG,
                         selectforeground=SELFG, activestyle="none")
        box.pack(fill="both", expand=True, padx=18)
        work = list(self.vc.layout)

        def redraw(keep=0):
            box.delete(0, "end")
            for fid, on in work:
                box.insert("end", f"[{'x' if on else ' '}]  {FIELD_TITLE[fid]}")
            if work:
                box.selection_clear(0, "end")
                box.selection_set(min(keep, len(work) - 1))
                box.activate(min(keep, len(work) - 1))

        def move(step):
            sel = box.curselection()
            if not sel:
                return "break"
            i = sel[0]
            j = i + step
            if 0 <= j < len(work):
                work[i], work[j] = work[j], work[i]
                redraw(j)
            return "break"

        def toggle(_e=None):
            sel = box.curselection()
            if not sel:
                return "break"
            i = sel[0]
            work[i] = (work[i][0], not work[i][1])
            redraw(i)
            return "break"

        box.bind("<space>", toggle)
        box.bind("<Double-Button-1>", toggle)
        row = tk.Frame(win, bg=PAPER)
        row.pack(fill="x", padx=18, pady=12)
        ttk.Button(row, text="↑", width=3, command=lambda: move(-1)).pack(side="left")
        ttk.Button(row, text="↓", width=3, command=lambda: move(1)).pack(side="left",
                                                                        padx=(4, 0))
        ttk.Button(row, text="mostrar / ocultar", style="Quiet.TButton",
                   command=toggle).pack(side="left", padx=(10, 0))

        def restore():
            work[:] = [(f, True) for f in FIELD_IDS]
            redraw(0)

        def apply_now():
            self.vc.layout = list(work)
            self.data = save_ui({"card_fields": [{"id": f, "on": on} for f, on in work]})
            self.vc.apply_layout()
            win.destroy()
            self.say("Campos reorganizados.")

        row2 = tk.Frame(win, bg=PAPER)
        row2.pack(fill="x", padx=18, pady=(0, 14))
        ttk.Button(row2, text="Usar", command=apply_now).pack(side="left")
        ttk.Button(row2, text="Padrão", style="Quiet.TButton",
                   command=restore).pack(side="left", padx=(8, 0))
        ttk.Button(row2, text="Cancelar", style="Quiet.TButton",
                   command=win.destroy).pack(side="left", padx=(8, 0))
        win.bind("<Escape>", lambda e: win.destroy())
        redraw(0)
        box.focus_set()

    def choose_typeface(self):
        fams = self.mono_families()
        win = self.dialog("Tipo de letra do terminal", 420, 460)
        tk.Label(win, text="TIPO DE LETRA DO TERMINAL", bg=PAPER, fg=FAINT,
                 font=self.f_label).pack(anchor="w", padx=18, pady=(14, 2))
        tk.Label(win, text="Só faces monoespaçadas: qualquer outra desalinha\n"
                           "as colunas e o cursor em bloco.",
                 bg=PAPER, fg=SOFT, font=self.f_meta, justify="left"
                 ).pack(anchor="w", padx=18, pady=(0, 8))
        box = tk.Listbox(win, height=12, width=34, font=self.f_meta, bg=PAPER, fg=INK,
                         relief="flat", highlightthickness=0, selectbackground=SELBG,
                         selectforeground=SELFG, activestyle="none")
        box.pack(fill="both", expand=True, padx=18)
        box.insert("end", "(padrão)")
        for fam in fams:
            box.insert("end", fam)
        current = (self.data.get("ui") or {}).get("font_mono")
        if current in fams:
            idx = fams.index(current) + 1
            box.selection_set(idx)
            box.see(idx)
        else:
            box.selection_set(0)
        row = tk.Frame(win, bg=PAPER)
        row.pack(fill="x", padx=18, pady=12)

        def apply():
            sel = box.curselection()
            pick = None if not sel or sel[0] == 0 else fams[sel[0] - 1]
            save_ui({"font_mono": pick})
            win.destroy()
            self.commit_if_dirty()
            self.restart_theme = self.theme
            self.stop_carets()
            self.root.destroy()

        ttk.Button(row, text="Usar", command=apply).pack(side="left")
        ttk.Button(row, text="Cancelar", style="Quiet.TButton",
                   command=win.destroy).pack(side="left", padx=(8, 0))
        win.bind("<Escape>", lambda e: win.destroy())

    def switch_theme(self, key):
        if key == self.theme:
            return
        self.commit_if_dirty()
        save_ui({"theme": key})
        self.restart_theme = key
        self.stop_carets()
        self.root.destroy()

    def do_help(self):
        self.show_text("Atalhos",
                       "\n  Ctrl+F     ir para a busca"
                       "\n  ↓ / Enter  da busca para a lista"
                       "\n  Ctrl+N     nova pessoa"
                       "\n  Ctrl+Q     entrada rápida (pessoas, formas ou conceitos)"
                       "\n  Ctrl+S     salvar o registro aberto"
                       "\n  Ctrl+Enter salvar e começar outro do mesmo tipo"
                       "\n  Ctrl+Z / Ctrl+Y   desfazer / refazer"
                       "\n  Ctrl+J / Ctrl+K   próximo / anterior, de qualquer lugar"
                       "\n  Ctrl+G     ir para: nº (1852), folha (fl 37), carimbo, id ou nome"
                       "\n  Ctrl+L     ver no livro: sai da busca, abre a folha do registro"
                       "\n  Ctrl+1..4  escopo pessoas / verba / fontes / corpus; Ctrl+0 tudo"
                       "\n  /  na lista volta à busca;  Enter na lista vai ao cartão"
                       "\n  Home / End na folha;  PageUp / PageDown vira a folha"
                       "\n  Ctrl+PageUp / Ctrl+PageDown vira a folha de qualquer lugar"
                       "\n  F5         recarregar do disco"
                       "\n  Esc        voltar à lista\n"
                       f"\n  LIVRO {BOOK}: todo registro recebe, ao ser gravado pela"
                       "\n  primeira vez, um carimbo (AAAAMMDDhhmmss) e um número de"
                       f"\n  ordem. Cada folha tem {FOLHA} números; cada volume,"
                       f"\n  {FOLHAS_POR_LIVRO} folhas. O número nunca muda: o que é apagado"
                       "\n  fica na folha como cancelado. Sem busca, a lista é o livro;"
                       "\n  com busca ou filtro, é o INDICADOR, em ordem alfabética,"
                       "\n  com o endereço de cada registro.\n"
                       "\n  Operadores da busca:"
                       "\n  p: v: f: c:   só pessoas / verba / fontes / corpus"
                       "\n  ^ab           nome que começa com ab"
                       "\n  tag:csh  lang:de  type:livro  sys:renal  dom:direito  id:c_"
                       "\n  ex.:  v: lang:de ^ab   ·   f: type:artigo luhmann\n"
                       "\n  Campos de texto crescem até 10 linhas e depois rolam por"
                       "\n  dentro (ui.max_rows no JSON muda o teto). O mapa do corpo"
                       "\n  recolhe pelo [−] e lembra o estado.\n"
                       "\n  No trilho, ACERVO limita a pessoas ou a verba;"
                       "\n  qualquer filtro abaixo escolhe o acervo sozinho.\n"
                       "\n  Tarefas (pessoas):"
                       "\n  Enter       nova linha já com [ ]"
                       "\n  Espaço      sobre o [ ] muda o estado"
                       "\n  Ctrl+Espaço muda de qualquer ponto da linha"
                       "\n  [ ] a fazer  [/] em curso  [>] esperando"
                       "\n  [x] feito    [-] cancelado  (vão para o log ao salvar)"
                       "\n  Data no fim é o prazo: 2026-09-10, 2026-09-10-1000,"
                       "\n  ~2026-09-10 10:00. A ÚLTIMA data da linha vence.\n"
                       "\n  Ligações, uma por linha, em qualquer cartão:"
                       "\n  rel alvo [intervalo] — razão # fonte"
                       "\n  ex.: expresses c_timoneiro -800/400 — sentido próprio"
                       "\n  ex.: author_of s_wiener_1948_cybernetics"
                       "\n  ex.: cites s_lochtrop_2006 — verbete p. 12"
                       "\n  Alvo é o id: c_ conceito, f_ forma, p_ pessoa,"
                       "\n  s_ fonte, h_ medida. Um rel fora da tabela não é"
                       "\n  erro: é ligação ATÍPICA, com o rótulo que você deu;"
                       "\n  o doctor lista as atípicas para você promover.\n"
                       "\n  FONTE (em pessoas, verbetes e medidas): s_… de uma"
                       "\n  fonte, ou texto livre. Fontes citam em ABNT, autor-data,"
                       "\n  BibTeX ou CSL-JSON (seletor no cartão, botão copiar)."
                       "\n  Corpus: leituras '2026-09-01 13.5 jejum', uma por linha;"
                       "\n  fora da referência aparece com (!).\n"
                       "\n  Sincronização: cada gravação relê o disco; ao abrir,"
                       "\n  *.sync-conflict-* são fundidos e guardados em"
                       f"\n  {CONFLICT_DIR.name}/. O histórico completo está em"
                       f"\n  {STEM}.log.<máquina>.jsonl (menu Base › Histórico).\n")

    # ------------------------------------------------------------ diálogos
    def dialog(self, title, width=520, height=None):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=PAPER)
        win.transient(self.root)
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + 120
        win.geometry(f"{width}x{height or 200}+{max(0, x)}+{max(0, y)}")
        paint_frame(win)
        return win

    def confirm(self, title, message, yes="Sim", no="Cancelar"):
        win = self.dialog(title, 560, 230)
        answer = {"v": False}
        tk.Label(win, text=title, bg=PAPER, fg=INK,
                 font=(self.f_body[0], 14)).pack(anchor="w", padx=20, pady=(18, 6))
        tk.Label(win, text=message, bg=PAPER, fg=SOFT, font=self.f_meta,
                 justify="left", wraplength=510).pack(anchor="w", padx=20)
        row = tk.Frame(win, bg=PAPER)
        row.pack(fill="x", side="bottom", padx=20, pady=16)

        def close(value):
            answer["v"] = value
            win.destroy()

        ttk.Button(row, text=yes, command=lambda: close(True)).pack(side="left")
        ttk.Button(row, text=no, style="Quiet.TButton",
                   command=lambda: close(False)).pack(side="left", padx=10)
        win.bind("<Escape>", lambda e: close(False))
        win.bind("<Return>", lambda e: close(True))
        win.grab_set()
        win.focus_set()
        self.root.wait_window(win)
        return answer["v"]

    def notify(self, title, message):
        win = self.dialog(title, 560, 220)
        tk.Label(win, text=title, bg=PAPER, fg=OXIDE,
                 font=(self.f_body[0], 14)).pack(anchor="w", padx=20, pady=(18, 6))
        tk.Label(win, text=message, bg=PAPER, fg=INK, font=self.f_meta,
                 justify="left", wraplength=510).pack(anchor="w", padx=20)
        ttk.Button(win, text="OK", command=win.destroy).pack(side="bottom", anchor="w",
                                                             padx=20, pady=16)
        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<Return>", lambda e: win.destroy())
        win.grab_set()
        win.focus_set()
        self.root.wait_window(win)

    def show_text(self, title, body):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=PAPER)
        win.geometry("700x480")
        win.transient(self.root)
        paint_frame(win)
        t = tk.Text(win, font=self.f_meta, bg=PAPER, fg=INK, relief="flat",
                    wrap="word", padx=16, pady=14)
        t.pack(fill="both", expand=True)
        t.insert("1.0", body)
        t.configure(state="disabled")
        win.bind("<Escape>", lambda e: win.destroy())

    def on_close(self):
        self.commit_if_dirty()
        self.stop_carets()
        self.root.destroy()


# ================================================================ app

def cmd_app(open_id=None):
    global tk, tkfont, ttk
    try:
        import tkinter as _tk
        from tkinter import font as _tkfont, ttk as _ttk
    except ImportError:
        raise SystemExit("Este Python veio sem Tkinter. Reinstale marcando tcl/tk.")
    tk, tkfont, ttk = _tk, _tkfont, _ttk

    notices = []
    if JSON_FILE.exists() and needs_upgrade(load_json()):
        old = load_json()
        n_before = len(old.get("sources", []))
        opening = cmd_upgrade(quiet=True)
        n_after = len(load_json()["sources"])
        if schema_version(old) < 3:
            notices.append(f"Base atualizada para {SCHEMA}: {n_after - n_before} "
                           "fonte(s) criadas a partir do campo FONTE.")
        if opening:
            notices.append(opening)
    if (CORPUS_SUBJECT and JSON_FILE.exists()
            and not (load_json().get("ui") or {}).get("corpus_subject")):
        save_ui({"corpus_subject": CORPUS_SUBJECT})
    reports = absorb_conflicts()
    if reports:
        notices.append("Conflitos absorvidos: " + describe_merge(reports))
        try:
            write_mirror(load_json())
        except SystemExit:
            pass
    for o in other_locks():
        notices.append(f"Aberto também em {o.get('host')} desde {o.get('since')}: "
                       "editar nas duas máquinas ao mesmo tempo gera conflito.")
    take_lock()

    theme = (load_json().get("ui") or {}).get("theme", "paper")
    first = open_id
    try:
        while True:
            load_palette(theme)
            root = tk.Tk()
            ui = App(root, theme, notices)
            notices = []
            if first:
                def jump(u=ui, rid=first):
                    try:
                        if rid in by_id(u.data):
                            u.open_record(rid)
                        else:
                            u.say(f"O registro {rid} não existe.")
                    except Exception:
                        pass
                root.after(260, jump)
                first = None
            root.protocol("WM_DELETE_WINDOW", ui.on_close)
            root.mainloop()
            if not ui.restart_theme:
                break
            theme = ui.restart_theme
    finally:
        drop_lock()
    return 0


def main():
    args = sys.argv[1:]
    if not args:
        return cmd_app()
    cmd, rest = args[0], args[1:]
    if cmd == "app":
        return cmd_app(rest[0] if rest else None)
    if cmd == "migrate":
        return cmd_migrate()
    if cmd == "merge":
        return cmd_merge()
    if cmd == "doctor":
        return cmd_doctor()
    if cmd == "mirror":
        cmd_mirror()
        write_corpus_html(load_json())
        return 0
    if cmd == "corpus":
        return cmd_corpus(open_it="--no-open" not in rest)
    if cmd == "search" and rest:
        return cmd_search(" ".join(rest))
    if cmd == "history" and rest:
        return cmd_history(rest[0])
    if cmd == "replay":
        return cmd_replay()
    if cmd == "import" and rest:
        if rest[0] == "zotero" and len(rest) > 1:
            return cmd_import_zotero(rest[1])
        return cmd_import(rest[0])
    if cmd == "normalize":
        return cmd_normalize()
    if cmd == "upgrade":
        cmd_upgrade()
        return 0
    if cmd == "cite" and rest:
        return cmd_cite(rest[0], rest[1] if len(rest) > 1 else "abnt")
    if cmd == "export":
        return cmd_export(rest[0] if rest else "bibtex", rest[1] if len(rest) > 1 else None)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
