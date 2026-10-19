# OpenCV check-in demo: Wed 21 Oct, 5:00 AM Dhaka (Tue 20 Oct, 4:00 PM PT)

Live app: **https://184-194-241-186.sslip.io** (open it on your phone and laptop)

## Tuesday night (10 min)
1. Tape the printed test panel flat on a wall at eye level, in good light.
2. On your phone, open the live app once, allow the camera, and take one photo of the panel. You should see the cracks measured in mm.
3. Charge the laptop and the phone.
4. Keep this file and `docs/demo/` open on the laptop as a backup.

## Wednesday, after Fajr
- Open the Zoom link by 4:55 AM. Test the mic and camera.
- Open the live app on the laptop too, and tap **Demo samples → good-straight** once. This warms the server up so the first answer is fast.

## The 5-minute script
1. **Problem (20 s).** "Crack width decides whether concrete needs repair. Inspectors measure it by eye with a card. Prohori measures it in millimetres from a phone photo and says when the number can't be trusted."
2. **Live phone demo (2 min).** Point the phone at the taped panel. Show:
   - The big width number, e.g. "0.52 mm ± 0.06" next to the true printed width.
   - Then stand far away and take another photo. The agent says **"Move closer: the board is only 5 px/mm, need 8."**
   - Move closer and retake. It turns green: **Certified**.
3. **Agent trace (1 min).** Scroll to *Agent trace*. "Each step: what OpenCV saw, then what the agent decided. The vision numbers change the next action. The AI never sees pixels, only the numbers." Switch the selector to **AI agent · Bedrock** for one shot to show the Amazon Bedrock call.
4. **AWS use (1 min).**
   - Runs on an AWS Graviton (Arm) t4g.small with OpenCV 5, HTTPS, DynamoDB for traces and S3 for evidence (private and encrypted), with a budget alarm.
   - Cost so far is almost zero. We kept it cheap on purpose: the free rules agent is the default, and the AI is capped per day.
   - The credits will go to the Graviton4 (c8g) benchmarks with OpenCV's optimised build (COOL) this week.
5. **Results and next steps (40 s).**
   - On sharp photos the average error is **0.036 mm** (about 5%). Blurry photos are flagged "not certified" instead of giving a wrong number.
   - By Oct 26: Graviton4 + COOL speed benchmarks, the agent comparison (random vs rules vs AI), the report and the video.

## Questions to ask Phil
- Thank him: the first $75 arrived in the bank. Ask when the second $75 will be sent after this call.
- Our account is on the AWS **Free plan**, which blocks Marketplace AMIs like COOL. Is upgrading to the paid plan expected?

## If something breaks
- **Camera won't open:** use **Upload photo** and pick a panel photo from the gallery.
- **Network is bad:** tap **Demo samples**. They need only a tiny upload.
- **Server is down:** show the backup clip (D10) and `docs/demo/app_move_closer_2026-10-19.jpg`.
