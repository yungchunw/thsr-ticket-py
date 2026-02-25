# THSR Captcha CNN Training Pipeline

## Prerequisites

```bash
uv pip install -e ".[train]"
```

## Step 1: Collect Captcha Images

```bash
python -m thsr_ticket.ml.train.collect_captchas --count 200

# Options
#   --count   Target total number (default: 200)
#   --delay   Delay between requests in seconds (default: 1.5)
#   --output  Output directory (default: thsr_ticket/ml/train/data/raw/)
```

## Step 2: Label Images

```bash
python -m thsr_ticket.ml.train.label_captchas

# Options
#   --data-dir  Image directory (default: thsr_ticket/ml/train/data/raw/)
```

Labels are stored in the filename:
- Unlabeled: `captcha_abc123.png`
- Labeled: `A3K7_abc123.png` (4-char label prefix)
- `s` to skip, `q` to quit, Ctrl+C safe

## Step 3: Train

```bash
python -m thsr_ticket.ml.train.train --epochs 50

# Options
#   --epochs      Number of epochs (default: 50)
#   --batch-size  Batch size (default: 64)
#   --lr          Learning rate (default: 0.001)
#   --output      Checkpoint path (default: captcha_cnn.pt)
#   --data-dir    Image directory
```

## Step 4: Export to ONNX

```bash
python -m thsr_ticket.ml.train.export_onnx captcha_cnn.pt

# Options
#   --output  ONNX output path (default: thsr_ticket/ml/models/thsrc_captcha.onnx)
```

## Step 5: Verify ONNX

```bash
python -m thsr_ticket.ml.train.verify_onnx thsr_ticket/ml/models/thsrc_captcha.onnx
```

## Incremental Training (Retrain with Failed Captchas)

When `--auto-captcha` is used, failed captcha images are automatically saved to
`thsr_ticket/ml/train/data/failed/`.

```bash
# 1. Copy failed images to raw directory
cp thsr_ticket/ml/train/data/failed/*.png thsr_ticket/ml/train/data/raw/

# 2. Label the new images (only unlabeled ones will be shown)
python -m thsr_ticket.ml.train.label_captchas

# 3. Retrain
python -m thsr_ticket.ml.train.train --epochs 50

# 4. Export
python -m thsr_ticket.ml.train.export_onnx captcha_cnn.pt

# 5. Verify
python -m thsr_ticket.ml.train.verify_onnx thsr_ticket/ml/models/thsrc_captcha.onnx
```
