import os
import io

import cv2
import numpy as np
import onnxruntime as ort

WIDTH = 140
HEIGHT = 48
ALLOWED_CHARS = '2345679ACDFGHKMNPQRTVWYZ'
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'models', 'thsrc_captcha.onnx')

_session = None


def _get_session() -> ort.InferenceSession:
    global _session
    if _session is None:
        _session = ort.InferenceSession(MODEL_PATH, providers=['CPUExecutionProvider'])
    return _session


def _poly_features_deg2(x: np.ndarray) -> np.ndarray:
    x = x.flatten().astype(np.float64)
    return np.column_stack([np.ones_like(x), x, x ** 2])


def _lstsq_predict(x_train: np.ndarray, y_train: np.ndarray, x_pred: np.ndarray) -> np.ndarray:
    w = np.linalg.lstsq(x_train, y_train, rcond=None)[0]
    return x_pred @ w


def _denoise(img_bgr: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoisingColored(img_bgr, None, 30, 30, 7, 21)


def _threshold_inv(img_bgr: np.ndarray) -> np.ndarray:
    _, thresh = cv2.threshold(img_bgr, 127, 255, cv2.THRESH_BINARY_INV)
    return thresh


def _find_regression(img_thresh: np.ndarray):
    gray = cv2.cvtColor(img_thresh, cv2.COLOR_BGR2GRAY)
    gray[:, 14:WIDTH - 7] = 0
    imagedata = np.where(gray == 255)
    if len(imagedata[0]) == 0:
        return None
    x = np.array([imagedata[1]])
    y = HEIGHT - imagedata[0]
    x_features = _poly_features_deg2(x[0])
    return x_features, y


def _remove_curve(img_thresh: np.ndarray, regr_data) -> np.ndarray:
    newimg = cv2.cvtColor(img_thresh, cv2.COLOR_BGR2GRAY)
    if regr_data is None:
        return newimg
    x_features, y = regr_data
    w = np.linalg.lstsq(x_features, y, rcond=None)[0]
    x2 = np.arange(WIDTH)
    x2_features = _poly_features_deg2(x2)
    predictions = x2_features @ w
    offset = 4
    for i in range(WIDTH):
        pos = HEIGHT - int(round(predictions[i]))
        top = max(0, pos - offset)
        bot = min(HEIGHT, pos + offset)
        newimg[top:bot, i] = 255 - newimg[top:bot, i]
    return newimg


def _preprocess(img_bgr: np.ndarray) -> np.ndarray:
    img = cv2.resize(img_bgr, (WIDTH, HEIGHT))
    denoised = _denoise(img)
    thresh = _threshold_inv(denoised)
    regr_data = _find_regression(thresh)
    result = _remove_curve(thresh, regr_data)
    return result


MIN_CONFIDENCE = 0.8


class LowConfidenceError(Exception):
    pass


def _predict(img_bgr_48x140: np.ndarray) -> str:
    normalized = img_bgr_48x140.astype(np.float32) / 255.0
    batch = np.expand_dims(normalized, axis=0)

    session = _get_session()
    input_name = session.get_inputs()[0].name
    output_names = [o.name for o in session.get_outputs()]
    predictions = session.run(output_names, {input_name: batch})

    result = ''
    for i, pred in enumerate(predictions):
        prob = pred[0]
        char_idx = np.argmax(prob)
        confidence = prob[char_idx]
        if confidence < MIN_CONFIDENCE:
            raise LowConfidenceError(
                f'字元 {i+1} 信心度過低 ({confidence:.2f}), 可能包含模型不認識的字元'
            )
        result += ALLOWED_CHARS[char_idx]
    return result


def solve(img_bytes: bytes, debug: bool = False) -> str:
    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
    img_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    img_bgr = cv2.resize(img_bgr, (WIDTH, HEIGHT))

    if debug:
        cv2.imwrite('/tmp/captcha_raw.jpg', img_bgr)

    gray = _preprocess(img_bgr)
    preprocessed_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    if debug:
        cv2.imwrite('/tmp/captcha_preprocessed.jpg', gray)

    return _predict(preprocessed_bgr)
