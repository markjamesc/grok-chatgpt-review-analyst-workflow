# Handoff packet format

Every message between the parent and a child is a packet. Packets are sealed once sent and never edited.

```text
PACKET_ID: <run>-<stage>-<seq>[-vN]
ROLE: <child role>
STAGE: <1-5 or 2F>
SUPERSEDES: <earlier packet id>   (only on a -vN correction)
TASK: <one paragraph>
INPUTS:
  - <relative path> sha256=<hash> bytes=<n>   (whole file; parts listed as part k of K)
ALLOWED TO SEE: <list>
NOT ALLOWED TO SEE: answer key; peer paths before freeze; <others>
RULES: <only the rules this task needs>
EXPECTED OUTPUT: <named output paths and format; parts if large>
REPLY ENDS WITH: ANSWERED <PACKET_ID> + list of produced files
```

Every reply ends like this, with the `PRODUCED FILES:` list never blank and `ANSWERED` as the last line:

```text
PRODUCED FILES:
- <path of each file written>

ANSWERED <PACKET_ID>
```

## Parent duties
- List every packet in `artifacts/packets/index.json` (id, path, status draft/sent/answered, sealed sha256, and the sealed reply once answered) and run G0 before each send and after each capture.
- Build each sent packet from the template as a new file; never send the template. G0 rejects `TEMPLATE` text, `{{placeholders}}` and the format's `<...>` placeholders.
- A packet is answered only when the child's reply arrives and ends with `ANSWERED <PACKET_ID>`. A file appearing on disk is not a completed send.
- Record send time, the packet hash, and the captured reply hash in the run ledger.
- Name the output paths in each packet under EXPECTED OUTPUT. The child writes only to those paths.
- Check the reply against EXPECTED OUTPUT before sealing it.
- A correction is a new packet with a `-vN` suffix that names what it supersedes.

## Outside-review packets for ChatGPT (Version 3)
- OR1 (Stage 2) and OR2 (Stage 5) packets use `ROLE: Outside Reviewer`. See [outside-review.md](outside-review.md).
- Freeze a copy of every input under `artifacts/outside_review/<OR>/inputs/<original path>` and list the copies.
- OR1: the brief, the proposed locked question and its terms only. No data, no data structure, no code.
- OR2: the locked question, the claims ledger, its deliverables (the draft recommendation) and only the evidence its claims cite.
- `RULES` include `do not write code` and `do not vote`. `EXPECTED OUTPUT` is one path, where the parent captures the reply.
- The reply is a numbered list of issues (`[blocking]` or `[minor]`, each with `Proposed fix:`), or `NO ISSUES`, ending `ANSWERED <PACKET_ID>`. It has no produced-files list.
- If ChatGPT is usage-limited, retry up to 3 times, 5 minutes apart, then mark the packet `skipped` and log `OR-SKIPPED`.

## Stage 3 packets for the Second Designer
- First packet: Stage 3 inputs only. Do not include the Lead Designer's draft or reasoning.
- After the Second Designer's independent design is sealed, send a second packet with the lead's design so the Second Designer can compare and report differences.

## Stage 2 packets for the Risk Reviewer
- Send the Lead Designer's framing for a check, alongside the Second Designer's critique.
- Send the G2F feasibility result for review.

## Stage 3 packets for the SQL Analyst
- Send the current design so the SQL Analyst can write the G3S source gates (extraction completeness, keys, joins, counts). The parent runs those gates.

## Stage 3 packets for the Risk Reviewer
- Send the current design for a red-team.
- After the parent runs G3S, send the source-gate code and results for review.

## Stage 4 packets for the SQL Analyst
- Send the locked design and the frozen, hashed snapshot (not a live system) so the SQL Analyst can run independent SELECT-only queries. Do not include R-A or R-B work before freeze.

## Stage 4 packets for the Risk Reviewer
- After the parent reconciles R-A, R-B, and SQL (G4b), send the reconciliation report and the reconciled evidence for the G4c review. Name the output paths in the packet.
