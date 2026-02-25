"""CLI tool for manually labeling collected THSR captchas.

Labeling is done by renaming files:
  - Unlabeled:  NNN_captcha_abc123.png
  - Labeled:    NNN_A3K7_abc123.png  (4-char label after number prefix)
  - Uncertain:  NNN_captcha_abc123.png  (unchanged, skipped)
"""

import argparse
import os
import subprocess

from thsr_ticket.ml.train.config import RAW_DIR


_VSCODE_PATHS = [
    '/usr/local/bin/code',
    '/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code',
]


def _find_code_cli() -> str:
    for p in _VSCODE_PATHS:
        if os.path.isfile(p):
            return p
    raise FileNotFoundError('VSCode CLI not found. Install "code" command from VSCode: '
                            'Cmd+Shift+P → "Shell Command: Install \'code\' command in PATH"')


def _show_image(filepath: str) -> None:
    """Open image in VSCode editor."""
    code = _find_code_cli()
    subprocess.Popen([code, '--reuse-window', os.path.abspath(filepath)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _is_unlabeled(filename: str) -> bool:
    """Unlabeled files contain '_captcha_' (e.g. 018_captcha_hash.png)."""
    return '_captcha_' in filename and filename.endswith('.png')


def _count_labeled(data_dir: str) -> int:
    return sum(
        1 for f in os.listdir(data_dir)
        if f.endswith('.png') and '_captcha_' not in f
    )


def label(data_dir: str) -> None:
    all_images = sorted([
        f for f in os.listdir(data_dir) if _is_unlabeled(f)
    ])
    labeled = _count_labeled(data_dir)

    print(f'Found {len(all_images)} unlabeled images ({labeled} already labeled)')
    print("Commands: 4-char label | 's' skip | 'q' quit\n")

    saved = 0

    try:
        for i, filename in enumerate(all_images):
            filepath = os.path.join(data_dir, filename)

            _show_image(filepath)

            user_input = input(f'[{i + 1}/{len(all_images)}] {filename}: ').strip().upper()

            if user_input == 'Q':
                break
            if user_input == 'S':
                continue
            if len(user_input) != 4:
                print('  Invalid (must be 4 chars), skipping.')
                continue

            # Rename: 018_captcha_hash.png -> 018_A3K7_hash.png
            # Find '_captcha_' and replace 'captcha' with the label
            idx = filename.index('_captcha_')
            prefix = filename[:idx]  # e.g. '018'
            suffix = filename[idx + len('_captcha_'):]  # e.g. 'hash.png'
            new_name = f'{prefix}_{user_input}_{suffix}'
            new_path = os.path.join(data_dir, new_name)
            os.rename(filepath, new_path)
            saved += 1
    except KeyboardInterrupt:
        pass

    print(f'\nLabeled {saved} images (total labeled: {labeled + saved})')


def main() -> None:
    parser = argparse.ArgumentParser(description='Label THSR captcha images')
    parser.add_argument('--data-dir', default=RAW_DIR,
                        help='Directory containing captcha images')
    args = parser.parse_args()
    label(args.data_dir)


if __name__ == '__main__':
    main()
