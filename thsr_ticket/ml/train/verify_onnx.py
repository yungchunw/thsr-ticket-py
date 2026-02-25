"""Verify exported ONNX model matches the expected contract for captcha_solver.py."""

import argparse
import sys

import numpy as np
import onnxruntime as ort

from thsr_ticket.ml.train.config import (
    HEIGHT, NUM_CHANNELS, NUM_CLASSES, ONNX_INPUT_NAME, ONNX_OUTPUT_NAMES, WIDTH,
)


def verify(model_path: str) -> bool:
    sess = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])

    # Check input
    inputs = sess.get_inputs()
    assert len(inputs) == 1, f'Expected 1 input, got {len(inputs)}'
    inp = inputs[0]
    assert inp.name == ONNX_INPUT_NAME, \
        f"Input name: expected '{ONNX_INPUT_NAME}', got '{inp.name}'"
    assert inp.type == 'tensor(float)', f'Input type: {inp.type}'
    shape = inp.shape
    assert shape[1:] == [HEIGHT, WIDTH, NUM_CHANNELS], \
        f'Input shape[1:]: expected {[HEIGHT, WIDTH, NUM_CHANNELS]}, got {shape[1:]}'

    # Check outputs
    outputs = sess.get_outputs()
    assert len(outputs) == len(ONNX_OUTPUT_NAMES), \
        f'Expected {len(ONNX_OUTPUT_NAMES)} outputs, got {len(outputs)}'
    for out, expected_name in zip(outputs, ONNX_OUTPUT_NAMES):
        assert out.name == expected_name, \
            f"Output name: expected '{expected_name}', got '{out.name}'"
        assert out.shape[-1] == NUM_CLASSES, \
            f'Output {out.name} last dim: expected {NUM_CLASSES}, got {out.shape[-1]}'

    # Run inference with dummy data
    dummy = np.random.rand(1, HEIGHT, WIDTH, NUM_CHANNELS).astype(np.float32)
    results = sess.run([o.name for o in outputs], {ONNX_INPUT_NAME: dummy})

    for i, result in enumerate(results):
        assert result.shape == (1, NUM_CLASSES), \
            f'Output {i} shape: expected (1, {NUM_CLASSES}), got {result.shape}'
        assert np.all(result >= 0), f'Output {i} has negative values'
        assert abs(result.sum() - 1.0) < 0.01, \
            f"Output {i} doesn't sum to ~1: {result.sum():.4f}"

    print('All checks passed!')
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description='Verify ONNX captcha model')
    parser.add_argument('model', help='Path to ONNX model')
    args = parser.parse_args()

    try:
        verify(args.model)
    except AssertionError as e:
        print(f'FAILED: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
