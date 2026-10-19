# OpenCV check-in demo: Wed 21 Oct, 5:00 AM Dhaka (Tue 20 Oct, 4:00 PM PT)

**Live app:** https://184-194-241-186.sslip.io (scan `QR_live_app.png` with your phone)
**Live build:** git tag `demo-2026-10-21`. Don't change the server before the call.

## Tuesday night (10 min)
1. Tape the printed test panel flat on a wall at eye level, in good light.
2. On your phone, open the app (scan the QR), allow the camera, type **wall-1** in *Joint ID*, and take one photo of the panel from about 20 cm. You should get a big mm number.
3. Charge the laptop and the phone.
4. Open this folder on the laptop: the screenshots are your backup if anything fails.
5. Click **Confirm** in the AWS email "Subscription Confirmation" (turns on the engineer alerts).

## Wednesday, after Fajr
- Open the Zoom link by 4:55 AM. Test the mic and camera.
- On the laptop, open the app and tap **Demo samples → good-straight** once. This wakes the server so the first answer is fast.

## The 5-minute script

**1. Problem (20 s)**
"Crack width decides whether concrete needs repair, and it's still measured by eye with a plastic card. Prohori measures it in millimetres from a phone photo, and it refuses to give a number when the photo can't support one."

**2. Live phone demo (2 min)**, sharing your phone screen or holding it to the webcam:
- Close photo of the panel (about 20 cm). Show the big number, e.g. **"0.52 mm ± 0.06"**, against the true printed width written on the panel.
- Step back about 1 m and shoot again. The banner turns amber: **"Move closer: the board is only 5 px/mm, need 8."**
- Come close again: **Certified**, green.
- Scroll to **History** (Joint ID wall-1). "Every visit to the same crack is stored. An alert goes to an engineer only if the change is bigger than the measurement uncertainty."

**3. Agent trace (1 min)**
Scroll to **Agent trace**. "Each step shows what OpenCV measured, then what the agent decided. The vision numbers change the next action. The AI never sees pixels, only numbers."
Optional: switch the selector to **AI agent · Bedrock** for one shot to show the Amazon Bedrock call (Nova Lite).

**4. How the grant is used (1 min)**
- **The server:** an AWS Graviton (Arm) t4g.small runs OpenCV 5 over HTTPS.
- **Storage:** DynamoDB for agent traces and visit history, and S3 for evidence photos, private and encrypted. Faces are blurred automatically before anything is saved.
- **Engineer alerts:** SNS alerts with an "I reviewed this" approval step.
- **Cost guards:** a budget alarm, and the AI capped per day. Free rules are the default, so the spend so far is cents.
- **Next for the credits:** Graviton4 (c8g) benchmarks with OpenCV's optimised COOL build. *Ask: our account is on the AWS Free plan, which blocks the COOL Marketplace image. Should we upgrade?*

**5. Results so far and plan to Oct 26 (40 s)**
- **Accuracy:** on sharp photos, average error **0.037 mm**. This is tested on photos the settings were never tuned on.
- **Trust:** we built a statistically calibrated quality check: of the cracks it certifies, about **4 in 100** are wrong (target ≤ 5), and the ± range holds the true width about **90%** of the time. It goes live after this call.
- **Agent vs rules** (pre-registered simulation, 100 held-out cases): on messy, multi-problem captures the AI recovered **85%**, fixed rules **62%**, random **2%**. "We wrote the test rules before running it, and we'll publish it even where the AI doesn't clearly win."
- **Public benchmark (krkCMd, 19,098 real crack profiles):** it showed us how resolution limits accuracy, and that already changed our design.
- **By Oct 26:** COOL on Graviton4 speed tests, crack finder trained on public datasets, report, video.

## Questions for Phil
- Thank him: the first $75 arrived. When will the second $75 be sent after today?
- Is upgrading to the AWS Paid plan expected so we can use the COOL Marketplace AMI?

## If something breaks
- **Camera won't open:** use **Upload photo** and pick a photo of the panel from the gallery.
- **Network is bad:** use **Demo samples** (tiny upload).
- **Server is down:** show the screenshots in this folder (`screens/`), in order 01 → 05.
