# Local face detector

`face_detection_yunet_2023mar.onnx` is the OpenCV 4.x YuNet model from
[OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet).
It is distributed under the accompanying MIT license.

SHA-256: `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`

The backend loads this 232,589-byte model locally by default. No download or
new Python dependency is needed at runtime. `OPENCV_FACE_DETECTOR_MODEL` can
still override its path. The optional face parser remains configurable.
