# Grant submission — everything you need, in order

**Form:** https://www.jotform.com/form/262145877145059
**Verified live and accepting as of 2026-08-28.** Review is rolling; the Aug 25 date was when *notices began*, not a close. Six fields, one of which is a CAPTCHA you must complete yourself.

---

## Field-by-field

| # | Field | What to enter |
|---|---|---|
| 1 | **Full Name** (First / Last) | Your legal name as you want it on a prize cheque. Must match the Devpost account. |
| 2 | **Email Address** | `<your Devpost email>` — must be the same address as your Devpost registration, because grant recipient notices go to the team leader's email. |
| 3 | **Team Name** | `Prohori` |
| 4 | **Country** | `Bangladesh` |
| 5 | **Upload Proposal (PDF only)** | `F:\Projects\Prohori\grant\PROHORI_AWS_Compute_Grant_Proposal.pdf` (4 pages, 248 KB) |
| 6 | **Verify you are human** | CAPTCHA — you must do this one. |

Then press **Submit Proposal**.

---

## Status & Readiness

The proposal has been updated and compiled into a clean 4-page PDF with all verified credentials:
- **Lead Name:** S M Hozaifa Hossain (solo)
- **Honors & Awards:** Winner of the **IEEE EDS TCAD Hackathon 2026** (first from Bangladesh), IEEE HTB Certificate of Recognition (2025), IELTS 8.0 Overall.
- **Publications Added:** IJABC 2024 (Computer Vision/Video pose estimation, 97.0% F1), IEEE EDTM 2026 (Deep Learning inverse design over 6,000 simulations), and Springer Nature SNAM 2026 (LLM prompting & reasoning with Mixtral 8x7B).
- **Measurement & Systems:** GAA-FeFET & SNN defended thesis under ex-GlobalFoundries Principal Engineer, Torbiz distributed edge inference, Muhasaba 18-tool MCP server, and KPMG PMO Lead.

To rebuild if further edits are made:

```bash
cd F:/Projects/Prohori/grant && python ../tools/make_pdf.py proposal.md PROHORI_AWS_Compute_Grant_Proposal.pdf "PROHORI - AWS Compute Grant Proposal" "PROHORI - OpenCV AI Competition 2026 - Team Prohori"
```

---

## What the proposal covers, mapped to their required list

All nine required elements are present:

| Required | Where |
|---|---|
| Team name | Header |
| Problem statement + real-world impact | §1 |
| Planned OpenCV 5 image/video analysis | §3 |
| Planned AWS architecture and services | §5 |
| Architecture diagram or technical description | §5, embedded diagram |
| Target users / beneficiaries | §2 |
| Evaluation method + judge demonstration | §7, §8 |
| COOL / Agentic / both / neither | Header — **both** |
| Team bio incl. hackathon history | §9 |

And against their published grant scoring weights:

| Criterion | Weight | How the proposal addresses it |
|---|---|---|
| OpenCV 5 & core image/video fit | 20% | §3 names specific modules with a reason each is necessary, and states every API was confirmed by direct probe |
| Technical & AWS feasibility | 20% | §5 service table; scope explicitly cut in §9; $0 path costed |
| Innovation | 20% | Error budget + measured bias; accuracy invariance as a COOL criterion; the P0/P1/P2 agent ablation |
| Real-world impact | 20% | §1 with cited figures, and an explicit statement of what the tool does *not* claim |
| Team strength | 10% | §9 — **the one section you should strengthen** |
| Evaluation & demo plan | 10% | §7, §8 |

---

## After you submit

1. Save the confirmation screen or email — the TickTick task "Confirm grant confirmation receipt" needs it.
2. Recipient notices go by email to the team leader. Non-selection changes nothing about your eligibility: you stay in the competition and remain eligible for all five prizes.
3. If selected, a **30-minute Zoom check-in between Sep 21 and Oct 2 is mandatory** to release the second half of the credits.

## What does not depend on this at all

The grant is $150. The prize ceiling is **$7,000** — one Overall Award plus both Special Awards, which the rules explicitly permit. The build phase runs to **Oct 26** regardless of the grant outcome. Nothing about the entry is blocked by this form.
