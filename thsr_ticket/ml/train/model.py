"""Lightweight CNN for THSR captcha recognition.

Architecture:
    - Input: [batch, 48, 140, 3] (HWC format, matching ONNX contract)
    - 4 conv blocks with batch norm and max pooling
    - Adaptive average pooling
    - 4 separate classification heads (one per digit position)
    - ~1.8M parameters, ~7MB ONNX
"""

import torch
import torch.nn as nn

from thsr_ticket.ml.train.config import HEIGHT, NUM_CLASSES, NUM_DIGITS, WIDTH


class CaptchaCNN(nn.Module):

    def __init__(self, num_classes: int = NUM_CLASSES):
        super().__init__()
        self.num_classes = num_classes

        self.features = nn.Sequential(
            # Block 1: 3 -> 32, [48, 140] -> [24, 70]
            nn.Conv2d(3, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),

            # Block 2: 32 -> 64, [24, 70] -> [12, 35]
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),

            # Block 3: 64 -> 128, [12, 35] -> [6, 17]
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),

            # Block 4: 128 -> 128, [6, 17] -> [3, 8]
            nn.Conv2d(128, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),
        )

        self.adaptive_pool = nn.AdaptiveAvgPool2d((3, 8))
        flatten_size = 128 * 3 * 8  # 3072

        self.digit_heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(flatten_size, 128),
                nn.ReLU(inplace=True),
                nn.Dropout(0.3),
                nn.Linear(128, num_classes),
            )
            for _ in range(NUM_DIGITS)
        ])

    def forward(self, x: torch.Tensor):
        """Forward pass.

        Args:
            x: [batch, 48, 140, 3] (HWC format to match ONNX contract).

        Returns:
            Tuple of 4 tensors, each [batch, num_classes].
            Training mode: raw logits (for CrossEntropyLoss).
            Eval mode: softmax probabilities (for ONNX export / inference).
        """
        # HWC -> CHW for PyTorch conv layers
        x = x.permute(0, 3, 1, 2)  # [batch, 3, 48, 140]

        x = self.features(x)
        x = self.adaptive_pool(x)   # [batch, 128, 3, 8]
        x = x.flatten(1)            # [batch, 3072]

        outputs = []
        for head in self.digit_heads:
            logits = head(x)
            if not self.training:
                logits = torch.softmax(logits, dim=1)
            outputs.append(logits)

        return tuple(outputs)
