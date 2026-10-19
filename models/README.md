# Models

| File | Used by | Source | License | SHA-256 |
|---|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` (232,589 bytes) | `src/prohori/redact.py` (OpenCV `cv2.FaceDetectorYN`) | https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx (official OpenCV Model Zoo, `models/face_detection_yunet`) | MIT (see the zoo's model README) | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |

Reference: W. Wu, H. Peng, S. Yu, "YuNet: A Tiny Millisecond-level Face Detector", *Machine Intelligence Research* 20(5):656-665, 2023, DOI 10.1007/s11633-023-1423-y.

Re-download and verify:

```bash
curl -L -o models/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
sha256sum models/face_detection_yunet_2023mar.onnx   # must equal the hash above
```

The service looks for the file at `models/face_detection_yunet_2023mar.onnx` (override with env `PROHORI_YUNET_MODEL`).
If it is missing, face redaction reports `unavailable` and the service refuses to persist evidence images (fail closed).
