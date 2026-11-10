# Standing rules (short list)

1. Do not weaken a gate. No verbal waivers. Versions 2 and 3 may seek an official lock; Version 1 is scored on accuracy only and cannot earn one.
2. Never overwrite or reseal sent, reviewed, or frozen inputs. Make new versions.
3. Keep the parent and children isolated; score blind; keep the key away from live roles. The earlier key preparer from the ChatGPT (Version 1) side holds the key and scores.
4. All team bots share one model family, so their independence is limited. Say so. The ChatGPT outside reviewer adds one other family at two points only.
5. Analysis is in R. SQL is SELECT-only. Gates are Python, owned by the parent.
6. No writes to live systems without owner approval.
7. Escalate only material analytical or business changes and required approvals.
8. Repair cap of 3 per defect, then escalate with problems, a recommendation, and a batched revision.
9. Large outputs come in parts, with assembly and a log.
10. No push to `main` without one owner approval.
11. After a repair, the current file goes back to every required reviewer before its gate. A review of a superseded version does not count.
12. A child's work is done only when its reply reaches the parent and ends with `ANSWERED <PACKET_ID>` after a non-blank list of produced files. A file on disk is not a reply.
13. Never send a template. Sent packets are new versions with no `TEMPLATE` text or `{{placeholders}}` (G0).
14. **Version 3 outside review.** ChatGPT reviews at OR1 (question lock) and OR2 (finish) only. It never writes code, never sees the key or the data, and never votes. The Grok side answers every issue as fixed (where) or not fixed (reason). An unfixed blocking issue goes on the owner's card. A usage limit gets 3 retries 5 minutes apart, then the step proceeds and logs OR-SKIPPED, shown to the owner.

## Run cap (head-to-head test)

One attempt per version on Case B. Maximum of 3 repair rounds. Stop and report after about a day of work per side. If a side is blocked, wait and retry up to 3 times, then report.

## Copyright

The owner holds the copyright. No license is granted. Do not add a LICENSE file.
