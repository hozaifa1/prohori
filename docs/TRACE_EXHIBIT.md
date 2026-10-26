# Agent trace exhibit: OpenCV output changes the next action

This is one real trace from the live endpoint (https://184-194-241-186.sslip.io, COOL on a Graviton4 c8g.large, policy `llm`,
model `us.amazon.nova-lite-v1:0`), recorded 2026-10-26 03:08 UTC. Session id `exhibit-20261026T030809`. The full stored trace, as
`GET /api/trace/<session_id>` returned it, is in [`exhibits/trace_exhibit.json`](exhibits/trace_exhibit.json). The two overlays are
`exhibits/trace_step0_overlay.jpg` and `exhibits/trace_step1_overlay.jpg`. To make a new one: `python tools/make_exhibits.py trace`.

The two photos are the demo samples `move-closer.jpg` (a real photo of the printed test panel, shrunk to a quarter of its size to mimic
standing too far back) and `closer.jpg` (the same photo shrunk less, 3072 px wide, which is the distance the agent asked for). The app
offers them as a two-step story. So the "operator" in this exhibit is a script that follows the instruction; a real person would take a new photo.

## Step table

| | Step 0 (first capture) | Step 1 (after the instruction) |
|---|---|---|
| Image | 1024 x 768 | 3072 x 2304 |
| **OpenCV 5 observation** | | |
| ChArUco corners found | 24 of 24 | 24 of 24 |
| px/mm at the cracks (board) | **2.71** (3.14) | **7.98** (9.41) |
| Obliquity | 19.4 deg | 19.4 deg |
| Blur variance / blur sigma | 2483 / 0.135 mm | 490 / 0.105 mm |
| Glare / noise | 0 % / 1.5 grey levels | 0 % / 0.8 grey levels |
| **Gate (conformal risk control)** | | |
| Tier | **refused** | **certified** |
| Cracks certified | 0 of 8 | 5 of 8 |
| Reason codes of the capture | `low_resolution` (every crack; K2, K3, K7, K8 also `unstable_width`) | none (K1, K6, K8 flagged `unstable_width`) |
| **Decision** (Nova Lite, forced tool `choose_action`) | | |
| Action | **`move_closer`** | **`accept`** |
| Instruction shown to the operator | "Move closer: the board is 2.71 px/mm, a 1.58 mm crack needs about 2.5 px/mm." | "Accept the capture: all cracks are certified." |
| Model call | 1,256 ms, 3,807 input / 70 output tokens | 689 ms, 3,853 input / 43 output tokens |
| Server time (decode, redact, measure, gate, agent, store) | 2.2 s | 1.2 s |
| Guardrail hit / fallback to rules | no / none | no / none |
| Escalation | none | none |

**Why this shows OpenCV output changing the next action.** In step 0 the only thing wrong is a number OpenCV computed: 2.71 px/mm on the
wall. The gate turns it into the reason code `low_resolution`, and every crack is refused. The agent's input is that observation, the gate
reasons and the crack list (no pixels). It picks `move_closer`, the action the prompt assigns to `low_resolution` when the board is otherwise
found (24 of 24 corners, sharp, 19 degrees). In step 1 the same photo content at 7.98 px/mm gives 5 certified cracks, an empty reason list, and the
agent's `accept` is the only action its guardrail allows on a certified gate. If the step-0 observation had shown a lost board, a steep angle or a soft picture instead, the same code path
would have produced `reposition_marker`, `reshoot_steadier` or `relight` (see [FAILURE_GALLERY.md](FAILURE_GALLERY.md)).

**What is not good in this trace.** The action is right but the sentence is not: it says a 1.58 mm crack "needs about 2.5 px/mm", which is
below the 2.71 px/mm just measured, so the sentence contradicts itself. The rules policy (P1) writes the same advice as "Move closer: only 2.4 px/mm
here, aim for 8 or more." The pre-registered ablation (`eval/results/agent_ablation.md`) found the same weakness: only 57 % of the LLM's
instructions cite a number as its prompt asks, against 91 % for the rules. Also, the gate in step 1 is per crack: 3 of 8 cracks are still flagged, and the capture
counts as certified because at least one crack is certified; the app lists every crack with its own status and interval.

## JSON excerpt (step 0, trimmed; the full record is in `exhibits/trace_exhibit.json`)

```json
{
  "session_id": "exhibit-20261026T030809", "step": 0,
  "observation": {"corners": 24, "px_per_mm": 2.71, "ppm_board": 3.14, "obliquity_deg": 19.39,
                  "blur_var": 2482.7, "blur_sigma_mm": 0.135, "glare_frac": 0, "noise_sigma": 1.499,
                  "crack_coverage": 1, "image_w": 1024, "image_h": 768},
  "gate": {"mode": "crc", "certified": false, "tier": "refused", "reasons": ["low_resolution"],
           "cracks_certified": 0, "cracks_total": 8},
  "decision": {"action": "move_closer", "policy": "llm", "model": "us.amazon.nova-lite-v1:0",
               "instruction": "Move closer: the board is 2.71 px/mm, a 1.58 mm crack needs about 2.5 px/mm.",
               "rationale": "The resolution is too low for the crack widths.",
               "latency_ms": 1255.77, "fallback_reason": null, "input_tokens": 3807, "output_tokens": 70},
  "escalation": null,
  "redaction": {"faces": 0, "model": "yunet_2023mar", "status": "ok", "persisted": true}
}
```

## JSON excerpt (step 1)

```json
{
  "session_id": "exhibit-20261026T030809", "step": 1,
  "observation": {"corners": 24, "px_per_mm": 7.98, "ppm_board": 9.41, "obliquity_deg": 19.39,
                  "blur_var": 490, "blur_sigma_mm": 0.105, "glare_frac": 0, "noise_sigma": 0.822,
                  "crack_coverage": 1, "image_w": 3072, "image_h": 2304},
  "gate": {"mode": "crc", "certified": true, "tier": "certified", "reasons": [],
           "cracks_certified": 5, "cracks_total": 8},
  "decision": {"action": "accept", "policy": "llm", "model": "us.amazon.nova-lite-v1:0",
               "instruction": "Accept the capture: all cracks are certified.",
               "latency_ms": 688.88, "fallback_reason": null, "input_tokens": 3853, "output_tokens": 43}
}
```

(The step-1 instruction also says "all cracks are certified" although 3 of 8 are flagged: another example of the wording problem above. The action and the gate fields are what the system acts on.)

![step 0 overlay](exhibits/trace_step0_overlay.jpg)
![step 1 overlay](exhibits/trace_step1_overlay.jpg)

Step 0 overlay: every crack flagged `low_resolution`. Step 1 overlay: the same board and cracks with 5 certified.
