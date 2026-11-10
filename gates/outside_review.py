"""G2R and G5R: the ChatGPT outside reviews OR1 and OR2 (Version 3; docs/outside-review.md).

OR1 runs after G2 (question lock checks) and before the owner approves the locked question. OR2 runs at Stage 5 after
the draft finish; G5R runs after G5 and before the owner approves the finish package. ChatGPT never writes code, never
sees the answer key and never votes: its issues are advice that the Grok side must answer, one disposition per issue.

Inputs (project-relative; <OR> is OR1 or OR2):
  artifacts/outside_review/<OR>.json  {review, reviewer: "chatgpt", packet_id, status: done|skipped,
        attempts: [{at, outcome: answered|usage_limit}], reply {path, sha256} (done),
        dispositions {path, sha256} (done), card {path, sha256}, skip_log (skipped)}
  the packet and its reply, listed in artifacts/packets/index.json (ROLE outside-reviewer)
  artifacts/outside_review/<OR>/inputs/<original path>  frozen copies of exactly what the outside reviewer saw
  dispositions JSON {review, reply {path, sha256}, dispositions: [{issue, severity, status: fixed|not_fixed,
        where + files [{path, sha256}] (fixed) | reason (not_fixed), decided_by}]}
  the owner card (Markdown shown on the lock / finish card)

Checks:
- the base gate (G2 for OR1, G5 for OR2) is PASS and current;
- the OR packet passes every G0 packet check, carries ROLE outside-reviewer and the right STAGE, states the rules
  "do not write code" and "do not vote", and every input is a frozen copy under the OR inputs folder;
- OR1 carries the brief, the proposed locked question and its terms only: no data and no data structure (no data or
  code file types, nothing named like feasibility/schema/snapshot/source gates, nothing from Stage 2F/3/4/5);
- OR2 carries the locked question, the claims ledger, at least one of its deliverables (draft recommendation) and
  only evidence the ledger cites (official numbers), each copy with the hash the ledger records; no code, no raw data;
- done: the last attempt answered, at most 3 retries 5+ minutes apart before it; the reply is the one sealed in the
  packet index, ends with ANSWERED, issues well-formed, no code; every issue has exactly one disposition with the
  same severity; fixed names where and the fixed files, each current and sealed by the current base gate (an input of
  its record or a reviewed subject in one of its review records); not fixed gives a reason; decided_by is a Grok role;
- skipped: the first send plus 3 retries, all usage-limited, each 5+ minutes after the last; skip_log says OR-SKIPPED;
  the packet index marks the packet skipped;
- the owner card lists exactly the unresolved blocking issues (`UNRESOLVED BLOCKING <OR>-<n>: ...`, or
  `UNRESOLVED BLOCKING: none`) and, when skipped, a line `OR-SKIPPED <OR>: ...`.
"""
from __future__ import annotations

import datetime
import os
import re

from gates import packet as PK
from gates.common import (Gate, PLACEHOLDER_RE, TIMESTAMP_RE, gate_record_current, load_json_strict, ref_current, safe_rel,
                          text)
from gates.or_format import (OUTSIDE_ROLE, RETRIES, RETRY_GAP_SECONDS, REVIEWS, SKIP_MARKER, card_says_none,
                             card_says_skipped, card_unresolved, has_code, parse_issues)

OR_DIR = "artifacts/outside_review"
GROK_ROLES = {"parent", "lead-designer", "second-designer", "risk-reviewer", "sql-analyst", "analyst-r-a", "analyst-r-b"}
FRAMING = "artifacts/stage2_framing.json"
REQUIRED_RULES = ("do not write code", "do not vote")
DATA_EXT = {".csv", ".tsv", ".parquet", ".sqlite", ".sqlite3", ".db", ".xlsx", ".xls", ".feather", ".arrow", ".rds", ".rda",
            ".rdata", ".jsonl", ".ndjson", ".sav", ".dta", ".zip", ".gz", ".tar"}
RAW_DATA_EXT = {".sqlite", ".sqlite3", ".db", ".parquet", ".feather", ".arrow", ".zip", ".gz", ".tar", ".xlsx", ".xls"}
CODE_EXT = {".r", ".sql", ".py", ".rmd", ".qmd", ".ipynb", ".sh", ".js", ".ts"}
OR1_PREFIXES = ("brief/", "docs/stage1/", "docs/stage2/")
OR1_FILES = ("artifacts/stage1_decision.json", FRAMING)
DATA_STRUCTURE_NAME = re.compile(r"feasib|schema|snapshot|source[_ -]?gate|data[_ -]?dictionary|columns|stage2f", re.IGNORECASE)
CLAIMS_NAME = re.compile(r"^artifacts/stage5_claims[^/]*\.json$")


def _plain(root, rel):
    full = safe_rel(root, rel)
    if full is None:
        return None
    obj, err = load_json_strict(full)
    return obj if err is None else None


def _read(root, rel):
    try:
        with open(safe_rel(root, rel), "rb") as fh:
            return fh.read().decode("utf-8")
    except (OSError, TypeError, UnicodeDecodeError):
        return None


def _ext(p):
    return os.path.splitext(p)[1].lower()


def _ts(s):
    if not isinstance(s, str) or not TIMESTAMP_RE.match(s):
        return None
    try:
        t = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else None


def gate_sealed_set(root, gid):
    """{path: sha256} a current PASS record of `gid` seals: its inputs, and the subjects of review records among them."""
    ok, _, _ = gate_record_current(root, gid)
    if not ok:
        return {}
    rec = _plain(root, f"artifacts/gates/{gid}.json") or {}
    out = {}
    for i in rec.get("inputs", []):
        if isinstance(i, dict) and text(i.get("path")) and isinstance(i.get("sha256"), str):
            out[i["path"]] = i["sha256"].lower()
            rv = _plain(root, i["path"]) if i["path"].endswith(".json") else None
            if isinstance(rv, dict) and text(rv.get("role")) and isinstance(rv.get("subjects"), list):
                for s in rv["subjects"]:
                    if isinstance(s, dict) and text(s.get("path")) and isinstance(s.get("sha256"), str):
                        out.setdefault(s["path"], s["sha256"].lower())
    return out


def _input_checks(g, root, review, parsed):
    """What the outside reviewer saw: frozen copies only; OR1 no data/structure; OR2 only the ledger's material."""
    mirror = f"{OR_DIR}/{review}/inputs/"
    refs = []
    for line in parsed.get("INPUTS") or []:
        m = PK.INPUT_RE.match(line)
        if m:
            refs.append((m.group("path"), m.group("sha").lower()))
    not_frozen = [p for p, _ in refs if not p.startswith(mirror)]
    g.add(f"{review} inputs are frozen copies", bool(refs) and not not_frozen,
          f"every input under {mirror}<original path>" + (f"; not frozen: {not_frozen}" if not_frozen else ""))
    orig = {p[len(mirror):]: (p, sha) for p, sha in refs if p.startswith(mirror)}
    code = [o for o in orig if _ext(o) in CODE_EXT]
    g.add(f"{review} no code inputs", not code, f"code files: {code}" if code else "none")
    if review == "OR1":
        bad = [o for o in orig if _ext(o) in DATA_EXT or DATA_STRUCTURE_NAME.search(o)
               or not (o in OR1_FILES or o.startswith(OR1_PREFIXES))]
        g.add("OR1 carries no data or data structure", bool(orig) and not bad,
              f"only {list(OR1_FILES)} and files under {list(OR1_PREFIXES)}; no data, schema, feasibility or snapshot"
              + (f"; not allowed: {bad}" if bad else ""))
        g.add("OR1 carries the brief and the proposed locked question", FRAMING in orig and any(o.startswith("brief/") for o in orig),
              f"inputs must include {FRAMING} and the brief under brief/")
        return
    ledgers = [o for o in orig if CLAIMS_NAME.match(o)]
    g.add("OR2 carries the claims ledger", len(ledgers) == 1, f"exactly one artifacts/stage5_claims*.json; got {ledgers}")
    led = _plain(root, orig[ledgers[0]][0]) if len(ledgers) == 1 else None
    led = led if isinstance(led, dict) else {}
    want = {}
    for d in led.get("deliverables", []) if isinstance(led.get("deliverables"), list) else []:
        if isinstance(d, dict) and text(d.get("path")):
            want[d["path"]] = ("deliverable", str(d.get("sha256")).lower())
    for c in led.get("claims", []) if isinstance(led.get("claims"), list) else []:
        for e in (c.get("evidence") if isinstance(c, dict) and isinstance(c.get("evidence"), list) else []):
            if isinstance(e, dict) and text(e.get("path")):
                want.setdefault(e["path"], ("evidence", str(e.get("sha256")).lower()))
    bad, wrong_hash = [], []
    for o, (_, sha) in orig.items():
        if o in ledgers or o == FRAMING or o.startswith("docs/stage2/"):
            continue
        if o not in want or o.startswith("data/") or _ext(o) in RAW_DATA_EXT:
            bad.append(o)
        elif want[o][1] != sha:
            wrong_hash.append(o)
    g.add("OR2 carries only the question, claims, draft recommendation and cited numbers", bool(orig) and not bad,
          "inputs: the locked question, the claims ledger, its deliverables and the evidence its claims cite; no raw data"
          + (f"; not allowed: {bad}" if bad else ""))
    g.add("OR2 copies match the claims ledger", not wrong_hash, f"hash differs from the ledger: {wrong_hash}" if wrong_hash else "ok")
    g.add("OR2 carries the locked question and a draft recommendation", FRAMING in orig and any(want.get(o, ("",))[0] == "deliverable" for o in orig),
          f"inputs must include {FRAMING} and at least one ledger deliverable")


def _attempt_checks(g, review, rec, status):
    at = rec.get("attempts")
    at = at if isinstance(at, list) else []
    ok_shape = bool(at) and all(isinstance(a, dict) and a.get("outcome") in ("answered", "usage_limit") and _ts(a.get("at")) for a in at)
    g.add(f"{review} attempts logged", ok_shape, "attempts: [{at (timestamp with zone), outcome answered|usage_limit}]")
    if not ok_shape:
        return
    times = [_ts(a["at"]) for a in at]
    gaps_ok = all((b - a).total_seconds() >= RETRY_GAP_SECONDS for a, b in zip(times, times[1:]))
    outs = [a["outcome"] for a in at]
    if status == "done":
        g.add(f"{review} answered within the retry limit",
              outs[-1] == "answered" and all(o == "usage_limit" for o in outs[:-1]) and len(outs) <= 1 + RETRIES and gaps_ok,
              f"last attempt answered; at most {RETRIES} retries, each {RETRY_GAP_SECONDS // 60}+ minutes after the last; got {outs}")
    else:
        g.add(f"{review} skipped only after {RETRIES} retries on a usage limit",
              len(outs) == 1 + RETRIES and all(o == "usage_limit" for o in outs) and gaps_ok,
              f"first send + {RETRIES} retries, all usage_limit, {RETRY_GAP_SECONDS // 60}+ minutes apart; got {outs}")
        g.add(f"{review} logged {SKIP_MARKER}", isinstance(rec.get("skip_log"), str) and SKIP_MARKER in rec["skip_log"],
              f"skip_log must say {SKIP_MARKER}")


def _disposition_checks(g, root, review, rec, issues, base_gate):
    dref = rec.get("dispositions")
    ok = ref_current(root, dref)
    g.add(f"{review} dispositions sealed", ok, "dispositions {path, sha256} current")
    if not ok:
        return []
    g.use(dref["path"])
    d = _plain(root, dref["path"]) or {}
    g.add(f"{review} dispositions answer this reply", d.get("review") == review and isinstance(d.get("reply"), dict)
          and d["reply"].get("path") == (rec.get("reply") or {}).get("path")
          and str(d["reply"].get("sha256")).lower() == str((rec.get("reply") or {}).get("sha256")).lower(),
          "dispositions.review and dispositions.reply must equal the sealed reply")
    rows = d.get("dispositions") if isinstance(d.get("dispositions"), list) else []
    by = {}
    for r in rows:
        if isinstance(r, dict) and isinstance(r.get("issue"), int):
            by.setdefault(r["issue"], []).append(r)
    nums = [i["n"] for i in issues]
    missing = [n for n in nums if n not in by]
    dup = [n for n, v in by.items() if len(v) > 1]
    extra = [n for n in by if n not in nums]
    g.add(f"{review} every issue has a disposition", not missing and not dup and not extra
          and all(isinstance(r, dict) and isinstance(r.get("issue"), int) for r in rows),
          "exactly one disposition per issue" + (f"; missing {missing}" if missing else "") + (f"; duplicate {dup}" if dup else "")
          + (f"; no such issue {extra}" if extra else ""))
    sealed = gate_sealed_set(root, base_gate)
    sev_bad, shape_bad, unsealed, voters = [], [], [], []
    unresolved = []
    for i in issues:
        r = (by.get(i["n"]) or [None])[0]
        if not isinstance(r, dict):
            continue
        if r.get("severity") != i["severity"]:
            sev_bad.append(i["n"])
        if r.get("decided_by") not in GROK_ROLES:
            voters.append(i["n"])
        st = r.get("status")
        if st == "fixed":
            files = r.get("files") if isinstance(r.get("files"), list) else []
            if not (text(r.get("where")) and not PLACEHOLDER_RE.search(r["where"]) and files):
                shape_bad.append(i["n"])
            for f in files:
                if not (isinstance(f, dict) and ref_current(root, f) and sealed.get(f.get("path")) == str(f.get("sha256")).lower()):
                    unsealed.append(f"{i['n']}:{f.get('path') if isinstance(f, dict) else f}")
                elif isinstance(f, dict):
                    g.use(f["path"])
        elif st == "not_fixed":
            if not (text(r.get("reason")) and not PLACEHOLDER_RE.search(r["reason"])):
                shape_bad.append(i["n"])
            if i["severity"] == "blocking":
                unresolved.append(i["n"])
        else:
            shape_bad.append(i["n"])
    g.add(f"{review} disposition severity matches the reply", not sev_bad, f"differs on issues {sev_bad}" if sev_bad else "ok")
    g.add(f"{review} dispositions fixed (where) or not fixed (reason)", not shape_bad,
          "fixed: where + files [{path, sha256}]; not_fixed: reason" + (f"; malformed: {shape_bad}" if shape_bad else ""))
    g.add(f"{review} fixes sealed by the current {base_gate}", not unsealed,
          f"each fixed file current and an input (or reviewed subject) of the current {base_gate} record"
          + (f"; not sealed: {unsealed}" if unsealed else ""))
    g.add(f"{review} decided by the Grok side", not voters,
          "decided_by must be a Grok role; the outside reviewer never votes" + (f"; issues {voters}" if voters else ""))
    return unresolved


def or_gate(gate_id, root):
    review = next(k for k, v in REVIEWS.items() if v["gate"] == gate_id)
    spec = REVIEWS[review]
    g = Gate(gate_id, root)
    okb, detb, refb = gate_record_current(root, spec["base_gate"])
    g.add(f"{spec['base_gate']} PASS and current", okb, detb)
    if refb:
        g.inputs.append(refb)
    rec = g.load(f"{OR_DIR}/{review}.json", f"{review} record") or {}
    status = rec.get("status")
    g.add(f"{review} record well-formed", rec.get("review") == review and rec.get("reviewer") == "chatgpt"
          and status in ("done", "skipped") and text(rec.get("packet_id")),
          f"review {review}, reviewer chatgpt, status done|skipped, packet_id")
    pid = rec.get("packet_id")
    idx = _plain(root, PK.INDEX) or {}
    rows = [p for p in idx.get("packets", []) if isinstance(p, dict) and p.get("id") == pid] if isinstance(idx.get("packets"), list) else []
    g.add(f"{review} packet listed in the packet index", len(rows) == 1, f"{PK.INDEX} must list packet {pid!r} once")
    unresolved, issues = [], []
    if len(rows) == 1:
        row = rows[0]
        want = "answered" if status == "done" else "skipped"
        g.add(f"{review} packet status {want}", row.get("status") == want, f"index status {row.get('status')!r}")
        sub = Gate("G0", root)
        ids = {p.get("id") for p in idx.get("packets", []) if isinstance(p, dict)}
        fs = [s for s in idx.get("forbidden_strings", []) if text(s)] if isinstance(idx.get("forbidden_strings"), list) else []
        fp = PK.DEFAULT_FORBIDDEN_PREFIXES + ([s for s in idx.get("forbidden_path_prefixes", []) if text(s)]
                                              if isinstance(idx.get("forbidden_path_prefixes"), list) else [])
        PK._check_packet(sub, root, row, ids, fs, fp)
        g.extend(sub.checks, "G0: ")
        for i in sub.inputs:
            if i not in g.inputs:
                g.inputs.append(i)
        body = _read(root, row.get("path")) if text(row.get("path")) else None
        parsed = PK.parse_packet(body) if body else {}
        g.add(f"{review} addressed to the outside reviewer", PK._norm_role((parsed.get("ROLE") or [""])[0]) == OUTSIDE_ROLE
              and (parsed.get("STAGE") or [""])[0].strip() == spec["stage"], f"ROLE {OUTSIDE_ROLE}, STAGE {spec['stage']}")
        rules = " ".join(parsed.get("RULES") or []).lower()
        g.add(f"{review} packet rules: no code, no vote", all(r in rules for r in REQUIRED_RULES),
              f"RULES must state {list(REQUIRED_RULES)}")
        if review == "OR1":
            nats = " ".join(parsed.get("NOT ALLOWED TO SEE") or []).lower()
            g.add("OR1 withholds the data", "data" in nats, "NOT ALLOWED TO SEE must name the data (values and structure)")
        _input_checks(g, root, review, parsed)
        if status == "done":
            same = isinstance(rec.get("reply"), dict) and isinstance(row.get("reply"), dict) \
                and rec["reply"].get("path") == row["reply"].get("path") \
                and str(rec["reply"].get("sha256")).lower() == str(row["reply"].get("sha256")).lower()
            g.add(f"{review} reply is the sealed reply", same and ref_current(root, rec.get("reply")),
                  "record.reply must equal the reply sealed in the packet index, unchanged")
            rbody = _read(root, rec["reply"]["path"]) if same else None
            if rbody is not None:
                issues, errs = parse_issues(rbody)
                g.add(f"{review} reply issues well-formed", not errs, f"{errs}" if errs else f"{len(issues)} issue(s)")
                g.add(f"{review} reply has no code", not has_code(rbody), "no fenced code block")
                issues = [i for i in issues if i["severity"]] if not errs else []
                unresolved = _disposition_checks(g, root, review, rec, issues, spec["base_gate"]) if not errs else []
    if status in ("done", "skipped"):
        _attempt_checks(g, review, rec, status)
    cref = rec.get("card")
    okc = ref_current(root, cref)
    g.add(f"{review} owner card sealed", okc, "card {path, sha256} current")
    if okc:
        g.use(cref["path"])
        ct = _read(root, cref["path"]) or ""
        listed = card_unresolved(ct, review)
        if status == "skipped":
            g.add(f"{review} owner card shows {SKIP_MARKER}", card_says_skipped(ct, review), f"card needs a line `{SKIP_MARKER} {review}: ...`")
        else:
            g.add(f"{review} owner card has no skip line", not card_says_skipped(ct, review), "review was done, not skipped")
        g.add(f"{review} owner card lists every unresolved blocking issue",
              sorted(listed) == sorted(unresolved) and len(listed) == len(set(listed))
              and (bool(listed) or status == "skipped" or card_says_none(ct)),
              f"card must list exactly {sorted(unresolved)} as `UNRESOLVED BLOCKING {review}-<n>: ...`"
              f" (or `UNRESOLVED BLOCKING: none`); card lists {sorted(listed)}")
    g.extra["outside_review"] = {"review": review, "status": status, "packet_id": pid, "issues": len(issues),
                                 "blocking": [i["n"] for i in issues if i["severity"] == "blocking"], "unresolved_blocking": sorted(unresolved)}
    return g.result()


def g2r(root):
    return or_gate("G2R", root)


def g5r(root):
    return or_gate("G5R", root)


GATES = {"G2R": g2r, "G5R": g5r}
