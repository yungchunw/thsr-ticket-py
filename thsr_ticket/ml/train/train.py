"""Training loop for THSR captcha CNN."""

import argparse
import time
from typing import Tuple

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split

from thsr_ticket.ml.train.config import (
    ALLOWED_CHARS, BATCH_SIZE, LEARNING_RATE, NUM_DIGITS,
    NUM_EPOCHS, RAW_DIR, VALIDATION_SPLIT, WEIGHT_DECAY,
)
from thsr_ticket.ml.train.dataset import CaptchaDataset
from thsr_ticket.ml.train.model import CaptchaCNN


def _train_one_epoch(
    model: CaptchaCNN,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
) -> Tuple[float, float]:
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for images, labels in loader:
        images = images.to(device)  # [batch, 48, 140, 3]
        labels = labels.to(device)  # [batch, 4]

        optimizer.zero_grad()
        outputs = model(images)     # tuple of 4 x [batch, num_classes]

        loss = sum(
            criterion(outputs[i], labels[:, i])
            for i in range(NUM_DIGITS)
        )

        loss.backward()
        optimizer.step()

        total_loss += loss.item() * images.size(0)

        # All-4-correct accuracy
        preds = torch.stack([out.argmax(dim=1) for out in outputs], dim=1)
        correct += (preds == labels).all(dim=1).sum().item()
        total += images.size(0)

    return total_loss / total, correct / total


def _validate(
    model: CaptchaCNN,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> Tuple[float, float]:
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)

            outputs = model(images)
            loss = sum(
                criterion(outputs[i], labels[:, i])
                for i in range(NUM_DIGITS)
            )

            total_loss += loss.item() * images.size(0)
            preds = torch.stack([out.argmax(dim=1) for out in outputs], dim=1)
            correct += (preds == labels).all(dim=1).sum().item()
            total += images.size(0)

    return total_loss / total, correct / total


def main() -> None:
    parser = argparse.ArgumentParser(description='Train THSR captcha CNN')
    parser.add_argument('--data-dir', default=RAW_DIR)
    parser.add_argument('--epochs', type=int, default=NUM_EPOCHS)
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE)
    parser.add_argument('--lr', type=float, default=LEARNING_RATE)
    parser.add_argument('--output', default='captcha_cnn.pt',
                        help='Path to save best model checkpoint')
    parser.add_argument('--resume', default=None,
                        help='Path to checkpoint to resume training from')
    args = parser.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'Using device: {device}')

    # Dataset and splits
    dataset = CaptchaDataset(data_dir=args.data_dir)
    print(f'Total samples: {len(dataset)}')

    val_size = int(len(dataset) * VALIDATION_SPLIT)
    train_size = len(dataset) - val_size
    train_set, val_set = random_split(
        dataset, [train_size, val_size],
        generator=torch.Generator().manual_seed(42),
    )

    train_loader = DataLoader(
        train_set, batch_size=args.batch_size, shuffle=True, num_workers=2,
    )
    val_loader = DataLoader(
        val_set, batch_size=args.batch_size, shuffle=False, num_workers=2,
    )

    # Model, loss, optimizer
    model = CaptchaCNN(num_classes=len(ALLOWED_CHARS)).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(
        model.parameters(), lr=args.lr, weight_decay=WEIGHT_DECAY,
    )
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=5,
    )

    best_val_acc = 0.0

    if args.resume:
        checkpoint = torch.load(args.resume, map_location=device, weights_only=True)
        model.load_state_dict(checkpoint)
        # Evaluate resumed model to set baseline
        val_loss, val_acc = _validate(model, val_loader, criterion, device)
        best_val_acc = val_acc
        print(f'Resumed from {args.resume} (val_acc={val_acc:.4f})')

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        train_loss, train_acc = _train_one_epoch(
            model, train_loader, optimizer, criterion, device,
        )
        val_loss, val_acc = _validate(model, val_loader, criterion, device)
        scheduler.step(val_loss)

        elapsed = time.time() - t0
        lr = optimizer.param_groups[0]['lr']
        print(
            f'Epoch {epoch:3d}/{args.epochs} '
            f'| train_loss={train_loss:.4f} train_acc={train_acc:.4f} '
            f'| val_loss={val_loss:.4f} val_acc={val_acc:.4f} '
            f'| lr={lr:.6f} | {elapsed:.1f}s'
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), args.output)
            print(f'  -> Saved best model (val_acc={val_acc:.4f})')

    print(f'\nTraining complete. Best val accuracy: {best_val_acc:.4f}')


if __name__ == '__main__':
    main()
