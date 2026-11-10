# Version 3: ChatGPT outside review (OR1 and OR2)

Version 3 is the Grok Bot team workflow (parent plus six child bots, as in Version 2) with **two outside-review steps
done by one dedicated ChatGPT chat**. ChatGPT is a reviewer from a different model family. It looks for problems at the
two points where a shared blind spot costs most: the question lock and the finish.

ChatGPT **never writes code, never sees the answer key or the data, and never votes.** Each issue it raises is advice
that the Grok side must answer. The Grok side decides; the owner sees anything left unresolved.

## OR1: question lock (Stage 2)

- **When.** After the Stage 2 reviews and G2 pass, before the owner approves the locked question (and before G2F).
- **Packet.** The case brief, the proposed locked question and its terms (the framing record). **No data and no data
  structure**: no values, samples, schemas, table or column lists, feasibility results, snapshots or code.
- **Task.** Find any ambiguity or assumption that could change the answer.
- **Gate.** G2R.

## OR2: finish (Stage 5)

- **When.** After the draft finish (Lead Designer write-up and claims ledger), before G5's final run and before the owner
  approves the finish package. G5R runs after G5.
- **Packet.** The locked question, the claims ledger, the draft recommendation (the ledger's deliverables) and the official
  numbers (only the sealed evidence the ledger's claims cite). No raw data and no code.
- **Task.** Does the conclusion follow from the official numbers, and does any claim exceed the evidence?
- **Gate.** G5R.

## Packet

An outside-review packet uses the normal [handoff format](handoff.md) with:

- `ROLE: Outside Reviewer`, `STAGE: 2` (OR1) or `STAGE: 5` (OR2), packet id `<run>-OR1-<seq>` or `<run>-OR2-<seq>`;
- every input a **frozen copy** under `artifacts/outside_review/<OR>/inputs/<original path>`, so what ChatGPT saw stays
  sealed even when the original is later repaired as a new version;
- `NOT ALLOWED TO SEE` naming the answer key (and, for OR1, the data: values and structure);
- `RULES` including `do not write code` and `do not vote`;
- `EXPECTED OUTPUT` naming exactly one path, where the parent captures ChatGPT's reply verbatim;
- `REPLY ENDS WITH: ANSWERED <PACKET_ID> after the numbered issues`.

## Reply format

A numbered list of issues, each with a severity and a proposed fix, ending with the ANSWERED marker:

```text
1. [blocking] <issue>
   Proposed fix: <fix>
2. [minor] <issue>
   Proposed fix: <fix>

ANSWERED <PACKET_ID>
```

`blocking` means the issue could change the answer or the decision; `minor` means it could not. With nothing to report the
reply says `NO ISSUES` instead of the list. A reply containing a code block fails G0 and the review gate.

## Dispositions

The Grok side answers **every** issue in `artifacts/outside_review/<OR>_dispositions.json`:

```text
{"review": "OR1", "reply": {"path", "sha256"},
 "dispositions": [{"issue": 1, "severity": "blocking", "status": "fixed", "where": "...", "files": [{"path", "sha256"}],
                   "decided_by": "lead-designer"},
                  {"issue": 2, "severity": "minor", "status": "not_fixed", "reason": "...", "decided_by": "lead-designer"}]}
```

- `fixed` names where, and the fixed files. Each fixed file must be sealed by the current base gate (G2 for OR1, G5 for
  OR2), so a fix goes through the normal re-review and gate before the review gate passes.
- `not_fixed` gives a reason.
- `decided_by` is a Grok role. The outside reviewer never decides its own issues.

## Owner card

The parent writes the card text shown on the owner's lock card (OR1) or finish card (OR2) to
`artifacts/outside_review/<OR>_card.md`. It must list **every** blocking issue that was not fixed, one line each:

```text
- UNRESOLVED BLOCKING OR1-3: <issue and the Grok side's reason>
```

or `- UNRESOLVED BLOCKING: none`. The owner's approval records the card's hash: `or1_card_sha256` in
`artifacts/stage2_owner_question_approval.json` and `or2_card_sha256` in `artifacts/stage5_owner_approval.json`.

## Usage limits

If ChatGPT is blocked by a usage limit, retry up to 3 times, at least 5 minutes apart. If it is still blocked, proceed
without it: set the review's status to `skipped`, log `OR-SKIPPED` in its record, mark the packet `skipped` in the
packet index, and show `- OR-SKIPPED <OR>: <reason>` on the owner card. Every attempt is logged with its time and outcome.

## Record

`artifacts/outside_review/<OR>.json`:

```text
{"review": "OR1", "reviewer": "chatgpt", "packet_id": "...", "status": "done" | "skipped",
 "attempts": [{"at": "<timestamp with zone>", "outcome": "answered" | "usage_limit"}],
 "reply": {"path", "sha256"}, "dispositions": {"path", "sha256"},       (done)
 "skip_log": "OR-SKIPPED ...",                                         (skipped)
 "card": {"path", "sha256"}}
```

## Gates

- **G2R / G5R** check that the base gate passed and is current; the OR packet passes every G0 check and carries only the
  allowed material; the reply has the ANSWERED marker and is the reply sealed in the packet index; every issue has
  exactly one disposition; fixes are sealed; and the owner card lists exactly the unresolved blocking issues (or
  OR-SKIPPED with the logged retries).
- **G0** applies the outside-review reply contract to `outside-reviewer` packets and allows status `skipped` only for them.
- **G6** requires G2R and G5R PASS and current with status done or skipped, the skipped packets in G0 to be exactly the
  logged skips, and owner approvals that name the OR1 and OR2 card hashes.

## Honest limit

One outside reviewer is one more model family, not independence. Its silence is not evidence that the work is right, and
its agreement is not a vote. Version 3 must not be described as a three-family check.
