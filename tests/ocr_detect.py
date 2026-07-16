"""使用 ONNX Runtime 进行 OCR 文字识别（PaddleOCR 模型，不依赖 paddle / torch）"""
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent

# 模型路径
DET_MODEL_PATH = ROOT / "weights" / "rapidocr" / "ch_PP-OCRv4_det_infer.onnx"
REC_MODEL_PATH = ROOT / "weights" / "rapidocr" / "ch_PP-OCRv4_rec_infer.onnx"
CLS_MODEL_PATH = ROOT / "weights" / "rapidocr" / "ch_ppocr_mobile_v2.0_cls_infer.onnx"

# 输入图片
IMAGE_PATH = ROOT / "tests" / "images" / "a1.png"

# 输出目录
OUTPUT_DIR = ROOT / "tests" / "outputs"

# 检测参数
DET_LIMIT_SIDE_LEN = 960
DET_BOX_THRESH = 0.3
DET_UNCLIP_RATIO = 1.6

# 识别参数
REC_BATCH_SIZE = 6
REC_IMG_H = 48

# 分类阈值
CLS_THRESH = 0.9

# 字符集路径
CHARSET_PATH = ROOT / "weights" / "rapidocr" / "ppocr_keys_v1.txt"


def load_charset() -> list[str]:
    """加载字符集"""
    if CHARSET_PATH.exists():
        with open(CHARSET_PATH, "r", encoding="utf-8") as f:
            return [line.rstrip("\n") for line in f]
    print("警告: 字典文件不存在，使用内置字符集（可能不完整）")
    return None


class TextDetector:
    """文字检测器"""

    def __init__(self, model_path: str):
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    def detect(self, image: np.ndarray) -> list[np.ndarray]:
        """检测文字区域，返回四边形框列表"""
        h, w = image.shape[:2]

        # 计算缩放比例
        ratio = 1.0
        max_side = max(h, w)
        if max_side > DET_LIMIT_SIDE_LEN:
            ratio = DET_LIMIT_SIDE_LEN / max_side

        resize_h = int(h * ratio)
        resize_w = int(w * ratio)

        # 确保是 32 的倍数
        resize_h = max(32, ((resize_h + 31) // 32) * 32)
        resize_w = max(32, ((resize_w + 31) // 32) * 32)

        # 缩放图片
        img_resized = cv2.resize(image, (resize_w, resize_h))

        # 归一化: mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
        img_norm = img_resized.astype(np.float32) / 255.0
        img_norm = (img_norm - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img_norm = img_norm.transpose(2, 0, 1)[np.newaxis, ...]

        # 推理
        outputs = self.session.run(None, {"x": img_norm})
        pred = outputs[0][0, 0]  # [H, W]

        # 二值化
        mask = (pred > DET_BOX_THRESH).astype(np.uint8) * 255

        # 查找轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        boxes = []
        for contour in contours:
            if len(contour) < 4:
                continue
            # 最小外接矩形
            rect = cv2.minAreaRect(contour)
            box = cv2.boxPoints(rect)
            box = self._unclip(box, DET_UNCLIP_RATIO)

            # 映射回原图坐标
            box[:, 0] = box[:, 0] / resize_w * w
            box[:, 1] = box[:, 1] / resize_h * h

            # 确保点顺序：左上 → 右上 → 右下 → 左下
            box = self._order_points(box)
            boxes.append(box)

        return boxes

    @staticmethod
    def _unclip(box: np.ndarray, ratio: float) -> np.ndarray:
        """扩展框"""
        center = box.mean(axis=0)
        expanded = box + (box - center) * (ratio - 1.0)
        return expanded

    @staticmethod
    def _order_points(pts: np.ndarray) -> np.ndarray:
        """将四个点排序为 左上→右上→右下→左下"""
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect


class TextRecognizer:
    """文字识别器"""

    def __init__(self, model_path: str, charset: list[str]):
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.charset = charset

    def recognize(self, image: np.ndarray, text_boxes: list[np.ndarray]) -> list[dict]:
        """识别文字区域中的文字"""
        results = []
        if not text_boxes:
            return results

        # 裁剪文字区域
        crops = []
        for box in text_boxes:
            crop = self._get_rotate_crop(image, box)
            crops.append(crop)

        # 批量识别
        for i in range(0, len(crops), REC_BATCH_SIZE):
            batch = crops[i:i + REC_BATCH_SIZE]
            batch_results = self._recognize_batch(batch)
            results.extend(batch_results)

        return results

    def _get_rotate_crop(self, image: np.ndarray, box: np.ndarray) -> np.ndarray:
        """透视变换裁剪文字区域"""
        pts = box.astype(np.float32)
        width = int(max(
            np.linalg.norm(pts[0] - pts[1]),
            np.linalg.norm(pts[2] - pts[3]),
        ))
        height = int(max(
            np.linalg.norm(pts[0] - pts[3]),
            np.linalg.norm(pts[1] - pts[2]),
        ))
        dst = np.array([
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1],
        ], dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(pts, dst)
        crop = cv2.warpPerspective(image, matrix, (width, height))
        return crop

    def _recognize_batch(self, crops: list[np.ndarray]) -> list[dict]:
        """批量识别"""
        results = []
        if not crops:
            return results

        # 预处理：resize 到固定高度 48，保持宽高比
        max_width = 0
        processed = []
        for crop in crops:
            h, w = crop.shape[:2]
            ratio = w / h
            new_w = int(REC_IMG_H * ratio)
            new_w = max(1, new_w)
            max_width = max(max_width, new_w)
            resized = cv2.resize(crop, (new_w, REC_IMG_H))
            # 归一化
            resized = resized.astype(np.float32) / 255.0
            resized = (resized - 0.5) / 0.5
            resized = resized.transpose(2, 0, 1)
            processed.append(resized)

        # 统一宽度（padding）
        batch_input = np.zeros((len(processed), 3, REC_IMG_H, max_width), dtype=np.float32)
        for idx, img in enumerate(processed):
            batch_input[idx, :, :, :img.shape[2]] = img

        # 推理
        outputs = self.session.run(None, {"x": batch_input})
        preds = outputs[0]  # [B, T, 6625]

        # CTC 解码
        for pred in preds:
            text, score = self._ctc_decode(pred)
            results.append({"text": text, "confidence": score})

        return results

    def _ctc_decode(self, pred: np.ndarray) -> tuple[str, float]:
        """CTC 贪心解码

        模型输出 6625 类：index 0 = CTC blank，index 1~6624 对应 charset[0]~charset[6623]
        """
        char_indices = pred.argmax(axis=1)
        confidences = pred.max(axis=1)

        # 去重，跳过 blank (index 0)
        chars = []
        scores = []
        prev = -1
        for idx, conf in zip(char_indices, confidences):
            if idx != prev and idx > 0:
                char_idx = idx - 1  # 模型 index 1 对应 charset[0]
                if char_idx < len(self.charset):
                    chars.append(self.charset[char_idx])
                    scores.append(conf)
            prev = idx

        text = "".join(chars)
        score = float(np.mean(scores)) if scores else 0.0
        return text, score


class TextClassifier:
    """文字方向分类器"""

    def __init__(self, model_path: str):
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    def classify(self, crops: list[np.ndarray]) -> list[bool]:
        """判断文字是否需要翻转（True = 需要翻转 180 度）"""
        if not crops:
            return []

        # 预处理
        processed = []
        for crop in crops:
            resized = cv2.resize(crop, (192, 48))
            resized = resized.astype(np.float32) / 255.0
            resized = (resized - 0.5) / 0.5
            resized = resized.transpose(2, 0, 1)
            processed.append(resized)

        batch = np.stack(processed, axis=0)
        outputs = self.session.run(None, {"x": batch})
        preds = outputs[0]  # [B, 2]

        results = []
        for pred in preds:
            # softmax
            exp = np.exp(pred - pred.max())
            probs = exp / exp.sum()
            # label=1 表示需要翻转
            if probs[1] > CLS_THRESH:
                results.append(True)
            else:
                results.append(False)

        return results


def draw_results(image: np.ndarray, results: list[dict]) -> np.ndarray:
    """在图片上绘制 OCR 结果"""
    drawn = image.copy()
    for item in results:
        box = item["box"]
        text = item["text"]
        conf = item["confidence"]

        pts = box.astype(np.int32)
        cv2.polylines(drawn, [pts], True, (0, 255, 0), 2)

        # 在框上方绘制文字
        x, y = pts[0]
        label = f"{text} ({conf:.2f})"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(drawn, (x, y - th - 4), (x + tw, y), (0, 255, 0), -1)
        cv2.putText(drawn, label, (x, y - 2), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 0, 0), 1)

    return drawn


def main():
    # 检查文件
    for path in [DET_MODEL_PATH, REC_MODEL_PATH, CLS_MODEL_PATH]:
        if not path.exists():
            print(f"模型文件不存在: {path}")
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

    # 加载字符集
    charset = load_charset()
    print(f"字符集大小: {len(charset)}")

    # 1. 文字检测
    print(f"\n[1/3] 文字检测...")
    detector = TextDetector(str(DET_MODEL_PATH))
    t0 = time.perf_counter()
    text_boxes = detector.detect(image)
    t1 = time.perf_counter()
    print(f"  检测到 {len(text_boxes)} 个文字区域, 耗时: {(t1 - t0) * 1000:.1f}ms")

    if not text_boxes:
        print("未检测到文字区域")
        return

    # 2. 方向分类
    print(f"\n[2/3] 方向分类...")
    classifier = TextClassifier(str(CLS_MODEL_PATH))
    crops = []
    for box in text_boxes:
        crop = _get_rotate_crop_raw(image, box)
        crops.append(crop)

    t0 = time.perf_counter()
    flip_flags = classifier.classify(crops)
    t1 = time.perf_counter()
    print(f"  分类耗时: {(t1 - t0) * 1000:.1f}ms")

    # 翻转需要翻转的图片
    for i, flip in enumerate(flip_flags):
        if flip:
            crops[i] = cv2.rotate(crops[i], cv2.ROTATE_180)

    # 3. 文字识别
    print(f"\n[3/3] 文字识别...")
    recognizer = TextRecognizer(str(REC_MODEL_PATH), charset)
    t0 = time.perf_counter()
    rec_results = recognizer.recognize(image, text_boxes)
    t1 = time.perf_counter()
    print(f"  识别耗时: {(t1 - t0) * 1000:.1f}ms")

    # 合并结果
    results = []
    for i, (box, rec) in enumerate(zip(text_boxes, rec_results)):
        results.append({
            "box": box,
            "text": rec["text"],
            "confidence": rec["confidence"],
        })

    # 打印结果
    print(f"\n识别到 {len(results)} 条文字:")
    for j, item in enumerate(results):
        box = item["box"]
        print(f"  [{j}] \"{item['text']}\" (置信度={item['confidence']:.4f}) "
              f"坐标=({box[0][0]:.0f},{box[0][1]:.0f})")

    # 绘制并保存
    result_image = draw_results(image, results)
    save_path = OUTPUT_DIR / "a1_ocr_result.jpg"
    cv2.imwrite(str(save_path), result_image)
    print(f"\n结果已保存: {save_path}")


def _get_rotate_crop_raw(image: np.ndarray, box: np.ndarray) -> np.ndarray:
    """透视变换裁剪（用于分类器）"""
    pts = box.astype(np.float32)
    width = int(max(
        np.linalg.norm(pts[0] - pts[1]),
        np.linalg.norm(pts[2] - pts[3]),
    ))
    height = int(max(
        np.linalg.norm(pts[0] - pts[3]),
        np.linalg.norm(pts[1] - pts[2]),
    ))
    dst = np.array([
        [0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1],
    ], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(pts, dst)
    return cv2.warpPerspective(image, matrix, (width, height))


if __name__ == "__main__":
    main()
