import os
import random
import time
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageFont
from PIL.ImageDraw import Draw

from thsr_ticket.ml.train.config import ALLOWED_CHARS, HEIGHT, WIDTH


class GenerateCaptcha:
    def __init__(
            self,
            width: int = WIDTH,
            height: int = HEIGHT,
            font_size: int = 50
        ) -> None:
        self._width = width
        self._height = height
        self._font_size = font_size
        self._mode = "L"  # 8-bit pixel
        self._font = self._load_font(font_size)
        self._chars = list(ALLOWED_CHARS)

    @staticmethod
    def _load_font(size: int) -> ImageFont.FreeTypeFont:
        candidates = [
            "calibri.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    def generate(self) -> Tuple[Image.Image, List[str]]:
        image = Image.new(self._mode, (self._width, self._height), color=255)
        c_list = list(np.random.choice(self._chars, size=4, replace=True))
        image = self.draw_characters(image, c_list)
        image = self.add_arc(image)
        image = self.add_noise(image)
        image = self.add_sp_noise(image)
        return image, c_list

    def add_noise(self, img: Image.Image, color_bound: int = 80) -> Image.Image:
        arr = np.array(img, dtype=np.int16)
        noise = np.random.randint(0, color_bound + 1, size=arr.shape)
        bright = arr > color_bound
        arr[bright] -= noise[bright]
        arr[~bright] += noise[~bright]
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    def add_sp_noise(self, img: Image.Image, prob: float = 0.03) -> Image.Image:
        arr = np.array(img)
        mask = np.random.random(arr.shape) < prob
        flipped = np.where(arr > 128, 0, 255).astype(np.uint8)
        arr[mask] = flipped[mask]
        return Image.fromarray(arr)

    def add_arc(self, img: Image.Image) -> Image.Image:
        arr = np.array(img)
        w = arr.shape[1]
        start = random.randint(20, 25)
        diff = random.randint(15, 18)
        # Fit quadratic through 3 points
        px = np.array([0, random.randint(32, 38), w], dtype=np.float64)
        py = np.array([start, start - diff // 2, start - diff], dtype=np.float64)
        coeffs = np.polyfit(px, py, 2)
        xx = np.arange(w)
        yy = np.round(np.polyval(coeffs, xx)).astype(int)
        for i in range(w):
            ry = slice(max(0, yy[i] - 2), min(arr.shape[0], yy[i] + 2))
            arr[ry, i] = np.where(arr[ry, i] < 128, 255, 0)
        return Image.fromarray(arr)

    def _draw_character(self, img: Image.Image, c: str) -> Image.Image:
        w, h = self._font_size - 6, self._font_size - 6

        dx = random.randint(0, 6)
        dy = random.randint(0, 6)
        im = Image.new(self._mode, (w + dx, h + dy), color=255)
        Draw(im).text((dx, dy), c, font=self._font, fill=0)

        # rotate
        bbox = im.getbbox()
        if bbox:
            im = im.crop(bbox)
        im = im.rotate(random.uniform(-10, 5), Image.BILINEAR, expand=1, fillcolor=255)

        # warp
        ddx = w * random.uniform(0.1, 0.2)
        ddy = h * random.uniform(0.1, 0.2)
        x1 = int(random.uniform(-ddx, ddx))
        y1 = int(random.uniform(-ddy, ddy))
        x2 = int(random.uniform(-ddx, ddx))
        y2 = int(random.uniform(-ddy, ddy))
        w2 = w + abs(x1) + abs(x2)
        h2 = h + abs(y1) + abs(y2)
        data = (
            x1, y1,
            -x1, h2 - y2,
            w2 + x2, h2 + y2,
            w2 - x2, -y1,
        )
        im = im.resize((w2, h2))
        im = im.transform((w, h), Image.QUAD, data, fill=255, fillcolor=255)
        return im

    def draw_characters(self, img: Image.Image, chars: List[str]) -> Image.Image:
        images = []
        for c in chars:
            images.append(self._draw_character(img, c))

        text_width = sum([im.size[0] for im in images])

        average = int(text_width / len(chars))
        rand = int(0.1 * average)
        offset = int(average * 0.1)

        table = [150 for _ in range(256)]
        for idx, im in enumerate(images):
            bbox = self._font.getbbox(chars[idx])
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            mask = im.point(table)
            img.paste(im, (offset, (self._height - h) // 2), mask)
            offset = offset + w + random.randint(-rand, 0)

        h_offset = 4
        arr = np.array(img)[h_offset:-h_offset, :offset + w // 3]
        arr = np.where(arr < 255, 0, 255)
        return Image.fromarray(arr.astype(np.uint8))


def generate_captcha(num_caps: int, save_path: str = None) -> None:
    captcha = GenerateCaptcha()
    for i in range(num_caps):
        img, c_list = captcha.generate()
        if save_path is not None:
            path = os.path.join(save_path, "{}.png".format(i))
            img.convert("RGB").save(path)


if __name__ == "__main__":
    captcha = GenerateCaptcha()
    start_t = time.time()
    img, c_list = captcha.generate()
    diff_t = time.time() - start_t
    print("".join(c_list), diff_t)
    img.show()
