"""Export trained PyTorch model to ONNX format compatible with captcha_solver.py."""

import argparse
import os

import torch

from thsr_ticket.ml.train.config import (
    HEIGHT, MODEL_OUTPUT_DIR, NUM_CHANNELS, NUM_CLASSES,
    ONNX_INPUT_NAME, ONNX_OPSET_VERSION, ONNX_OUTPUT_NAMES, WIDTH,
)
from thsr_ticket.ml.train.model import CaptchaCNN


def export(checkpoint_path: str, output_path: str) -> None:
    model = CaptchaCNN(num_classes=NUM_CLASSES)
    model.load_state_dict(torch.load(checkpoint_path, map_location='cpu', weights_only=True))
    model.eval()  # softmax will be included in the ONNX graph

    # Dummy input matching the ONNX contract: [batch, 48, 140, 3]
    dummy_input = torch.randn(1, HEIGHT, WIDTH, NUM_CHANNELS)

    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        opset_version=ONNX_OPSET_VERSION,
        input_names=[ONNX_INPUT_NAME],
        output_names=ONNX_OUTPUT_NAMES,
        dynamic_axes={
            ONNX_INPUT_NAME: {0: 'batch'},
            **{name: {0: 'batch'} for name in ONNX_OUTPUT_NAMES},
        },
        dynamo=False,
    )

    file_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f'Exported ONNX model to {output_path} ({file_size:.1f} MB)')


def main() -> None:
    parser = argparse.ArgumentParser(description='Export captcha CNN to ONNX')
    parser.add_argument('checkpoint', help='Path to .pt checkpoint')
    parser.add_argument(
        '--output',
        default=os.path.join(MODEL_OUTPUT_DIR, 'thsrc_captcha.onnx'),
        help='Output ONNX path',
    )
    args = parser.parse_args()
    export(args.checkpoint, args.output)


if __name__ == '__main__':
    main()
