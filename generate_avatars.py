#!/usr/bin/env python3
"""Generate semi-realistic cute cat avatars for Arch, Stack, and Pixel."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import random
from typing import Tuple

from PIL import Image, ImageDraw, ImageFilter

Color = Tuple[int, int, int]


@dataclass(frozen=True)
class AvatarSpec:
    key: str
    seed: int
    bg_top: Color
    bg_bottom: Color
    fur_base: Color
    fur_shadow: Color
    fur_light: Color
    iris_outer: Color
    iris_inner: Color


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(c1: Color, c2: Color, t: float) -> Color:
    return (
        int(lerp(c1[0], c2[0], t)),
        int(lerp(c1[1], c2[1], t)),
        int(lerp(c1[2], c2[2], t)),
    )


def jitter(color: Color, spread: int, rng: random.Random) -> Color:
    return tuple(max(0, min(255, c + rng.randint(-spread, spread))) for c in color)  # type: ignore[return-value]


def vertical_gradient(size: tuple[int, int], top: Color, bottom: Color) -> Image.Image:
    width, height = size
    img = Image.new("RGBA", size)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(1, height - 1)
        color = lerp_color(top, bottom, t)
        draw.line([(0, y), (width, y)], fill=(*color, 255))
    return img


def add_soft_background_shapes(img: Image.Image, rng: random.Random, spec: AvatarSpec) -> None:
    """Clean manga-style background with subtle depth."""
    w, h = img.size
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    # Fewer, cleaner shapes for manga look
    for _ in range(8):
        radius = rng.randint(int(w * 0.12), int(w * 0.3))
        x = rng.randint(-radius, w + radius)
        y = rng.randint(-radius, h + radius)
        tint = lerp_color(spec.bg_top, spec.fur_light, rng.uniform(0.1, 0.3))
        alpha = rng.randint(8, 20)  # Very subtle
        draw.ellipse([(x - radius, y - radius), (x + radius, y + radius)], fill=(*tint, alpha))
    # Light blur for clean look
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(radius=w * 0.018)))


def build_cat_mask(size: tuple[int, int], center: tuple[int, int], r: int) -> Image.Image:
    """Super round squishy chibi cat face - maximum cuteness."""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    cx, cy = center

    # Extra round, squishy face shape
    draw.ellipse(
        [(cx - int(r * 1.15), cy - int(r * 0.88)), (cx + int(r * 1.15), cy + int(r * 1.0))],
        fill=255,
    )

    # Pointier but still cute ears
    left_ear = [
        (cx - int(r * 0.78), cy - int(r * 0.32)),
        (cx - int(r * 0.38), cy - int(r * 1.38)),  # Taller!
        (cx + int(r * 0.05), cy - int(r * 0.38)),
    ]
    right_ear = [
        (cx + int(r * 0.08), cy - int(r * 0.40)),
        (cx + int(r * 0.52), cy - int(r * 1.40)),
        (cx + int(r * 0.95), cy - int(r * 0.28)),
    ]
    draw.polygon(left_ear, fill=255)
    draw.polygon(right_ear, fill=255)

    return mask


def add_fur_texture(
    avatar: Image.Image,
    mask: Image.Image,
    center: tuple[int, int],
    r: int,
    spec: AvatarSpec,
    rng: random.Random,
) -> None:
    """Clean flat fur with minimal texture for manga style."""
    w, h = avatar.size
    cx, cy = center

    # Flat base layer - clean manga look
    base_layer = Image.new("RGBA", (w, h), (*spec.fur_base, 255))
    clipped = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    clipped.paste(base_layer, (0, 0), mask)
    avatar.alpha_composite(clipped)

    # Subtle shading layer
    shadow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    shadow_draw.ellipse(
        [(cx - int(r * 0.9), cy - int(r * 0.1)), (cx + int(r * 0.9), cy + int(r * 1.1))],
        fill=(*spec.fur_shadow, 60),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=int(r * 0.25)))
    clipped_shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    clipped_shadow.paste(shadow_layer, (0, 0), mask)
    avatar.alpha_composite(clipped_shadow)


def draw_inner_ears(avatar: Image.Image, center: tuple[int, int], r: int) -> None:
    draw = ImageDraw.Draw(avatar)
    cx, cy = center
    inner_color = (248, 184, 186, 150)

    left_inner = [
        (cx - int(r * 0.55), cy - int(r * 0.50)),
        (cx - int(r * 0.40), cy - int(r * 0.98)),
        (cx - int(r * 0.13), cy - int(r * 0.55)),
    ]
    right_inner = [
        (cx + int(r * 0.25), cy - int(r * 0.58)),
        (cx + int(r * 0.47), cy - int(r * 0.97)),
        (cx + int(r * 0.70), cy - int(r * 0.50)),
    ]
    draw.polygon(left_inner, fill=inner_color)
    draw.polygon(right_inner, fill=inner_color)


def draw_eye(
    avatar: Image.Image,
    eye_center: tuple[int, int],
    r: int,
    iris_outer: Color,
    iris_inner: Color,
    pupil_shift: float,
) -> None:
    """Super cute manga-style BIG sparkly eyes for maximum kawaii."""
    draw = ImageDraw.Draw(avatar)
    ex, ey = eye_center

    # HUGE eyes for super chibi manga look
    sclera_w = int(r * 2.0)
    sclera_h = int(r * 1.7)

    # Bright white sclera with outline
    draw.ellipse(
        [(ex - sclera_w - 2, ey - sclera_h - 2), (ex + sclera_w + 2, ey + sclera_h + 2)],
        fill=(60, 50, 70, 180),  # Subtle outline
    )
    draw.ellipse(
        [(ex - sclera_w, ey - sclera_h), (ex + sclera_w, ey + sclera_h)],
        fill=(255, 255, 255, 255),
    )

    # Massive vibrant iris
    iris_r = int(r * 1.45)
    iris_cx = ex + int(iris_r * pupil_shift * 0.3)
    iris_cy = ey + int(r * 0.05)

    # Saturated iris gradient
    for i in range(10):
        t = i / 9
        current = lerp_color(iris_outer, iris_inner, t)
        radius = int(iris_r * (1 - t * 0.7))
        draw.ellipse(
            [(iris_cx - radius, iris_cy - radius), (iris_cx + radius, iris_cy + radius)],
            fill=(*current, 255),
        )

    # Cute round pupil
    pupil_r = int(r * 0.6)
    draw.ellipse(
        [(iris_cx - pupil_r, iris_cy - pupil_r), (iris_cx + pupil_r, iris_cy + pupil_r)],
        fill=(15, 15, 25, 255),
    )

    # GIANT sparkly highlights - THE KEY TO KAWAII
    # Main highlight - huge
    draw.ellipse(
        [(iris_cx - int(r * 0.55), iris_cy - int(r * 0.7)),
         (iris_cx + int(r * 0.15), iris_cy + int(r * 0.1))],
        fill=(255, 255, 255, 255),
    )
    # Second big highlight
    draw.ellipse(
        [(iris_cx + int(r * 0.2), iris_cy + int(r * 0.3)),
         (iris_cx + int(r * 0.55), iris_cy + int(r * 0.6))],
        fill=(255, 255, 255, 230),
    )
    # Third tiny sparkle
    draw.ellipse(
        [(iris_cx - int(r * 0.75), iris_cy + int(r * 0.1)),
         (iris_cx - int(r * 0.5), iris_cy + int(r * 0.35))],
        fill=(255, 255, 255, 220),
    )


def draw_face(avatar: Image.Image, center: tuple[int, int], r: int, spec: AvatarSpec, rng: random.Random) -> tuple[tuple[int, int], tuple[int, int]]:
    draw = ImageDraw.Draw(avatar)
    cx, cy = center

    # Eyes positioned for cuter look - slightly lower and closer together
    eye_y = cy - int(r * 0.02)
    left_eye = (cx - int(r * 0.30), eye_y)
    right_eye = (cx + int(r * 0.22), eye_y)

    eye_r = int(r * 0.28)  # Bigger eye radius
    draw_eye(avatar, left_eye, eye_r, spec.iris_outer, spec.iris_inner, pupil_shift=0.15)
    draw_eye(avatar, right_eye, eye_r, spec.iris_outer, spec.iris_inner, pupil_shift=0.15)

    # Smaller, cuter nose
    nose_x = cx + int(r * 0.08)
    nose_y = cy + int(r * 0.25)
    nose_size = int(r * 0.10)
    nose = [
        (nose_x, nose_y - nose_size),
        (nose_x - nose_size, nose_y + int(nose_size * 0.5)),
        (nose_x + nose_size, nose_y + int(nose_size * 0.5)),
    ]
    draw.polygon(nose, fill=(255, 155, 165, 250))  # Pinker, cuter nose

    # Cute w-shaped mouth
    mouth_color = (200, 110, 125, 230)
    mouth_y = nose_y + int(nose_size * 1.1)
    # Left curve
    draw.arc(
        [
            (nose_x - int(r * 0.22), mouth_y - int(r * 0.08)),
            (nose_x, mouth_y + int(r * 0.12)),
        ],
        start=200,
        end=340,
        fill=mouth_color,
        width=max(2, int(r * 0.035)),
    )
    # Right curve
    draw.arc(
        [
            (nose_x, mouth_y - int(r * 0.08)),
            (nose_x + int(r * 0.22), mouth_y + int(r * 0.12)),
        ],
        start=200,
        end=340,
        fill=mouth_color,
        width=max(2, int(r * 0.035)),
    )

    # Cheek blush - bigger and more visible for manga!
    blush_color = (255, 160, 180, 160)
    draw.ellipse(
        [(cx - int(r * 0.92), cy + int(r * 0.05)), (cx - int(r * 0.30), cy + int(r * 0.50))],
        fill=blush_color,
    )
    draw.ellipse(
        [(cx + int(r * 0.25), cy + int(r * 0.05)), (cx + int(r * 0.87), cy + int(r * 0.50))],
        fill=blush_color,
    )

    # Bolder whiskers for manga look
    whisker_color = (80, 70, 85, 200)
    whisker_width = max(2, int(r * 0.025))
    for side in (-1, 1):
        base_x = nose_x + side * int(r * 0.25)
        for i in range(3):
            y = nose_y + int(r * (-0.08 + i * 0.12))
            length = int(r * (0.5 + i * 0.06))
            curve = side * int(r * 0.04)
            draw.line(
                [(base_x, y), (base_x + side * length, y + curve)],
                fill=whisker_color,
                width=whisker_width,
            )

    return left_eye, right_eye


def add_arch_accessory(avatar: Image.Image, right_eye: tuple[int, int], r: int) -> None:
    """Cute monocle for Arch - slightly oversized for chibi look."""
    draw = ImageDraw.Draw(avatar)
    ex, ey = right_eye
    ring_r = int(r * 0.38)  # Bigger monocle

    # Gold monocle rim
    draw.ellipse(
        [
            (ex - ring_r, ey - ring_r),
            (ex + ring_r, ey + ring_r),
        ],
        outline=(205, 175, 95, 255),
        width=max(3, int(r * 0.04)),
    )
    # Inner shine
    draw.ellipse(
        [
            (ex - ring_r + 5, ey - ring_r + 5),
            (ex + ring_r - 5, ey + ring_r - 5),
        ],
        outline=(240, 220, 170, 180),
        width=2,
    )

    # Cute chain
    chain_start = (ex + ring_r - 3, ey + int(r * 0.05))
    chain_end = (ex + int(r * 0.65), ey + int(r * 0.45))
    draw.line([chain_start, chain_end], fill=(205, 175, 95, 240), width=max(2, int(r * 0.025)))

    # Chain beads
    for i in range(5):
        px = int(lerp(chain_start[0], chain_end[0], i / 4))
        py = int(lerp(chain_start[1], chain_end[1], i / 4))
        d = max(2, int(r * 0.025))
        draw.ellipse([(px - d, py - d), (px + d, py + d)], fill=(235, 210, 145, 230))


def add_stack_accessory(avatar: Image.Image, center: tuple[int, int], r: int) -> None:
    """Cute hoodie and wrench for Stack - ready to code!"""
    draw = ImageDraw.Draw(avatar)
    cx, cy = center

    # Cute hoodie in warm gray-blue
    hood_color = (95, 110, 135, 245)
    draw.arc(
        [
            (cx - int(r * 1.15), cy + int(r * 0.30)),
            (cx + int(r * 1.10), cy + int(r * 1.50)),
        ],
        start=10,
        end=170,
        fill=hood_color,
        width=max(10, int(r * 0.14)),
    )

    # Hood strings
    string_color = (235, 235, 240, 230)
    draw.line(
        [
            (cx - int(r * 0.18), cy + int(r * 0.82)),
            (cx - int(r * 0.20), cy + int(r * 1.15)),
        ],
        fill=string_color,
        width=max(2, int(r * 0.025)),
    )
    draw.line(
        [
            (cx + int(r * 0.02), cy + int(r * 0.82)),
            (cx + int(r * 0.05), cy + int(r * 1.15)),
        ],
        fill=string_color,
        width=max(2, int(r * 0.025)),
    )

    # Cute wrench
    wrench_x = cx - int(r * 1.05)
    wrench_y = cy + int(r * 0.92)
    metal = (175, 185, 200, 220)
    handle_color = (255, 165, 75, 200)  # Orange handle - matches fur!
    # Handle
    draw.rectangle(
        [
            (wrench_x, wrench_y),
            (wrench_x + int(r * 0.32), wrench_y + int(r * 0.07)),
        ],
        fill=handle_color,
    )
    # Metal part
    draw.rectangle(
        [
            (wrench_x + int(r * 0.30), wrench_y),
            (wrench_x + int(r * 0.45), wrench_y + int(r * 0.07)),
        ],
        fill=metal,
    )
    draw.ellipse(
        [
            (wrench_x + int(r * 0.38), wrench_y - int(r * 0.06)),
            (wrench_x + int(r * 0.55), wrench_y + int(r * 0.13)),
        ],
        outline=metal,
        width=max(2, int(r * 0.025)),
    )


def add_pixel_accessory(avatar: Image.Image, center: tuple[int, int], r: int) -> None:
    """Cute artist beret and paintbrush for Pixel."""
    draw = ImageDraw.Draw(avatar)
    cx, cy = center

    # Cute pink beret
    beret = (215, 135, 165, 250)
    draw.ellipse(
        [
            (cx - int(r * 0.95), cy - int(r * 1.00)),
            (cx + int(r * 0.60), cy - int(r * 0.20)),
        ],
        fill=beret,
    )
    # Beret pom-pom
    draw.ellipse(
        [
            (cx - int(r * 0.22), cy - int(r * 1.18)),
            (cx - int(r * 0.02), cy - int(r * 0.95)),
        ],
        fill=(235, 165, 195, 255),
    )

    # Cute paintbrush with colorful tip
    brush_x = cx + int(r * 0.82)
    brush_y = cy + int(r * 0.88)
    # Wooden handle
    draw.rectangle(
        [
            (brush_x, brush_y),
            (brush_x + int(r * 0.09), brush_y + int(r * 0.42)),
        ],
        fill=(195, 155, 110, 220),
    )
    # Silver ferrule
    draw.rectangle(
        [
            (brush_x, brush_y - int(r * 0.05)),
            (brush_x + int(r * 0.09), brush_y),
        ],
        fill=(195, 200, 210, 220),
    )
    # Paint tip - rainbow gradient effect
    draw.ellipse(
        [
            (brush_x - int(r * 0.08), brush_y - int(r * 0.12)),
            (brush_x + int(r * 0.17), brush_y + int(r * 0.06)),
        ],
        fill=(255, 140, 180, 230),  # Pink paint
    )
    # Small paint dot accent
    draw.ellipse(
        [
            (brush_x - int(r * 0.04), brush_y - int(r * 0.18)),
            (brush_x + int(r * 0.08), brush_y - int(r * 0.08)),
        ],
        fill=(180, 220, 255, 200),  # Blue accent
    )


def add_soft_shading(avatar: Image.Image, center: tuple[int, int], r: int) -> None:
    """Minimal clean shading for manga style."""
    w, h = avatar.size
    cx, cy = center

    # Subtle shadow under chin only
    shadow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow_layer)
    draw.ellipse(
        [(cx - int(r * 0.8), cy + int(r * 0.5)), (cx + int(r * 0.8), cy + int(r * 1.2))],
        fill=(50, 50, 60, 35),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=int(r * 0.15)))
    avatar.alpha_composite(shadow_layer)


def apply_vignette(img: Image.Image) -> None:
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    margin = int(w * 0.03)
    draw.rounded_rectangle(
        [(margin, margin), (w - margin, h - margin)],
        radius=int(w * 0.14),
        outline=(0, 0, 0, 52),
        width=max(3, int(w * 0.012)),
    )
    img.alpha_composite(overlay.filter(ImageFilter.GaussianBlur(radius=max(4, int(w * 0.01)))))


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (size[0], size[1])], radius=radius, fill=255)
    return mask


def generate_avatar(spec: AvatarSpec, size: int = 640) -> Image.Image:
    rng = random.Random(spec.seed)
    canvas = vertical_gradient((size, size), spec.bg_top, spec.bg_bottom)
    add_soft_background_shapes(canvas, rng, spec)

    avatar = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    center = (int(size * 0.54), int(size * 0.57))
    r = int(size * 0.26)

    mask = build_cat_mask((size, size), center, r)
    add_fur_texture(avatar, mask, center, r, spec, rng)
    add_soft_shading(avatar, center, r)
    draw_inner_ears(avatar, center, r)
    _, right_eye = draw_face(avatar, center, r, spec, rng)

    if spec.key == "arch":
        add_arch_accessory(avatar, right_eye, r)
    elif spec.key == "stack":
        add_stack_accessory(avatar, center, r)
    elif spec.key == "pixel":
        add_pixel_accessory(avatar, center, r)

    # Keep sharp for manga style - no blur!
    canvas.alpha_composite(avatar)
    apply_vignette(canvas)

    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(canvas, (0, 0), rounded_mask((size, size), radius=int(size * 0.12)))

    # Sharp and clean
    return out


def main() -> None:
    # Vibrant anime-style color palettes for cuter chibi look
    specs = [
        AvatarSpec(
            key="arch",
            seed=2026021701,
            bg_top=(175, 205, 235),  # Bright sky blue
            bg_bottom=(115, 155, 205),
            fur_base=(250, 252, 255),  # Pure white
            fur_shadow=(210, 220, 235),
            fur_light=(255, 255, 255),
            iris_outer=(60, 130, 190),  # Bright blue
            iris_inner=(140, 195, 240),
        ),
        AvatarSpec(
            key="stack",
            seed=2026021702,
            bg_top=(255, 225, 175),  # Sunny cream
            bg_bottom=(245, 185, 125),
            fur_base=(255, 190, 115),  # Bright orange tabby
            fur_shadow=(225, 145, 80),
            fur_light=(255, 220, 165),
            iris_outer=(160, 100, 60),  # Warm amber
            iris_inner=(215, 170, 110),
        ),
        AvatarSpec(
            key="pixel",
            seed=2026021703,
            bg_top=(240, 210, 230),  # Soft pink-lavender
            bg_bottom=(210, 170, 200),
            fur_base=(255, 252, 250),  # Warm white
            fur_shadow=(225, 210, 205),
            fur_light=(255, 255, 255),
            iris_outer=(140, 100, 150),  # Soft purple
            iris_inner=(200, 165, 210),
        ),
    ]

    output_dir = Path("public/avatars")
    output_dir.mkdir(parents=True, exist_ok=True)

    for spec in specs:
        avatar = generate_avatar(spec)
        if spec.key == "pixel":
            # Calico patches with soft watercolor edges
            size = avatar.size[0]
            cx = int(size * 0.54)
            cy = int(size * 0.57)
            r = int(size * 0.26)

            # Create a separate layer for patches
            patch_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            patch_draw = ImageDraw.Draw(patch_layer)

            # Orange patch - softer, more blended
            patch_draw.polygon(
                [
                    (cx - int(r * 0.62), cy - int(r * 0.40)),
                    (cx - int(r * 0.32), cy - int(r * 1.01)),
                    (cx - int(r * 0.06), cy - int(r * 0.55)),
                    (cx - int(r * 0.29), cy - int(r * 0.17)),
                ],
                fill=(242, 165, 115, 90),  # Softer orange, lower alpha
            )
            # Black/brown patch
            patch_draw.polygon(
                [
                    (cx + int(r * 0.23), cy - int(r * 0.50)),
                    (cx + int(r * 0.51), cy - int(r * 1.14)),
                    (cx + int(r * 0.84), cy - int(r * 0.38)),
                    (cx + int(r * 0.46), cy - int(r * 0.12)),
                ],
                fill=(68, 62, 72, 85),  # Softer dark
            )

            # Blur the patches for watercolor bleeding
            patch_layer = patch_layer.filter(ImageFilter.GaussianBlur(radius=8))
            avatar.alpha_composite(patch_layer)

        out_path = output_dir / f"{spec.key}.png"
        avatar.save(out_path, format="PNG", optimize=True)
        print(f"Generated {out_path}")


if __name__ == "__main__":
    main()
