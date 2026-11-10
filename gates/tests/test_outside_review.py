"""Version 3: tests for the ChatGPT outside reviews OR1/OR2 (gates G2R, G5R), their G0 reply contract and the G6
requirements. Parser tests need no R. The gate tests build the same R-certified project as test_finish_gates
(every gate G1..G6 PASS in order, with OR1 and OR2 done), then plant one defect per test and assert the named
check FAILs. No R counterpart exists for G2R/G5R (the R gate has no outside review), so there is no parity test for them.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from gates.or_format import has_code, parse_issues
from gates.run import run_gate
from gates.tests import fixture_project as F
from gates.tests.test_finish_gates import build_base, failed


class IssueParser(unittest.TestCase):
    def test_good_reply(self):
        issues, errs = parse_issues(F.or_reply_text("X-OR1-01", F.OR_ISSUES["OR1"]))
        self.assertEqual(errs, [])
        self.assertEqual([(i["n"], i["severity"]) for i in issues], [(1, "blocking"), (2, "minor"), (3, "blocking")])
        self.assertTrue(all(i["fix"] for i in issues))

    def test_no_issues(self):
        self.assertEqual(parse_issues("NO ISSUES\n\nANSWERED X\n"), ([], []))

    def test_missing_severity(self):
        _, errs = parse_issues("1. The window is vague.\n   Proposed fix: say inclusive.\n\nANSWERED X\n")
        self.assertTrue(any("severity" in e for e in errs))

    def test_unknown_severity(self):
        _, errs = parse_issues("1. [major] The window is vague.\n   Proposed fix: say inclusive.\n\nANSWERED X\n")
        self.assertTrue(any("severity" in e for e in errs))

    def test_missing_fix(self):
        _, errs = parse_issues("1. [minor] The window is vague.\n2. [minor] Other.\n   Proposed fix: x\n\nANSWERED X\n")
        self.assertTrue(any("issue 1: no proposed fix" in e for e in errs))

    def test_numbering(self):
        _, errs = parse_issues("1. [minor] a\n   Proposed fix: x\n3. [minor] b\n   Proposed fix: y\n\nANSWERED X\n")
        self.assertTrue(any("numbered 1..N" in e for e in errs))

    def test_empty_reply(self):
        _, errs = parse_issues("Looks fine to me.\n\nANSWERED X\n")
        self.assertTrue(errs)

    def test_no_issues_with_list(self):
        _, errs = parse_issues("NO ISSUES\n1. [minor] a\n   Proposed fix: x\nANSWERED X\n")
        self.assertTrue(errs)

    def test_multiline_issue_and_fix(self):
        issues, errs = parse_issues("1. [blocking] first line\n   continues here\n   Proposed fix: do x\n   and y\n\nANSWERED X\n")
        self.assertEqual(errs, [])
        self.assertEqual(issues[0]["text"], "first line continues here")
        self.assertEqual(issues[0]["fix"], "do x and y")

    def test_code_detection(self):
        self.assertTrue(has_code("1. [minor] a\n   Proposed fix:\n```r\nx <- 1\n```\n"))
        self.assertFalse(has_code("1. [minor] use `x` instead\n"))


@unittest.skipUnless(F.r_available(), "Rscript and the R repo (GATES_R_REPO) are needed to build an R-certified project")
class OutsideReviewGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="grok-or-")
        cls.base = os.path.join(cls.tmp, "base")
        cls.records, _ = build_base(cls.base, os.path.join(cls.tmp, "pin"))
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def copy(self):
        OutsideReviewGates.n += 1
        d = os.path.join(self.tmp, f"case{OutsideReviewGates.n}")
        shutil.copytree(self.base, d, symlinks=True)
        return d

    def assertFailsOn(self, gate, root, check_substr):
        rec = run_gate(gate, root)
        self.assertEqual(rec["result"], "FAIL", f"{gate} should FAIL; checks={failed(rec)} error={rec.get('error')}")
        hit = [c for c in failed(rec) if check_substr in c]
        self.assertTrue(hit, f"{gate}: expected a failing check containing {check_substr!r}; failing: {failed(rec)}")
        return rec

    def assertPasses(self, gate, root):
        rec = run_gate(gate, root)
        self.assertEqual(rec["result"], "PASS", f"{gate}: {failed(rec)} {rec.get('error', '')}")
        return rec

    # ---------------------------------------------------------------- good path
    def test_00_good_path(self):
        for g in ("G2R", "G5R", "G0", "G6"):
            self.assertEqual(self.records[g]["result"], "PASS", f"{g}: {failed(self.records[g])}")
        o1 = self.records["G2R"]["outside_review"]
        self.assertEqual((o1["status"], o1["issues"], o1["blocking"], o1["unresolved_blocking"]), ("done", 3, [1, 3], [3]))
        o2 = self.records["G5R"]["outside_review"]
        self.assertEqual((o2["status"], o2["unresolved_blocking"]), ("done", []))
        self.assertIn("outside_reviews", self.records["G6"]["certificate"])

    def test_skipped_after_retries_passes_and_is_shown(self):
        r = self.copy()
        F.add_outside_review(r, "OR2", status="skipped")
        rec = self.assertPasses("G5R", r)
        self.assertEqual(rec["outside_review"]["status"], "skipped")
        g0 = self.assertPasses("G0", r)
        self.assertEqual((g0["unanswered"], g0["skipped"]), ([], ["CASE-OR2-01"]))
        F.approve_finish(r)
        self.assertPasses("G6", r)

    def test_no_issues_reply_passes(self):
        r = self.copy()
        F.add_outside_review(r, "OR2", issues=[])
        self.assertPasses("G5R", r)

    # ---------------------------------------------------------------- packet content
    def test_or1_packet_with_data(self):
        for rel in ("data/orders.csv", "artifacts/stage2f_feasibility.json", "artifacts/stage3_grok_design.json"):
            with self.subTest(path=rel):
                r = self.copy()
                F.add_outside_review(r, "OR1", inputs=F.or_inputs("OR1") + [rel])
                self.assertFailsOn("G2R", r, "OR1 carries no data or data structure")

    def test_or1_packet_with_code(self):
        r = self.copy()
        F.add_outside_review(r, "OR1", inputs=F.or_inputs("OR1") + ["sql/g3s/keys.sql"])
        rec = self.assertFailsOn("G2R", r, "OR1 no code inputs")
        self.assertIn("OR1 carries no data or data structure", failed(rec))

    def test_or1_packet_without_brief(self):
        r = self.copy()
        F.add_outside_review(r, "OR1", inputs=["artifacts/stage2_framing.json"])
        self.assertFailsOn("G2R", r, "OR1 carries the brief and the proposed locked question")

    def test_or_input_not_frozen(self):
        r = self.copy()
        pid = "CASE-OR1-01"
        F.add_outside_review(r, "OR1", packet=F.or_packet_text(r, "OR1", pid, ["brief/BRIEF.md", "artifacts/stage2_framing.json"]))
        self.assertFailsOn("G2R", r, "OR1 inputs are frozen copies")

    def test_or_answer_key_input(self):
        r = self.copy()
        F.wt(r, "docs/stage2/answer_key.md", "secret\n")
        F.add_outside_review(r, "OR1", inputs=F.or_inputs("OR1") + ["docs/stage2/answer_key.md"])
        self.assertFailsOn("G2R", r, "G0: Packet CASE-OR1-01 no forbidden inputs")
        self.assertFailsOn("G0", r, "Packet CASE-OR1-01 no forbidden inputs")

    def test_or1_data_not_withheld(self):
        r = self.copy()
        frozen = [f"artifacts/outside_review/OR1/inputs/{x}" for x in F.or_inputs("OR1")]
        F.add_outside_review(r, "OR1", packet=F.or_packet_text(r, "OR1", "CASE-OR1-01", frozen, not_allowed="answer key"))
        self.assertFailsOn("G2R", r, "OR1 withholds the data")

    def test_or_rules_missing_no_vote(self):
        r = self.copy()
        F.freeze_inputs(r, "OR1", F.or_inputs("OR1"))
        frozen = [f"artifacts/outside_review/OR1/inputs/{x}" for x in F.or_inputs("OR1")]
        F.add_outside_review(r, "OR1", packet=F.or_packet_text(r, "OR1", "CASE-OR1-01", frozen, rules="do not write code"))
        self.assertFailsOn("G2R", r, "OR1 packet rules: no code, no vote")

    def test_or_wrong_role(self):
        r = self.copy()
        frozen = [f"artifacts/outside_review/OR1/inputs/{x}" for x in F.or_inputs("OR1")]
        F.freeze_inputs(r, "OR1", F.or_inputs("OR1"))
        F.add_outside_review(r, "OR1", packet=F.or_packet_text(r, "OR1", "CASE-OR1-01", frozen, role="Risk Reviewer"))
        self.assertFailsOn("G2R", r, "OR1 addressed to the outside reviewer")

    def test_or2_extra_input_not_in_ledger(self):
        r = self.copy()
        F.add_outside_review(r, "OR2", inputs=F.or_inputs("OR2") + ["outputs/rb/summary.csv"])
        self.assertFailsOn("G5R", r, "OR2 carries only the question, claims, draft recommendation and cited numbers")

    def test_or2_raw_data(self):
        r = self.copy()
        F.add_outside_review(r, "OR2", inputs=F.or_inputs("OR2") + ["data/snapshot.sqlite"])
        self.assertFailsOn("G5R", r, "OR2 carries only the question")

    def test_or2_without_ledger(self):
        r = self.copy()
        F.add_outside_review(r, "OR2", inputs=["artifacts/stage2_framing.json", "stage5-decision.md"])
        self.assertFailsOn("G5R", r, "OR2 carries the claims ledger")

    def test_or2_copy_differs_from_ledger(self):
        r = self.copy()
        F.add_outside_review(r, "OR2")
        F.wt(r, "artifacts/outside_review/OR2/inputs/stage5-decision.md", "Decision: hold.\n")
        F.add_outside_review(r, "OR2", inputs=[])  # rebuild packet over the edited copy
        pid = "CASE-OR2-01"
        frozen = [f"artifacts/outside_review/OR2/inputs/{x}" for x in F.or_inputs("OR2")]
        F.add_outside_review(r, "OR2", inputs=[], packet=F.or_packet_text(r, "OR2", pid, frozen))
        self.assertFailsOn("G5R", r, "OR2 copies match the claims ledger")

    # ---------------------------------------------------------------- reply
    def test_reply_without_answered(self):
        r = self.copy()
        F.add_outside_review(r, "OR1", reply=F.or_reply_text("CASE-OR1-01", F.OR_ISSUES["OR1"]).replace("ANSWERED CASE-OR1-01", "Done."))
        self.assertFailsOn("G2R", r, "G0: Packet CASE-OR1-01 reply ends with ANSWERED")

    def test_reply_edited_after_seal(self):
        r = self.copy()
        with open(os.path.join(r, "replies/outside/CASE-OR1-01_reply.md"), "a") as fh:
            fh.write("late\n")
        rec = self.assertFailsOn("G2R", r, "reply sealed")
        self.assertIn("OR1 reply is the sealed reply", failed(rec))

    def test_reply_issue_without_severity(self):
        r = self.copy()
        F.add_outside_review(r, "OR1", reply="1. The window is vague.\n   Proposed fix: inclusive.\n\nANSWERED CASE-OR1-01\n")
        rec = self.assertFailsOn("G2R", r, "OR1 reply issues well-formed")
        self.assertIn("G0: Packet CASE-OR1-01 outside-review issues well-formed", failed(rec))

    def test_reply_with_code(self):
        r = self.copy()
        rep = "1. [minor] Use a filter.\n   Proposed fix: filter rows.\n```r\ndf |> filter(x)\n```\n\nANSWERED CASE-OR1-01\n"
        F.add_outside_review(r, "OR1", reply=rep, issues=[("minor", "Use a filter.", "filter rows.", "not_fixed")])
        rec = self.assertFailsOn("G2R", r, "OR1 reply has no code")
        self.assertIn("G0: Packet CASE-OR1-01 outside reviewer wrote no code", failed(rec))

    def test_reply_not_at_expected_output(self):
        r = self.copy()
        F.add_outside_review(r, "OR1")
        idx = F.rj(r, "artifacts/packets/index.json")
        row = next(p for p in idx["packets"] if p["id"] == "CASE-OR1-01")
        row["reply"] = F.wt(r, "replies/elsewhere.md", F.or_reply_text("CASE-OR1-01", F.OR_ISSUES["OR1"]))
        F.wj(r, "artifacts/packets/index.json", idx)
        self.assertFailsOn("G0", r, "reply captured at the expected output")

    # ---------------------------------------------------------------- dispositions
    def _disp(self, r, review="OR1"):
        return F.rj(r, f"artifacts/outside_review/{review}_dispositions.json")["dispositions"]

    def test_issue_without_disposition(self):
        r = self.copy()
        d = self._disp(r)[:2]
        F.add_outside_review(r, "OR1", dispositions=d)
        self.assertFailsOn("G2R", r, "OR1 every issue has a disposition")

    def test_duplicate_disposition(self):
        r = self.copy()
        d = self._disp(r); d.append(dict(d[0]))
        F.add_outside_review(r, "OR1", dispositions=d)
        self.assertFailsOn("G2R", r, "OR1 every issue has a disposition")

    def test_fixed_without_where(self):
        r = self.copy()
        d = self._disp(r); d[0].pop("where")
        F.add_outside_review(r, "OR1", dispositions=d)
        self.assertFailsOn("G2R", r, "OR1 dispositions fixed (where) or not fixed (reason)")

    def test_not_fixed_without_reason(self):
        r = self.copy()
        d = self._disp(r); d[1]["reason"] = "TBD"
        F.add_outside_review(r, "OR1", dispositions=d)
        self.assertFailsOn("G2R", r, "OR1 dispositions fixed (where) or not fixed (reason)")

    def test_fix_not_sealed_by_base_gate(self):
        r = self.copy()
        F.wt(r, "docs/stage2/FRAMING_RECORD_v02.md", "repaired but never re-reviewed\n")
        F.add_outside_review(r, "OR1", fix_files=["docs/stage2/FRAMING_RECORD_v02.md"])
        self.assertFailsOn("G2R", r, "OR1 fixes sealed by the current G2")

    def test_severity_changed(self):
        r = self.copy()
        d = self._disp(r); d[2]["severity"] = "minor"
        F.add_outside_review(r, "OR1", dispositions=d)
        self.assertFailsOn("G2R", r, "OR1 disposition severity matches the reply")

    def test_outside_reviewer_cannot_decide(self):
        r = self.copy()
        d = self._disp(r); d[1]["decided_by"] = "outside-reviewer"
        F.add_outside_review(r, "OR1", dispositions=d)
        self.assertFailsOn("G2R", r, "OR1 decided by the Grok side")

    # ---------------------------------------------------------------- owner card
    def test_unresolved_blocking_missing_from_card(self):
        r = self.copy()
        F.add_outside_review(r, "OR1", card=F.or_card_text("OR1", []))
        self.assertFailsOn("G2R", r, "OR1 owner card lists every unresolved blocking issue")

    def test_card_lists_a_resolved_issue(self):
        r = self.copy()
        F.add_outside_review(r, "OR1", card=F.or_card_text("OR1", [1, 3]))
        self.assertFailsOn("G2R", r, "OR1 owner card lists every unresolved blocking issue")

    def test_card_silent_when_none(self):
        r = self.copy()
        F.add_outside_review(r, "OR2", card="# Owner card\n")
        self.assertFailsOn("G5R", r, "OR2 owner card lists every unresolved blocking issue")

    # ---------------------------------------------------------------- usage-limit skip
    def test_skip_too_early(self):
        r = self.copy()
        at = [{"at": f"2026-11-10T10:{m:02d}:00-06:00", "outcome": "usage_limit"} for m in (0, 5, 10)]
        F.add_outside_review(r, "OR2", status="skipped", attempts=at)
        self.assertFailsOn("G5R", r, "OR2 skipped only after 3 retries on a usage limit")

    def test_skip_retries_too_close(self):
        r = self.copy()
        at = [{"at": f"2026-11-10T10:{m:02d}:00-06:00", "outcome": "usage_limit"} for m in (0, 1, 2, 3)]
        F.add_outside_review(r, "OR2", status="skipped", attempts=at)
        self.assertFailsOn("G5R", r, "OR2 skipped only after 3 retries on a usage limit")

    def test_skip_not_shown_on_card(self):
        r = self.copy()
        F.add_outside_review(r, "OR2", status="skipped", card=F.or_card_text("OR2", []))
        self.assertFailsOn("G5R", r, "OR2 owner card shows OR-SKIPPED")

    def test_answered_after_too_many_retries(self):
        r = self.copy()
        at = [{"at": f"2026-11-10T10:{m:02d}:00-06:00", "outcome": "usage_limit"} for m in (0, 5, 10, 15)]
        at.append({"at": "2026-11-10T10:20:00-06:00", "outcome": "answered"})
        F.add_outside_review(r, "OR1", attempts=at)
        self.assertFailsOn("G2R", r, "OR1 answered within the retry limit")

    def test_skipped_status_only_for_outside_review(self):
        r = self.copy()
        F.add_packets(r, [("CASE-4-01", F.packet_text(r, "CASE-4-01"), "skipped", None)])
        self.assertFailsOn("G0", r, "Packet CASE-4-01 skipped only for an outside review")

    # ---------------------------------------------------------------- G6
    def test_g6_requires_both_outside_reviews(self):
        for gid, review in (("G2R", "OR1"), ("G5R", "OR2")):
            with self.subTest(gate=gid):
                r = self.copy()
                os.remove(os.path.join(r, f"artifacts/gates/{gid}.json"))
                rec = self.assertFailsOn("G6", r, f"{review} outside review done or logged as skipped")
                self.assertIn(f"{gid} PASS and current", failed(rec))

    def test_g6_or_record_stale(self):
        r = self.copy()
        with open(os.path.join(r, "artifacts/outside_review/OR1_card.md"), "a") as fh:
            fh.write("edited after the gate\n")
        self.assertFailsOn("G6", r, "G2R PASS and current")

    def test_g6_question_approval_missing_or_wrong_card(self):
        r = self.copy()
        os.remove(os.path.join(r, "artifacts/stage2_owner_question_approval.json"))
        self.assertFailsOn("G6", r, "Owner approved the locked question with the OR1 card")
        r = self.copy()
        a = F.rj(r, "artifacts/stage2_owner_question_approval.json"); a["or1_card_sha256"] = "0" * 64
        F.wj(r, "artifacts/stage2_owner_question_approval.json", a)
        self.assertFailsOn("G6", r, "Owner approved the locked question with the OR1 card")

    def test_g6_finish_approval_without_or2_card(self):
        r = self.copy()
        a = F.rj(r, "artifacts/stage5_owner_approval.json"); a.pop("or2_card_sha256")
        F.wj(r, "artifacts/stage5_owner_approval.json", a)
        self.assertFailsOn("G6", r, "Owner finish approval names the OR2 card")

    def test_g6_skipped_packet_not_logged(self):
        r = self.copy()
        idx = F.rj(r, "artifacts/packets/index.json")
        row = next(p for p in idx["packets"] if p["id"] == "CASE-OR2-01")
        row["status"] = "skipped"; row.pop("reply")
        F.wj(r, "artifacts/packets/index.json", idx)
        self.assertPasses("G0", r)
        self.assertFailsOn("G6", r, "Skipped packets are logged outside reviews")

    def test_g6_g2f_before_g2r(self):
        r = self.copy()
        rec = F.rj(r, "artifacts/gates/G2R.json"); rec["checked_at_utc"] = "2099-01-01T00:00:00Z"
        F.wj(r, "artifacts/gates/G2R.json", rec)
        self.assertFailsOn("G6", r, "All stages in order")

    def test_g5r_requires_current_g5(self):
        r = self.copy()
        os.remove(os.path.join(r, "artifacts/gates/G5.json"))
        self.assertFailsOn("G5R", r, "G5 PASS and current")


if __name__ == "__main__":
    unittest.main()
