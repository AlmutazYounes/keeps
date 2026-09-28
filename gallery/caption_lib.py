"""Describe a photo with Florence-2 so the gallery can search what is in it."""

import subprocess
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

ROOT = Path("/Volumes/SamsungT7/Google Photos Backup")
PHOTOS = ROOT / "Photos"
MODEL = ROOT / "gallery" / "models" / "florence2"
ONNX = MODEL / "onnx"
PROMPT = "Describe with a paragraph what is shown in the image."
EOS = 2
MAX_NEW_TOKENS = 64
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def session(path):
    options = ort.SessionOptions()
    options.intra_op_num_threads = 6
    options.inter_op_num_threads = 1
    return ort.InferenceSession(
        str(path),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )


def load_bgr(path):
    ext = path.suffix.lower()
    src = path
    tmp = None
    if ext in {".heic", ".heif", ".tif", ".tiff", ".bmp"}:
        tmp = ROOT / "gallery" / "cache" / "_caption.jpg"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["sips", "-s", "format", "jpeg", "--out", str(tmp), str(path)],
            capture_output=True,
        )
        src = tmp
    image = cv2.imread(str(src))
    if tmp is not None:
        tmp.unlink(missing_ok=True)
    return image


def pixels(image):
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (768, 768), interpolation=cv2.INTER_CUBIC)
    values = resized.astype(np.float32) / 255.0
    values = (values - MEAN) / STD
    return np.transpose(values, (2, 0, 1))[None]


def past_from(outputs, names):
    feed = {}
    for name, value in zip(names, outputs):
        feed[name.replace("present.", "past_key_values.")] = value
    return feed


class Captioner:
    def __init__(self):
        self.vision = session(ONNX / "vision_encoder_q4f16.onnx")
        self.embed = session(ONNX / "embed_tokens_q4f16.onnx")
        self.encoder = session(ONNX / "encoder_model_q4f16.onnx")
        self.prefill = session(ONNX / "decoder_model_q4f16.onnx")
        self.decode = session(ONNX / "decoder_model_merged_q4.onnx")
        self.tokenizer = Tokenizer.from_file(str(MODEL / "tokenizer.json"))
        self.prompt_ids = self.prompt_tokens()
        self.prefill_names = [item.name for item in self.prefill.get_outputs()][1:]
        self.decode_names = [item.name for item in self.decode.get_outputs()][1:]

    def prompt_tokens(self):
        ids = self.tokenizer.encode(PROMPT).ids
        if not ids or ids[0] != 0:
            ids = [0] + ids
        if ids[-1] != EOS:
            ids = ids + [EOS]
        return np.array([ids], dtype=np.int64)

    def caption_image(self, image):
        features = self.vision.run(None, {"pixel_values": pixels(image)})[0]
        prompt = self.embed.run(None, {"input_ids": self.prompt_ids})[0]
        embeds = np.concatenate([features, prompt], axis=1)
        mask = np.ones((1, embeds.shape[1]), dtype=np.int64)
        hidden = self.encoder.run(None, {
            "inputs_embeds": embeds,
            "attention_mask": mask,
        })[0]
        step = self.prefill.run(None, {
            "inputs_embeds": embeds[:, -1:],
            "encoder_hidden_states": hidden,
            "encoder_attention_mask": mask,
        })
        tokens = []
        cache = past_from(step[1:], self.prefill_names)
        encoder_cache = {
            key: value.copy()
            for key, value in cache.items()
            if ".encoder." in key
        }
        for _ in range(MAX_NEW_TOKENS):
            token = int(np.argmax(step[0][0, -1]))
            if token == EOS:
                break
            tokens.append(token)
            nxt = self.embed.run(None, {"input_ids": np.array([[token]], dtype=np.int64)})[0]
            feed = {
                "use_cache_branch": np.array([True], dtype=np.bool_),
                "inputs_embeds": nxt,
                "encoder_hidden_states": hidden,
                "encoder_attention_mask": mask,
            }
            feed.update(cache)
            step = self.decode.run(None, feed)
            cache = past_from(step[1:], self.decode_names)
            cache.update(encoder_cache)
        text = self.tokenizer.decode(tokens, skip_special_tokens=True).strip()
        if text.lower().startswith(PROMPT.lower()):
            text = text[len(PROMPT):].strip(" .:")
        return " ".join(text.split())

    def caption_path(self, path):
        image = load_bgr(Path(path))
        if image is None:
            return ""
        return self.caption_image(image)
