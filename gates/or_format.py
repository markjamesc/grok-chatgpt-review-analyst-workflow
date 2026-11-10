"""Reply format of the ChatGPT outside reviews OR1 and OR2 (Version 3; docs/outside-review.md).

A reply is a numbered list of issues, each with a severity and a proposed fix, and ends with `ANSWERED <PACKET_ID>`:

    1. [blocking] The window end is not stated as inclusive or exclusive.
       Proposed fix: State "through 2026-03-31 inclusive".
    2. [minor] "Active" is not defined.
       Proposed fix: Define active as one or more orders in the window.

    ANSWERED RUN-OR1-01

A reply with nothing to report says `NO ISSUES` on its own line instead of a list. The reply contains no code
(no fenced code block): the outside reviewer never writes code.
"""
from __future__ import annotations

import re

OUTSIDE_ROLE = "outside-reviewer"
SEVERITIES = ("blocking", "minor")
REVIEWS = {"OR1": {"stage": "2", "base_gate": "G2", "gate": "G2R"}, "OR2": {"stage": "5", "base_gate": "G5", "gate": "G5R"}}
RETRIES = 3                 # after the first send: up to 3 retries ...
RETRY_GAP_SECONDS = 300     # ... at least 5 minutes apart; then proceed and log OR-SKIPPED
SKIP_MARKER = "OR-SKIPPED"
CARD_NONE = "UNRESOLVED BLOCKING: none"

NUMBERED_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
ISSUE_RE = re.compile(r"^\[(blocking|minor)\]\s+(\S.*)$", re.IGNORECASE)
FIX_RE = re.compile(r"^\s*proposed fix:\s*(\S.*)?$", re.IGNORECASE)
NO_ISSUES_RE = re.compile(r"^\s*NO ISSUES\s*$")
ANSWERED_RE = re.compile(r"^\s*ANSWERED\s+\S+\s*$")
CODE_RE = re.compile(r"^\s*(```|~~~)", re.MULTILINE)


def has_code(body):
    return CODE_RE.search(body) is not None


def parse_issues(body):
    """Returns (issues, errors). issues: [{n, severity, text, fix}] in reply order; errors: list of problems.

    Every numbered line is an issue and must carry `[blocking]` or `[minor]`; each issue needs a non-empty
    `Proposed fix:` before the next issue; numbering runs 1..N; zero issues requires a `NO ISSUES` line."""
    issues, errors, cur, no_issues = [], [], None, False
    for line in body.splitlines():
        if ANSWERED_RE.match(line):
            break
        if NO_ISSUES_RE.match(line):
            no_issues = True
            continue
        m = NUMBERED_RE.match(line)
        if m:
            n, rest = int(m.group(1)), m.group(2).strip()
            im = ISSUE_RE.match(rest)
            if not im:
                errors.append(f"issue {n}: no severity [blocking] or [minor]")
                cur = {"n": n, "severity": None, "text": rest, "fix": None}
            else:
                cur = {"n": n, "severity": im.group(1).lower(), "text": im.group(2).strip(), "fix": None}
            issues.append(cur)
            continue
        fm = FIX_RE.match(line)
        if fm and cur is not None:
            cur["fix"] = (fm.group(1) or "").strip() or None
            continue
        if cur is not None and line.strip():
            if cur["fix"] is None:
                cur["text"] += " " + line.strip()
            else:
                cur["fix"] += " " + line.strip()
    nums = [i["n"] for i in issues]
    if nums != list(range(1, len(nums) + 1)):
        errors.append(f"issues must be numbered 1..N in order; got {nums}")
    for i in issues:
        if not i["fix"]:
            errors.append(f"issue {i['n']}: no proposed fix")
    if not issues and not no_issues:
        errors.append("no numbered issues and no `NO ISSUES` line")
    if issues and no_issues:
        errors.append("`NO ISSUES` together with numbered issues")
    return issues, errors


CARD_LINE_RE = re.compile(r"^\s*-?\s*UNRESOLVED BLOCKING (OR[12])-(\d+):\s*\S")


def card_unresolved(card_text, review):
    """Issue numbers the owner card lists as unresolved blocking for this review."""
    out = []
    for line in card_text.splitlines():
        m = CARD_LINE_RE.match(line)
        if m and m.group(1) == review:
            out.append(int(m.group(2)))
    return out


def card_says_none(card_text):
    return any(line.strip().lstrip("- ").strip() == CARD_NONE for line in card_text.splitlines())


def card_says_skipped(card_text, review):
    return any(line.strip().lstrip("- ").startswith(f"{SKIP_MARKER} {review}") for line in card_text.splitlines())
