"""Download real THSR captcha images for training data collection."""

import argparse
import hashlib
import os
import time

from thsr_ticket.remote.http_request import HTTPRequest


def _count_existing(output_dir: str) -> int:
    if not os.path.exists(output_dir):
        return 0
    return len([f for f in os.listdir(output_dir) if f.endswith('.png')])


def collect(output_dir: str, target: int, delay: float = 1.5) -> None:
    os.makedirs(output_dir, exist_ok=True)

    existing = _count_existing(output_dir)
    if existing >= target:
        print(f'Already have {existing} images (target: {target}). Nothing to do.')
        return

    need = target - existing
    print(f'Existing: {existing}, target: {target}, need: {need}')

    saved = 0
    attempt = 0
    while existing + saved < target:
        attempt += 1
        try:
            client = HTTPRequest()
            book_page = client.request_booking_page()
            img_resp = client.request_security_code_img(book_page.content)
            img_bytes = img_resp.content

            img_hash = hashlib.md5(img_bytes).hexdigest()[:12]
            filename = f'captcha_{img_hash}.png'
            filepath = os.path.join(output_dir, filename)

            if not os.path.exists(filepath):
                with open(filepath, 'wb') as f:
                    f.write(img_bytes)
                saved += 1
                total = existing + saved
                print(f'[{total}/{target}] Saved: {filename}')
            else:
                print(f'[{attempt}] Duplicate, skipped: {filename}')

        except Exception as e:
            print(f'[{attempt}] Error: {e}')

        if existing + saved < target:
            time.sleep(delay)

    print(f'\nDone. Saved {saved} new captchas (total: {existing + saved})')


def main() -> None:
    parser = argparse.ArgumentParser(description='Collect THSR captcha images')
    parser.add_argument('--output', default=os.path.join(
        os.path.dirname(__file__), 'data', 'raw',
    ), help='Output directory for captcha images')
    parser.add_argument('--count', type=int, default=200,
                        help='Target number of captchas (including existing)')
    parser.add_argument('--delay', type=float, default=1.5,
                        help='Delay between requests in seconds')
    args = parser.parse_args()
    collect(args.output, target=args.count, delay=args.delay)


if __name__ == '__main__':
    main()
