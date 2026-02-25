"""Incremental training: download captchas, verify via THSR, retrain.

Usage:
    python -m thsr_ticket.ml.train.incremental [--count 50] [--epochs 10]

Flow:
    1. Download captchas from THSR and predict with current model
    2. Submit to THSR to verify — only label if THSR accepts
    3. Resume training from existing checkpoint
    4. Export updated ONNX model
"""

import argparse
import hashlib
import json
import os
import time

from thsr_ticket.ml.train.config import MODEL_OUTPUT_DIR, RAW_DIR


def _next_num(raw_dir: str) -> int:
    existing = [f for f in os.listdir(raw_dir) if f.endswith('.png') and f[0].isdigit()]
    return max((int(f.split('_')[0]) for f in existing), default=0) + 1


def _save(raw_dir: str, num: int, img_bytes: bytes, label: str = None) -> None:
    img_hash = hashlib.md5(img_bytes).hexdigest()[:12]
    middle = label if label else 'captcha'
    filepath = os.path.join(raw_dir, f'{num:05d}_{middle}_{img_hash}.png')
    if not os.path.exists(filepath):
        with open(filepath, 'wb') as f:
            f.write(img_bytes)


def collect_and_label(count: int, delay: float = 1.5) -> tuple:
    """Download captchas, predict, and verify by submitting to THSR.

    Only auto-labels captchas that THSR confirms as correct.
    Returns (verified_count, failed_count, skipped_count).
    """
    from thsr_ticket.ml.captcha_solver import LowConfidenceError, solve
    from thsr_ticket.remote.http_request import HTTPRequest
    from thsr_ticket.configs.web.param_schema import BookingModel
    from thsr_ticket.configs.web.parse_html_element import BOOKING_PAGE, ERROR_FEEDBACK
    from bs4 import BeautifulSoup

    os.makedirs(RAW_DIR, exist_ok=True)
    num = _next_num(RAW_DIR)

    verified = 0
    failed = 0
    skipped = 0

    for i in range(1, count + 1):
        try:
            client = HTTPRequest()
            book_page_resp = client.request_booking_page()
            book_page = book_page_resp.content
            img_bytes = client.request_security_code_img(book_page).content

            try:
                prediction = solve(img_bytes)
            except LowConfidenceError:
                _save(RAW_DIR, num, img_bytes)
                print(f'[{i}/{count}] low confidence, saved unlabeled')
                skipped += 1
                num += 1
                if i < count:
                    time.sleep(delay)
                continue

            # Build minimal booking form to verify captcha
            page = BeautifulSoup(book_page, features='html.parser')

            # Parse required hidden fields
            trip_tag = page.find('input', {'name': 'tripCon:typesoftrip'})
            types_of_trip = int(trip_tag['value']) if trip_tag else 0

            search_tag = page.find('input', {'name': 'bookingMethod', 'checked': True})
            search_by = search_tag['value'] if search_tag else '1'

            seat_tag = page.find(**BOOKING_PAGE["seat_prefer_radio"])
            seat_val = seat_tag.find_next(selected='selected')['value'] if seat_tag else '0'

            book_model = BookingModel(
                start_station=2,   # Taipei
                dest_station=7,    # Taichung
                outbound_date='2026/03/15',
                outbound_time='1000A',
                adult_ticket_num='1F',
                college_ticket_num='0H',
                seat_prefer=seat_val,
                class_type=0,
                types_of_trip=types_of_trip,
                search_by=search_by,
                security_code=prediction,
            )

            dict_params = json.loads(book_model.json(by_alias=True))
            resp = client.submit_booking_form(dict_params)

            # Check if captcha was accepted
            resp_page = BeautifulSoup(resp.content, features='html.parser')
            errors = resp_page.find_all(**ERROR_FEEDBACK)

            if not errors:
                # THSR accepted → captcha is correct
                _save(RAW_DIR, num, img_bytes, label=prediction)
                print(f'[{i}/{count}] {prediction} (verified)')
                verified += 1
            else:
                error_text = errors[0].text.strip()
                _save(RAW_DIR, num, img_bytes)
                print(f'[{i}/{count}] {prediction} rejected: {error_text}')
                failed += 1
            num += 1

        except Exception as e:
            print(f'[{i}/{count}] error: {e}')
            skipped += 1

        if i < count:
            time.sleep(delay)

    return verified, failed, skipped


def retrain(epochs: int, lr: float) -> None:
    """Resume training from existing checkpoint."""
    import subprocess
    import sys

    pt_path = os.path.join(MODEL_OUTPUT_DIR, 'captcha_cnn.pt')
    onnx_path = os.path.join(MODEL_OUTPUT_DIR, 'thsrc_captcha.onnx')

    # Train
    train_cmd = [
        sys.executable, '-m', 'thsr_ticket.ml.train.train',
        '--resume', pt_path,
        '--epochs', str(epochs),
        '--lr', str(lr),
        '--output', pt_path,
    ]
    print(f'\n=== 開始增量訓練 ({epochs} epochs, lr={lr}) ===')
    subprocess.run(train_cmd, check=True)

    # Export ONNX
    export_cmd = [
        sys.executable, '-m', 'thsr_ticket.ml.train.export_onnx',
        pt_path, '--output', onnx_path,
    ]
    print('\n=== 匯出 ONNX ===')
    subprocess.run(export_cmd, check=True)

    # Verify
    verify_cmd = [
        sys.executable, '-m', 'thsr_ticket.ml.train.verify_onnx',
        onnx_path,
    ]
    subprocess.run(verify_cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='增量訓練：下載 captcha → 高鐵驗證標記 → 重新訓練',
    )
    parser.add_argument('--count', type=int, default=50,
                        help='下載 captcha 數量 (預設: 50)')
    parser.add_argument('--epochs', type=int, default=10,
                        help='訓練 epochs (預設: 10)')
    parser.add_argument('--lr', type=float, default=1e-4,
                        help='學習率 (預設: 0.0001)')
    parser.add_argument('--delay', type=float, default=1.5,
                        help='下載間隔秒數 (預設: 1.5)')
    parser.add_argument('--collect-only', action='store_true',
                        help='只下載驗證，不訓練')
    parser.add_argument('--train-only', action='store_true',
                        help='只訓練，不下載')
    args = parser.parse_args()

    if not args.train_only:
        print('=== 下載 captcha 並透過高鐵驗證 ===')
        verified, failed, skipped = collect_and_label(args.count, delay=args.delay)
        print(f'\n驗證通過: {verified}, 驗證失敗: {failed}, 跳過: {skipped}')

    if not args.collect_only:
        retrain(args.epochs, args.lr)

    print('\n完成！')


if __name__ == '__main__':
    main()
