"""
B站文字点选: 参照极验3点选策略
YOLO全图检测 → 按框大小分题目/游戏 → Siamese贪心匹配
"""
import numpy as np
import cv2
import onnxruntime as ort
from pathlib import Path

BASE = Path(__file__).parent
MODEL_DIR = BASE / "model"
NUM_THREADS = 4
INPUT_SIZE = 105  # siamese输入尺寸


def letterbox(img, new_shape=(640, 640), color=(114, 114, 114)):
    shape = img.shape[:2]
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    nu = (int(round(shape[1] * r)), int(round(shape[0] * r)))
    dw, dh = new_shape[1] - nu[0], new_shape[0] - nu[1]
    dw1, dw2, dh1, dh2 = dw // 2, dw - dw // 2, dh // 2, dh - dh // 2
    img = cv2.resize(img, nu)
    img = cv2.copyMakeBorder(img, dh1, dh2, dw1, dw2, cv2.BORDER_CONSTANT, value=color)
    return img, (r, dw1, dh1)


class CaptchaSolver:
    def __init__(self):
        opt = ort.SessionOptions()
        opt.intra_op_num_threads = NUM_THREADS
        self.yolo = ort.InferenceSession(str(MODEL_DIR / "yolov8s.onnx"), opt,
                                          providers=['CPUExecutionProvider'])
        self.siam = ort.InferenceSession(str(MODEL_DIR / "siamese.onnx"), opt,
                                          providers=['CPUExecutionProvider'])

    def predict(self, img_path):
        if isinstance(img_path, (str, Path)):
            data = np.fromfile(str(img_path), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        else:
            img = img_path

        h, w = img.shape[:2]

        # 1. YOLO检测
        lb, (r, pdx, pdy) = letterbox(img)
        inp = cv2.cvtColor(lb, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        inp = inp.transpose(2, 0, 1)[None]
        preds = self.yolo.run(None, {self.yolo.get_inputs()[0].name: inp})[0]
        preds = preds[0].transpose()

        cx, cy, bw, bh = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
        sc = preds[:, 4]
        x1 = ((cx - bw / 2) - pdx) / r
        y1 = ((cy - bh / 2) - pdy) / r
        x2 = ((cx + bw / 2) - pdx) / r
        y2 = ((cy + bh / 2) - pdy) / r

        # 转成 [x,y,w,h] 并过滤
        boxes, scores = [], []
        for i in range(len(sc)):
            if sc[i] >= 0.5:
                x, y, bw_i, bh_i = x1[i], y1[i], x2[i] - x1[i], y2[i] - y1[i]
                boxes.append([int(x), int(y), int(bw_i), int(bh_i)])
                scores.append(float(sc[i]))

        if not boxes:
            return []

        # 分开做NMS: 游戏区(IoU=0.5) 题目区(IoU=0.2)
        quest_mask = np.array([b[1] + b[3] - 5 >= h - 40 for b in boxes])
        game_mask = ~quest_mask

        indices = []
        for mask, iou_th in [(game_mask, 0.5), (quest_mask, 0.2)]:
            m_idx = np.where(mask)[0]
            if len(m_idx) == 0: continue
            subset_boxes = [boxes[i] for i in m_idx]
            subset_scores = [scores[i] for i in m_idx]
            nms_idx = cv2.dnn.NMSBoxes(subset_boxes, subset_scores, 0.5, iou_th)
            if len(nms_idx) > 0:
                indices.extend(m_idx[np.array(nms_idx).flatten()])

        if not indices:
            return []

        small, big = {}, []
        for i in indices:
            b = boxes[i]
            if b[1] + b[3] - 5 >= h - 40:
                small[b[0]] = b
            else:
                big.append(b)

        if not small or not big:
            return []

        # 3. Siamese匹配
        siam_in = [i.name for i in self.siam.get_inputs()]

        def prep(c):
            return np.expand_dims(
                np.transpose(cv2.resize(c, (INPUT_SIZE, INPUT_SIZE)) / 255.0, (2, 0, 1)),
                0).astype(np.float32)

        click_points = []
        for k in sorted(small):  # 按x排序
            img1 = prep(img[small[k][1]:small[k][1] + small[k][3],
                            small[k][0]:small[k][0] + small[k][2]])
            for b in big:
                pt = [b[0] + b[2] // 2, b[1] + b[3] // 2]
                if pt in click_points:
                    continue
                img2 = prep(img[b[1]:b[1] + b[3], b[0]:b[0] + b[2]])
                feeds = {siam_in[0]: img1, siam_in[1]: img2}
                out = self.siam.run(None, feeds)[0][0, 0]
                if 1 / (1 + np.exp(-out)) >= 0.1:  # sigmoid >= 0.1
                    click_points.append(pt)
                    break

        return click_points


_solver = None


def predict(img_path):
    global _solver
    if _solver is None:
        _solver = CaptchaSolver()
    return _solver.predict(img_path)


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "test_images/dx_img.png"
    coords = predict(p)
    print(f"Coords: {coords}")
    for i, pt in enumerate(coords):
        print(f"  {i + 1}: ({pt[0]}, {pt[1]})")

