# Capture protocol: desk session (D03)

About 15 minutes at home. **You don't need to find real cracks.** The printed test panel has 8 synthetic cracks of exactly known width (0.30 to 3.00 mm) on the same sheet as the ChArUco board. That makes it better ground truth than a real crack.

## Setup (once)
1. Print `data/print/PRINT_ME_test_panel_A4.pdf` at **100% / Actual size** (turn off "fit to page"). Matte paper, laser printer if you can.
2. Check the 100 mm bar at the bottom with a ruler. If it's off by more than 1 mm, reprint.
3. Tape the sheet flat on a wall or a table. No curl.

## Shoot (about 25 photos)
Default camera app, no zoom, no portrait mode, no filters.
- 5 straight-on at ~25 cm (whole board and all cracks in frame)
- 5 straight-on at ~45 cm
- 5 tilted ~30 degrees (vary left/right/up/down)
- 5 in poor conditions: dim room, a lamp making glare, a slightly shaky hand
- 5 very close (~12 cm), cropping to a few cracks plus part of the board

## Hand-off
Copy the originals unrenamed into `F:/Projects/Prohori/data/raw/2026-09-19/` by USB or Google Drive. Don't use WhatsApp, because it strips the EXIF data I use.

## Optional, zero effort
If you happen to see a real crack at home or work, snap 2 photos with the panel held flat beside it. Never go looking for one.
