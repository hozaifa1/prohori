# Credits and sources for the demo video

## Rana Plaza context card (`assets/cards/rana_plaza.png`)

Claims on the card, checked on 2026-10-26 against these sources. **No news photographs or footage are used anywhere in the video.**

| Claim | Source |
|---|---|
| Collapse on 24 April 2013 in Savar (near Dhaka), Bangladesh | Wikipedia, "Rana Plaza collapse", https://en.wikipedia.org/wiki/Rana_Plaza_collapse ; ILO, "Bangladesh Rana Plaza Compensation Scheme" (ILO/TF/Bangladesh/R.1), https://www.ilo.org/sites/default/files/wcmsp5/groups/public/@ed_protect/@soc_sec/documents/publication/wcms_431795.pdf |
| 1,134 people died | Same two sources (the ILO compensation-scheme document gives 1,134; Wikipedia says the search for the dead ended on 13 May 2013 with 1,134 confirmed deaths and about 2,500 injured people rescued). Some other sources give slightly different counts (1,132 to 1,138). |
| Cracks were reported the day before (23 April 2013); the building was ordered evacuated; factories told workers to return the next day | Wikipedia (as above); The National, "Police ordered shutdown of tower the day before its deadly collapse", https://www.thenational.ae/uae/police-ordered-shutdown-of-tower-the-day-before-its-deadly-collapse-1.646507 ; Dhaka Tribune, "Rana Plaza collapse: What happened that day", https://www.dhakatribune.com/bangladesh/344731/rana-plaza-collapse-what-happened-that-day |
| Cause attributed mainly to regulatory failure (not shown on the card) | ILO, https://www.ilo.org/resource/article/enforce-building-code-all-public-establishments |

The narration says "collapsed a day after cracks were reported", which matches the table.

## Published numbers shown on `assets/cards/published_comparison.png`

* Hassouna, M., Marzouk, M., Fathalla, E. Automated low-cost framework for crack measurements in RC structures using deep learning approach. *Scientific Reports*, 2026. doi:10.1038/s41598-026-50880-w (coefficient of variation 21.9 % below 0.5 mm, 5.8 % from 0.5 mm).
* Deng, P. et al. 3D modeling and automated measurement of concrete cracks via Segment Anything refinement and visual inertial LiDAR fusion. *Computer-Aided Civil and Infrastructure Engineering*, 2026. doi:10.1016/j.cacaie.2026.100019 (MAE 0.09 mm on 15 cracks).

Both are context, not a head-to-head comparison (other targets, other conditions). See `docs/report/REPORT.md` and `eval/results/width_eval.md`.

## Images

* App screen recordings: the live Prohori app (https://184-194-241-186.sslip.io) driven by Playwright with the app's own demo sample photos (`service/static/samples/`, photos of the project's printed test panel taken by the author; `move-closer` and `closer` are resized versions of one of them). The camera viewfinder in the first recording is a simulated camera feed that plays one of those sample photos; no person or room is shown.
* Failure-gallery images: `docs/exhibits/gallery/` (overlays produced by the Prohori pipeline on the same sample photos or synthetic degradations of them).
* Crack-comparator illustration (`assets/cards/crack_comparator.png`): original vector drawing made for this video; not a copy of any product.
* Charts: regenerated from the repository's result files by `tools/video_charts.py`; diagrams from `docs/figures/*.svg`.
* QR code: generated with the `qrcode` Python package for the live-app URL.

## Software and fonts

* Fonts: Geist and Geist Mono (SIL Open Font License 1.1), self-hosted in `service/static/fonts/`. Icon in cards: the Prohori app icon.
* Phosphor icons (MIT) inside the app UI.
* Playwright (Apache-2.0) with Chromium for screen recording and card rendering; FFmpeg for encoding; Matplotlib, NumPy, SciPy, Pillow, OpenCV for charts and figures.
* OpenCV 5 and COOL (Cloud Optimized OpenCV, AWS Marketplace) as described in `eval/results/cool/`.

## Music / sound

None in these assets. If music is added in the final edit, record its licence here.
