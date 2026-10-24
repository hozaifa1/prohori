# PROHORI — Datasets (segmentation harness, synthetic generator)

*Retrieved 2026-10-19 by the D12/D11 work. Copy of `data/datasets/MANIFEST.md` (the data itself is git-ignored). Loader: `src/prohori/datasets.py`; metrics: `src/prohori/segeval.py`; baseline: `eval/results/seg_baseline_classical.{csv,md}`.*

All numbers below were counted from the files on disk (`python -c "from prohori import datasets as D; D.count(name, split)"`). Checksums are SHA-256 of the file as downloaded unless marked MD5.

## 1. Segmentation benchmarks

| name (`datasets.py`) | what | splits obtained (official) | status |
|---|---|---|---|
| `crack500` | Crack500, phone photos of asphalt, the 3,368-image cropped release used by SCSegamba / EfficientCrackNet (S1, S2) | train 1,896 / val 348 / test 1,124 (the authors' `train.txt`, `val.txt`, `test.txt`) | complete |
| `deepcrack` | DeepCrack, concrete / brick / asphalt | train 300 / test 237 | complete |
| `tut` | TUT (CrackSCF, S3): 8 cluttered scenes | train 987 / val 139 / test 282 (= the published 1,408) | complete |
| `facade390` | Facade390 (CrackSAM, S6): UAV facade cracks with stains, paint, joints | 390 images, no train/val (zero-shot set), 448x448; `images_HR` also kept | complete |
| `road420` | Road420 (CrackSAM, S6): iPhone road cracks | 420 images, zero-shot set, 448x448 | complete (HR images left in the archive, see below) |
| `cfd`, `ael`, `cracktree200`, `gaps384` | public constituents of OmniCrack30k (S10): CFD 118, AEL 58 (of 68 listed: the other 10 have no mask in the release), CrackTree200 206, GAPs384 (cropped) 509 | evaluation-only sets, no official split: all images with a mask = `test` | complete |
| `crackseg9k` | CrackSeg9k (Kulkarni et al., CVPRW 2022): 9,159 images from 10 merged sources resized to 400x400 | the authors' `train.txt` / `test.txt`: 7,332 / 1,827 | complete |
| `omni_public` | **substitute for OmniCrack30k**: union of `cfd`, `ael`, `cracktree200`, `gaps384`, `crack500`, `deepcrack` test sets | `test` | see section 2 |

Note on TUT: the README inside the downloaded archive points to a different Google-Drive id (`1Aqv5XTa0KNnOTZMViWFWLMekv4F82vfC`) than the one this copy was fetched from (id below, as reported for github.com/Karl1109/TUT). The downloaded archive has exactly the published layout and the published 987 / 139 / 282 split, so it is taken as the TUT release; the checksum below identifies the file.

### Sources, licences, checksums

| dataset | official source (retrieved from) | licence as released | archive checksum |
|---|---|---|---|
| Crack500, CFD, AEL, CrackTree200, GAPs384 | FPHB toolbox archive `pavement crack datasets` (Yang et al., IEEE TITS 2019), Google Drive id `13_vDYl54Mrd34dddX9w4ppAEiuWv4MlD` linked from github.com/fyangneil/pavement-crack-detection (1.98 GB, only the needed members were extracted) | no licence stated; released for research | bundle `2a75847f15a4384ca37fe1b0b0cb70fb50189354638b6590d2331e5284f6b075`; members: `CRACK500/traincrop.zip d5e9eb4b…cbd`, `valcrop.zip 78974e47…43a`... (full list in `data/datasets/_dl/pavement_member_sha256.txt`) |
| DeepCrack | github.com/yhlleo/DeepCrack, `dataset/DeepCrack.zip` (Liu et al., Neurocomputing 2019) | "restricted to non-commercial research and educational purposes" (authors' README) | `ec3fc2bee3b71c2cc3c74739cbc51c97b77f78193d08ce3dda0e16d7d41bf585` |
| TUT | Google Drive id `1A-LOJzY-KLsrNCBF8MerqflGCKoiBKF-` reported for github.com/Karl1109/TUT | not stated | `bf53ef3c40e8e71354fd030b0dd57516c57826770bc7a95c34e11102eef3cf03` |
| Facade390 | Google Drive id `1P1b15kRQpVcT7cNDzZB_1vFTrN0WKPB_` from github.com/KG-TSI-Civil/CrackSAM | CC BY 4.0 (repository README) | `44604a46956f923bf73b32910a650e247201011be7161da97b7893e2bd047ee1` |
| Road420 | Google Drive id `1khUfS2uDZb5eDOhpL1qJPYsOxso7Limu` from the same repository | CC BY 4.0 | `f5a53d7cc31bed02019e9f983ce7ead97f45e165487dd09323c8e7d0540d8bbd` (2.0 GB; `images/` + `masks/` extracted, `images_HR/` not extracted for disk space; archive kept at `C:\Users\User\prohori_data\dl\Road420.bin`) |
| CrackSeg9k | Harvard Dataverse doi:10.7910/DVN/EGIEBY v4 (files `Final-Dataset-Vol1.zip`, `Final-Dataset-Vol2.zip`) | CC0 1.0 | MD5 `0ee4b33617db30612184a2700116ba4d` and `d52bccf41c081d74fe50c9feec48ca39` (match the Dataverse API); SHA-256 `a3f2f7c1c527837103b906f222ce495d187ab294389805532d14d4cedd56ff44`, `9dfbd2407b8526d4a09a044250260d2de8432265a125d0c3ab55c88f90af73f1` |

The CrackSAM citation (Ge et al., CBM 431:136573, 2024) is required by the Road420/Facade390 licence note; DeepCrack's non-commercial clause applies to anything trained or evaluated on it.

### Local layout

`data/datasets/<name>/` (git-ignored). `crackseg9k` is a directory junction to `C:\Users\User\prohori_data\datasets\CrackSeg9k` because the F: drive had under 8 GB free (2.6 GB extracted); the loader does not care. Override the root with the `PROHORI_DATASETS` environment variable.

### Conventions fixed in the loader

* masks are binarised at 127 (Facade390/Road420/CrackSeg9k masks are soft-edged because they were resized);
* the AEL ground truth is stored crack = 0 and is inverted by the loader;
* images are BGR uint8, masks bool; the loader never resizes unless `max_side` is given.

## 2. OmniCrack30k — NOT obtained (explicit)

OmniCrack30k (S10, Benz & Rodehorst, CVPRW 2024) is **not publicly downloadable**. The repository (github.com/ben-z-original/omnicrack30k) states "due to license issues, the dataset cannot openly be shared"; access is granted on request by e-mail from a university account with the subject "Access OmniCrack30k Dataset", the full name, role, institution and a link to a research page, and a promise to follow the subset licences and use it non-commercially. There is no Zenodo / HuggingFace mirror. This was not requested on Hozaifa's behalf (sending an e-mail is outside this task's authority).

**Documented substitute:** `omni_public`, the six OmniCrack30k constituents that are openly released (CFD, AEL, CrackTree200, GAPs384 here, plus Crack500 and DeepCrack as separate sets), and `crackseg9k`, which merges ten public sources (including several that OmniCrack30k also uses). The comparison to S10's numbers is therefore indicative only: it is *not* the 30,017-image benchmark and it uses neither its de-duplication nor its official split.

**If Hozaifa wants the real thing:** send the e-mail described above from his University of Dhaka address (a 2-minute task for him; he is the only one who can). After downloading, add a loader for the `--subset` layout and re-run `eval/seg_baseline.py`.

## 3. Textures for the synthetic generator (D11)

| source | what | licence | files |
|---|---|---|---|
| ambientCG (ambientcg.com) | 33 PBR material colour maps, 2K, downloaded 2026-10-19 via the ambientCG API (`/get?file=<id>_2K-JPG.zip`): Concrete 007 008 010 014 016 017 019 020 021 022 023 024 025 026 030 034 035 036 040 042A 045 046 047A 048, Plaster 001-006, PaintedPlaster 002 004 017 | **CC0 1.0** (public domain) | `data/datasets/textures_ambientcg/<id>_Color.jpg`; zip SHA-256 list below |
| used in renders | 27 of the 33: excluded after visual inspection, because they carry slab joints / planks / moss / polka dots that would be crack-like distractors: Concrete007, 008, 010, 026, 045, PaintedPlaster002 | | `TEX_EXCLUDE` in `synth.py` |

The physical size of an ambientCG tile is not published (the API returns dimension 0); `synth.py` draws an assumed tile size from 0.3-0.9 m and extends the texture below its native 0.15-0.45 mm/px resolution with calibrated fractal grain (see `research/DATA_NOTES.md`).

Crack-free patches from the segmentation datasets were *not* used as textures: their licences are research-only or unstated, their scale is unknown and the images are 400-640 px wide.

Texture zip SHA-256:

```
fd7eec4fe8a310142173696e57753c3b98c7d5291f8f049d594fec32e1d7dd98 Concrete007   d96f93a6a6f4a2f77f165e297a08846e79b64d00ea933ce914ffa8c8cf649843 Concrete008
97779b1dab596bfc4a58c09cd9bcbb9f823c6303b121b18f470acc605e5732d3 Concrete010   3944911498bf71e72376256882805b9b810aa6f3c6e2c4a6aaf1d84c7f8def09 Concrete014
9bf09f42aabe3fadd125d65c86dbec5b9d5dfe9841306b0127422911317334e7 Concrete016   a0943ade0df0b7595bbb509460ce41146e7c92345ce8507d7fda60ece18b2fc6 Concrete017
27b584111d2d0fe839163d6729272b0e7ba133b4cc257ac2747d77b8917a54b3 Concrete019   de20893481ecd9debf9b826558ac0d6fd7b4993247aa4e56c788e6a6b3a93fbf Concrete020
7f1aea7bdbb891f0ecfccba873aa4e9f28fa7fd2bc63089c4acab8264d16d1aa Concrete021   a873e11c894a2382932f941598bed705c77fe77fbbf9185398c7beca21675d6b Concrete022
c3283e223304799755cb14be29da0f70d2d6febe5e853b7d74aecd4f6ffc6079 Concrete023   e1ac3d396ed9bd53385a45505723010307e3cb022fa473fe621210e8a3d7d580 Concrete024
494cc4ff3070fe30325745fb37f7e183c421d319552d1098cc3f3b6c2cb9643d Concrete025   21724bdbafdb3eead15879f739bc6be5228d760e73052494867cd28e627c154e Concrete026
cf129c209f714650e7ad6a9dcf34b1bc31e06192db1ccf3470b754c989a3993c Concrete030   fafd7cd3aee2b703abbb12b7810ef565ab76ac7ea3b1ea9a73b088e423e670b3 Concrete034
471ae8dbc7dd6d14d8f1ae70c68d7c74f1f8995ac11315c7812af0c6bddcd393 Concrete035   231c1f965748db7ad9541f168393c638ba0e935feb3441f5c0edfb1d9cb12d8b Concrete036
f757c69e3c9e380b76bfd9fd0641f519d3717b8ecd1dd76a99e14c3a3695dd7f Concrete040   6dfa046e23c907a509e4078b85819380ffb67ab950d7f8d302689b83140ec1fa Concrete042A
06ae5a2253f1965a33b2a29e11332f6bd0717f7047c1292ec520f0fee7a9de81 Concrete045   597e009cb504219e85671ec06a375cd0cf030142749bb414990cc3dece477dde Concrete046
70a9be4b8107d641cbcb9ca3e10b09592c5f95fb8effb4305b1fe2990fac71cc Concrete047A  c61a3e7f03c625889c7fd71351a928217a15e81ea26e6f7dda16865b2882e483 Concrete048
2f1070fd546e09d3ed3a188f8e14aef11fb20af1fc90cb82a0f64f7da735a67f PaintedPlaster002  1bfce871832df77eafd4c76fcb473c2e856023b866224f5de4cb4383ae1fd0f0 PaintedPlaster004
a61330b10b1aa58410f8b60632f667e7a6d84d521bbd85cec4c4de7136d282d2 PaintedPlaster017  9894765632cfa0feb3349b581825a9c224dee9efa1cebb8aba63bd1c7bc9fc3c Plaster001
c364e72a39ea894c6455cdb2c6b584f9b94f90cd48286578427acd1be0cd489f Plaster002   7088106ca868dab12f702c1bac8dc012f445f572a3e02d5377b42ed497be1fd8 Plaster003
b92e4cbddfe65219415366ff90b50b13b80bf7827195bd98f0808bf384483e37 Plaster004   90d3f6d869c40909abddc83e716291e6a9569d67b92034ae09292399a908bea0 Plaster005
8e9cec359f0c4eab6a74bc1d923e0daa2491bab5f6a92e1347c1b95246030b03 Plaster006
```

## 4. Not downloaded here

* **krkCMd** (METRICS §1b) is fetched by another work stream into `data/datasets/krkcmd/`; this document does not cover it.
* The 2K+ original-resolution Crack500 images (`testdata.zip`, `valdata.zip`) and the FPHB model outputs inside the bundle were skipped; the cropped release is what S1/S2 evaluate on.
* The 20-odd GB of OmniCrack30k itself (section 2).
