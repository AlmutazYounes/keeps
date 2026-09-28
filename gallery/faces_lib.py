"""Detect faces, embed them, and group the same person together."""

import subprocess

import faces_db
import library_root
import model_choices

import cv2
import numpy as np
import onnxruntime as ort

PHOTOS = library_root.photos_dir()
MODELS = library_root.program_dir() / "models"
CROP_DIR = library_root.data_dir() / "cache" / "faces"
DET_PATH = MODELS / "10g_bnkps.onnx"
REC_PATH = MODELS / "arcface_w600k_r50_batch.onnx"


def det_path():
    return model_choices.model_file("faces_detect")


def rec_path():
    return model_choices.model_file("faces_embed")

INPUT_SIZE = (640, 640)
DET_THRESH = 0.55
NMS_THRESH = 0.4
MATCH_THRESH = 0.42
MAX_SIDE = 1600
STRIDES = (8, 16, 32)
ARC_DST = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


def session(path):
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def load_bgr(path):
    ext = path.suffix.lower()
    if ext in {".heic", ".heif", ".tif", ".tiff", ".bmp"}:
        tmp = CROP_DIR / "_decode.jpg"
        CROP_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["sips", "-s", "format", "jpeg", "--out", str(tmp), str(path)],
            capture_output=True,
        )
        image = cv2.imread(str(tmp))
        tmp.unlink(missing_ok=True)
    else:
        image = cv2.imread(str(path))
    if image is None:
        return None
    height, width = image.shape[:2]
    scale = MAX_SIDE / max(height, width)
    if scale < 1:
        image = cv2.resize(image, (int(width * scale), int(height * scale)))
    return image


def sigmoid(values):
    return 1.0 / (1.0 + np.exp(-values))


def nms(boxes, scores, thresh):
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes.T
    areas = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        index = int(order[0])
        keep.append(index)
        rest = order[1:]
        if rest.size == 0:
            break
        xx1 = np.maximum(x1[index], x1[rest])
        yy1 = np.maximum(y1[index], y1[rest])
        xx2 = np.minimum(x2[index], x2[rest])
        yy2 = np.minimum(y2[index], y2[rest])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        union = areas[index] + areas[rest] - inter + 1e-6
        order = rest[inter / union <= thresh]
    return keep


def prepare_det(image):
    height, width = image.shape[:2]
    in_w, in_h = INPUT_SIZE
    ratio = height / width
    model_ratio = in_h / in_w
    if ratio > model_ratio:
        new_h = in_h
        new_w = int(new_h / ratio)
    else:
        new_w = in_w
        new_h = int(new_w * ratio)
    resized = cv2.resize(image, (new_w, new_h))
    canvas = np.zeros((in_h, in_w, 3), dtype=np.uint8)
    canvas[:new_h, :new_w] = resized
    blob = cv2.dnn.blobFromImage(canvas, 1.0 / 128.0, INPUT_SIZE, (127.5, 127.5, 127.5), swapRB=True)
    return blob, float(new_h) / height


def anchor_centers(height, width, stride, num_anchors):
    centers = np.stack(np.mgrid[:height, :width][::-1], axis=-1).astype(np.float32)
    centers = (centers * stride).reshape((-1, 2))
    if num_anchors > 1:
        centers = np.stack([centers] * num_anchors, axis=1).reshape((-1, 2))
    return centers


def detect_faces(det_session, image):
    blob, scale = prepare_det(image)
    outputs = det_session.run(None, {"input.1": blob})
    scores_all = []
    boxes_all = []
    kps_all = []
    for idx, stride in enumerate(STRIDES):
        scores = outputs[idx].reshape(-1)
        if scores.max() > 1.0 or scores.min() < 0.0:
            scores = sigmoid(scores)
        boxes = outputs[idx + 3] * stride
        kps = outputs[idx + 6] * stride
        grid = INPUT_SIZE[0] // stride
        num_anchors = boxes.shape[0] // (grid * grid)
        centers = anchor_centers(grid, grid, stride, num_anchors)
        boxes = distance2bbox(centers, boxes)
        kps = distance2kps(centers, kps).reshape((-1, 5, 2))
        keep = np.where(scores >= DET_THRESH)[0]
        scores_all.append(scores[keep])
        boxes_all.append(boxes[keep] / scale)
        kps_all.append(kps[keep] / scale)
    scores = np.concatenate(scores_all)
    boxes = np.concatenate(boxes_all)
    kps = np.concatenate(kps_all)
    if scores.size == 0:
        return []
    keep = nms(boxes, scores, NMS_THRESH)
    height, width = image.shape[:2]
    faces = []
    for index in keep:
        x1, y1, x2, y2 = boxes[index]
        if (x2 - x1) < 24 or (y2 - y1) < 24:
            continue
        x1 = float(np.clip(x1, 0, width - 1))
        y1 = float(np.clip(y1, 0, height - 1))
        x2 = float(np.clip(x2, 0, width - 1))
        y2 = float(np.clip(y2, 0, height - 1))
        faces.append({
            "box": (x1, y1, x2, y2),
            "kps": kps[index],
            "score": float(scores[index]),
        })
        if len(faces) >= 12:
            break
    return faces


def distance2bbox(points, distance):
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def distance2kps(points, distance):
    preds = []
    for offset in range(0, distance.shape[1], 2):
        preds.append(points[:, 0] + distance[:, offset])
        preds.append(points[:, 1] + distance[:, offset + 1])
    return np.stack(preds, axis=-1)


def align_face(image, landmarks):
    matrix, _ = cv2.estimateAffinePartial2D(landmarks.astype(np.float32), ARC_DST, method=cv2.LMEDS)
    if matrix is None:
        return None
    return cv2.warpAffine(image, matrix, (112, 112), borderValue=0.0)


def embed_face(rec_session, aligned):
    blob = cv2.dnn.blobFromImage(aligned, 1.0 / 128.0, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
    vector = rec_session.run(None, {"input.1": blob})[0][0]
    norm = np.linalg.norm(vector) + 1e-8
    return (vector / norm).astype(np.float32)


def square_crop(image, box):
    height, width = image.shape[:2]
    x1, y1, x2, y2 = box
    side = max(x2 - x1, y2 - y1) * 1.35
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    left = int(max(0, cx - side / 2))
    top = int(max(0, cy - side / 2))
    right = int(min(width, cx + side / 2))
    bottom = int(min(height, cy + side / 2))
    crop = image[top:bottom, left:right]
    if crop.size == 0:
        return None
    return cv2.resize(crop, (192, 192))


def cluster_faces(records):
    clusters = []
    ordered = sorted(records, key=lambda item: item["score"], reverse=True)
    for record in ordered:
        vector = record["embedding"]
        best_index = -1
        best_score = MATCH_THRESH
        for index, group in enumerate(clusters):
            center = group["center"]
            score = float(np.dot(vector, center))
            if score > best_score:
                best_index = index
                best_score = score
        if best_index < 0:
            clusters.append({"members": [record], "center": vector.copy()})
            continue
        group = clusters[best_index]
        group["members"].append(record)
        center = np.mean([item["embedding"] for item in group["members"]], axis=0)
        group["center"] = center / (np.linalg.norm(center) + 1e-8)
    clusters.sort(key=lambda group: len(group["members"]), reverse=True)
    return clusters


def save_results(records, scanned):
    clusters = cluster_faces(records)
    if faces_db.DB_PATH.exists():
        faces_db.DB_PATH.unlink()
    CROP_DIR.mkdir(parents=True, exist_ok=True)
    for old in CROP_DIR.glob("*.jpg"):
        old.unlink()
    conn = faces_db.connect()
    for person_id, group in enumerate(clusters, start=1):
        conn.execute(
            "INSERT INTO people(id, name, cover_face_id) VALUES (?, '', NULL)",
            (person_id,),
        )
        cover_id = None
        cover_crop = None
        best_score = -1.0
        for record in group["members"]:
            cursor = conn.execute(
                """
                INSERT INTO faces(relpath, x1, y1, x2, y2, score, person_id, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["relpath"],
                    record["x1"], record["y1"], record["x2"], record["y2"],
                    record["score"], person_id, record["embedding"].tobytes(),
                ),
            )
            if record["score"] > best_score and record.get("crop") is not None:
                best_score = record["score"]
                cover_id = cursor.lastrowid
                cover_crop = record["crop"]
        if cover_id and cover_crop is not None:
            cv2.imwrite(str(CROP_DIR / f"{cover_id}.jpg"), cover_crop)
            conn.execute(
                "UPDATE people SET cover_face_id = ? WHERE id = ?",
                (cover_id, person_id),
            )
    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('scanned', ?)",
        (str(scanned),),
    )
    conn.commit()
    faces_db.export_metadata(conn)
    conn.close()
    return len(clusters)
