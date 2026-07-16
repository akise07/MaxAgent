"""使用 ONNX Runtime 进行图标检测（不依赖 ultralytics / torch）"""
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent

# 模型路径
MODEL_PATH = ROOT / "weights" / "icon_detect" / "model.onnx"

# 输入图片
IMAGE_PATH = ROOT / "tests" / "images" / "a1.png"

# 输出目录
OUTPUT_DIR = ROOT / "tests" / "outputs"

# 模型输入尺寸
INPUT_SIZE = (640, 640)

# 置信度阈值
CONF_THRESHOLD = 0.3

# NMS IoU 阈值
IOU_THRESHOLD = 0.45


def preprocess(image: np.ndarray) -> tuple[np.ndarray, float, float, int, int]:
    """预处理：resize + padding 到 640x640，归一化，转 CHW"""
    h, w = image.shape[:2]
    # 计算缩放比例（保持宽高比，长边缩放到 640）
    scale = min(INPUT_SIZE[0] / w, INPUT_SIZE[1] / h)
    new_w, new_h = int(w * scale), int(h * scale)

    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    # 创建 640x640 画布并居中放置
    canvas = np.full((INPUT_SIZE[1], INPUT_SIZE[0], 3), 114, dtype=np.uint8)
    pad_x = (INPUT_SIZE[0] - new_w) // 2
    pad_y = (INPUT_SIZE[1] - new_h) // 2
    canvas[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized

    # 归一化到 [0, 1]，转 CHW，加 batch 维度
    blob = canvas.astype(np.float32) / 255.0
    blob = blob.transpose(2, 0, 1)[np.newaxis, ...]

    return blob, scale, float(pad_x), float(pad_y), new_w, new_h


def postprocess(output: np.ndarray, scale: float, pad_x: float, pad_y: float,
                orig_w: int, orig_h: int) -> list[dict]:
    """后处理：解析输出 → NMS → 映射回原图坐标"""
    # output shape: [1, 5, 8400] → [8400, 5]
    preds = output[0].transpose(1, 0)  # [8400, 5]

    # 提取坐标和置信度
    boxes_xywh = preds[:, :4]   # cx, cy, w, h（模型内部坐标）
    scores = preds[:, 4]        # objectness

    # 置信度过滤
    mask = scores > CONF_THRESHOLD
    boxes_xywh = boxes_xywh[mask]
    scores = scores[mask]

    if len(boxes_xywh) == 0:
        return []

    # xywh → xyxy（模型内部坐标）
    boxes = np.zeros_like(boxes_xywh)
    boxes[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2  # x1
    boxes[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2  # y1
    boxes[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2  # x2
    boxes[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2  # y2

    # 映射回原图坐标（去掉 padding，除以 scale）
    boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad_x) / scale
    boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad_y) / scale

    # 裁剪到图片范围内
    boxes[:, 0] = np.clip(boxes[:, 0], 0, orig_w)
    boxes[:, 1] = np.clip(boxes[:, 1], 0, orig_h)
    boxes[:, 2] = np.clip(boxes[:, 2], 0, orig_w)
    boxes[:, 3] = np.clip(boxes[:, 3], 0, orig_h)

    # NMS
    indices = cv2.dnn.NMSBoxes(
        bboxes=boxes.tolist(),
        scores=scores.tolist(),
        score_threshold=CONF_THRESHOLD,
        nms_threshold=IOU_THRESHOLD,
    )

    results = []
    if len(indices) > 0:
        for idx in indices.flatten():
            results.append({
                "bbox": boxes[idx].tolist(),
                "confidence": float(scores[idx]),
            })

    return results


def draw_results(image: np.ndarray, detections: list[dict]) -> np.ndarray:
    """在图片上绘制检测框"""
    drawn = image.copy()
    for det in detections:
        x1, y1, x2, y2 = map(int, det["bbox"])
        conf = det["confidence"]
        cv2.rectangle(drawn, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(drawn, (x1, y1 - th - 4), (x1 + tw, y1), (0, 255, 0), -1)
        cv2.putText(drawn, label, (x1, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 0, 0), 1)
    return drawn


def main():
    if not MODEL_PATH.exists():
        print(f"模型文件不存在: {MODEL_PATH}")
        sys.exit(1)

    if not IMAGE_PATH.exists():
        print(f"图片文件不存在: {IMAGE_PATH}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 读取图片
    image = cv2.imread(str(IMAGE_PATH))
    if image is None:
        print(f"无法读取图片: {IMAGE_PATH}")
        sys.exit(1)
    orig_h, orig_w = image.shape[:2]
    print(f"图片尺寸: {orig_w}x{orig_h}")

    # 预处理
    blob, scale, pad_x, pad_y, new_w, new_h = preprocess(image)

    # ONNX 推理
    print(f"加载模型: {MODEL_PATH}")
    session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])

    print("推理中...")
    t0 = time.perf_counter()
    outputs = session.run(None, {"images": blob})
    t1 = time.perf_counter()
    print(f"推理耗时: {(t1 - t0) * 1000:.1f}ms")

    # 后处理
    detections = postprocess(outputs[0], scale, pad_x, pad_y, orig_w, orig_h)

    print(f"检测到 {len(detections)} 个图标:")
    for j, det in enumerate(detections):
        x1, y1, x2, y2 = det["bbox"]
        print(f"  [{j}] 置信度={det['confidence']:.4f}, "
              f"坐标=({x1:.0f}, {y1:.0f}, {x2:.0f}, {y2:.0f})")

    # 绘制并保存结果
    result_image = draw_results(image, detections)
    save_path = OUTPUT_DIR / "a1_result.jpg"
    cv2.imwrite(str(save_path), result_image)
    print(f"结果已保存: {save_path}")


if __name__ == "__main__":
    main()
