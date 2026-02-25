"""PyTorch Dataset for labeled THSR captcha images.

Labeled images use filename convention: NNN_XXXX_hash.png
where NNN is a sequential number and XXXX is the 4-char captcha label.
"""

import os
from typing import Tuple

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from thsr_ticket.ml.captcha_solver import _preprocess
from thsr_ticket.ml.train.config import (
    ALLOWED_CHARS, HEIGHT, NUM_DIGITS, RAW_DIR, WIDTH,
)


class CaptchaDataset(Dataset):
    """Dataset that loads labeled captcha images.

    Each sample returns:
        image: float32 tensor [48, 140, 3] (HWC, normalized to [0, 1])
        labels: int64 tensor [4] (character indices into ALLOWED_CHARS)
    """

    def __init__(
        self,
        data_dir: str = RAW_DIR,
        allowed_chars: str = ALLOWED_CHARS,
        preprocess: bool = True,
    ):
        self.data_dir = data_dir
        self.allowed_chars = allowed_chars
        self.char_to_idx = {c: i for i, c in enumerate(allowed_chars)}
        self.preprocess = preprocess

        self.samples: list = []
        self._scan_labeled_files()

    def _scan_labeled_files(self) -> None:
        """Find labeled files: NNN_XXXX_hash.png (skip files with '_captcha_')."""
        for filename in os.listdir(self.data_dir):
            if not filename.endswith('.png') or '_captcha_' in filename:
                continue
            # Extract label: NNN_XXXX_hash.png -> XXXX
            parts = filename.split('_', 2)  # ['NNN', 'XXXX', 'hash.png']
            if len(parts) < 2:
                continue
            label_str = parts[1][:NUM_DIGITS]
            if len(label_str) != NUM_DIGITS:
                continue
            try:
                indices = [self.char_to_idx[c] for c in label_str]
            except KeyError:
                continue
            filepath = os.path.join(self.data_dir, filename)
            self.samples.append((filepath, indices))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        filepath, indices = self.samples[idx]

        img_bgr = cv2.imread(filepath)
        img_bgr = cv2.resize(img_bgr, (WIDTH, HEIGHT))

        if self.preprocess:
            gray = _preprocess(img_bgr)
            img_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        image = img_bgr.astype(np.float32) / 255.0

        image_tensor = torch.from_numpy(image)                  # [48, 140, 3]
        label_tensor = torch.tensor(indices, dtype=torch.long)  # [4]

        return image_tensor, label_tensor
