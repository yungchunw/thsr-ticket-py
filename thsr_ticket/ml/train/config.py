"""Shared constants for the THSR captcha training pipeline."""

import os

# Paths
TRAIN_DIR = os.path.join(os.path.dirname(__file__), 'data')
RAW_DIR = os.path.join(TRAIN_DIR, 'raw')
MODEL_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'models')

# Image dimensions (must match captcha_solver.py)
WIDTH = 140
HEIGHT = 48
NUM_CHANNELS = 3

# Character set — matches captcha_solver.py ALLOWED_CHARS.
# Update if labeling reveals a different set.
ALLOWED_CHARS = '2345679ACDFGHKMNPQRTVWYZ'
NUM_CLASSES = len(ALLOWED_CHARS)  # 24
NUM_DIGITS = 4

# Training hyperparameters
BATCH_SIZE = 64
LEARNING_RATE = 1e-3
NUM_EPOCHS = 50
VALIDATION_SPLIT = 0.15
WEIGHT_DECAY = 1e-4

# ONNX export
ONNX_INPUT_NAME = 'input'
ONNX_OUTPUT_NAMES = ['digit1', 'digit2', 'digit3', 'digit4']
ONNX_OPSET_VERSION = 13
