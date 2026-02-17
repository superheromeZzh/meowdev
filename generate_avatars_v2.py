"""
生成更可爱的猫猫头像 v2
基于 AI 图像分析的专业建议优化
"""

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
from pathlib import Path
import math

OUTPUT_DIR = Path(__file__).parent / "public" / "avatars"
SIZE = 512


def draw_gradient_circle(draw, cx, cy, radius, color_center, color_edge, alpha=255):
    """绘制渐变圆形"""
    for r in range(int(radius), 0, -1):
        ratio = r / radius
        cr = int(color_center[0] * ratio + color_edge[0] * (1 - ratio))
        cg = int(color_center[1] * ratio + color_edge[1] * (1 - ratio))
        cb = int(color_center[2] * ratio + color_edge[2] * (1 - ratio))
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(cr, cg, cb, alpha))


def draw_anime_eye(draw, cx, cy, size, colors):
    """绘制动漫风格大眼睛"""
    # 眼白 - 椭圆形
    draw.ellipse([cx-size, cy-size*0.8, cx+size, cy+size*0.8],
                 fill=(255, 255, 255, 255))

    # 虹膜渐变
    iris_size = size * 0.75
    for r in range(int(iris_size), 0, -2):
        ratio = r / iris_size
        cr = int(colors['iris_dark'][0] * (1-ratio*0.3) + colors['iris_light'][0] * ratio*0.3)
        cg = int(colors['iris_dark'][1] * (1-ratio*0.3) + colors['iris_light'][1] * ratio*0.3)
        cb = int(colors['iris_dark'][2] * (1-ratio*0.3) + colors['iris_light'][2] * ratio*0.3)
        draw.ellipse([cx-r, cy-r*0.9, cx+r, cy+r*0.9], fill=(cr, cg, cb, 255))

    # 瞳孔 - 垂直椭圆（猫眼）
    pupil_h = size * 0.55
    pupil_w = size * 0.25
    draw.ellipse([cx-pupil_w, cy-pupil_h, cx+pupil_w, cy+pupil_h],
                 fill=(15, 15, 25, 255))

    # 高光大 - 左上
    hl1_size = size * 0.35
    draw.ellipse([cx-size*0.4-hl1_size*0.5, cy-size*0.35-hl1_size*0.5,
                  cx-size*0.4+hl1_size*0.5, cy-size*0.35+hl1_size*0.5],
                 fill=(255, 255, 255, 255))

    # 高光中 - 右下
    hl2_size = size * 0.2
    draw.ellipse([cx+size*0.2-hl2_size*0.5, cy+size*0.25-hl2_size*0.5,
                  cx+size*0.2+hl2_size*0.5, cy+size*0.25+hl2_size*0.5],
                 fill=(255, 255, 255, 230))

    # 高光小 - 星形闪烁
    hl3_size = size * 0.12
    draw.ellipse([cx-size*0.15, cy-size*0.5,
                  cx-size*0.15+hl3_size, cy-size*0.5+hl3_size],
                 fill=(255, 255, 255, 200))


def draw_fluffy_cheek(draw, cx, cy, size, color):
    """绘制蓬松腮红"""
    # 主腮红 - 渐变
    for r in range(int(size), 0, -2):
        alpha = int(120 * (r / size))
        draw.ellipse([cx-r, cy-r*0.6, cx+r, cy+r*0.6],
                     fill=(color[0], color[1], color[2], alpha))

    # 高光点
    draw.ellipse([cx-size*0.3, cy-size*0.2, cx-size*0.1, cy],
                 fill=(255, 255, 255, 80))


def draw_cat_ear(draw, tip_x, tip_y, ear_size, face_color, inner_color, side='left'):
    """绘制猫耳朵"""
    # 外耳
    if side == 'left':
        points = [
            (tip_x - ear_size*0.4, tip_y + ear_size*0.8),
            (tip_x, tip_y),
            (tip_x + ear_size*0.4, tip_y + ear_size*0.8)
        ]
        inner_points = [
            (tip_x - ear_size*0.2, tip_y + ear_size*0.6),
            (tip_x, tip_y + ear_size*0.15),
            (tip_x + ear_size*0.2, tip_y + ear_size*0.6)
        ]
    else:
        points = [
            (tip_x - ear_size*0.4, tip_y + ear_size*0.8),
            (tip_x, tip_y),
            (tip_x + ear_size*0.4, tip_y + ear_size*0.8)
        ]
        inner_points = [
            (tip_x - ear_size*0.2, tip_y + ear_size*0.6),
            (tip_x, tip_y + ear_size*0.15),
            (tip_x + ear_size*0.2, tip_y + ear_size*0.6)
        ]

    draw.polygon(points, fill=face_color)
    draw.polygon(inner_points, fill=inner_color)


def draw_arch_avatar():
    """Arch酱 - 白色波斯猫 + 单片眼镜"""
    img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 背景 - 冰蓝渐变
    for y in range(SIZE):
        ratio = y / SIZE
        r = int(200 - ratio * 40)
        g = int(230 - ratio * 40)
        b = 255
        draw.line([(0, y), (SIZE, y)], fill=(r, g, b, 255))

    cx, cy = SIZE // 2, SIZE // 2 + 30

    # 耳朵
    ear_size = 80
    draw_cat_ear(draw, cx - 75, cy - 160, ear_size, (255, 255, 255), (255, 220, 235), 'left')
    draw_cat_ear(draw, cx + 75, cy - 160, ear_size, (255, 255, 255), (255, 220, 235), 'right')

    # 脸部阴影
    draw.ellipse([cx-148, cy-128, cx+148, cy+138], fill=(240, 240, 245, 255))
    # 脸部主体
    draw.ellipse([cx-140, cy-130, cx+140, cy+130], fill=(255, 255, 255, 255))

    # 大眼睛
    eye_colors = {
        'iris_light': (180, 220, 255),
        'iris_dark': (80, 160, 230)
    }
    draw_anime_eye(draw, cx - 55, cy - 15, 42, eye_colors)
    draw_anime_eye(draw, cx + 55, cy - 15, 42, eye_colors)

    # 鼻子
    draw.polygon([(cx, cy + 40), (cx - 12, cy + 55), (cx + 12, cy + 55)],
                 fill=(255, 200, 210))

    # 嘴巴
    draw.arc([cx - 25, cy + 60, cx, cy + 85], 200, 340, fill=(180, 160, 160), width=3)
    draw.arc([cx, cy + 60, cx + 25, cy + 85], 200, 340, fill=(180, 160, 160), width=3)

    # 腮红
    draw_fluffy_cheek(draw, cx - 110, cy + 25, 35, (255, 180, 195))
    draw_fluffy_cheek(draw, cx + 110, cy + 25, 35, (255, 180, 195))

    # 单片眼镜 - 金色边框
    mono_x, mono_y = cx - 55, cy - 15
    draw.ellipse([mono_x - 52, mono_y - 42, mono_x + 52, mono_y + 42],
                 outline=(218, 165, 32), width=6)

    # 链条
    chain_points = []
    for i in range(12):
        x = mono_x + 52 + i * 12
        y = mono_y + i * 12
        chain_points.append((x, y))
    for i, (x, y) in enumerate(chain_points[:-1]):
        draw.ellipse([x-4, y-4, x+4, y+4], fill=(218, 165, 32))

    # 轻微柔化
    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))

    # 增强色彩
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(1.2)

    img.save(OUTPUT_DIR / "arch.png", 'PNG')
    print("  ✓ arch.png")


def draw_stack_avatar():
    """Stack喵 - 橘猫 + 蓝色兜帽"""
    img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 背景 - 奶油色渐变
    for y in range(SIZE):
        ratio = y / SIZE
        r = int(255 - ratio * 20)
        g = int(250 - ratio * 25)
        b = int(230 - ratio * 40)
        draw.line([(0, y), (SIZE, y)], fill=(r, g, b, 255))

    cx, cy = SIZE // 2, SIZE // 2 + 30

    # 兜帽（在脸后面）
    hoodie_color = (70, 130, 180)
    draw.arc([cx - 160, cy - 220, cx + 160, cy + 20], 0, 180, fill=hoodie_color, width=35)

    # 耳朵 - 橘色带条纹
    ear_size = 80
    # 左耳
    draw.polygon([(cx-75-30, cy-160+70), (cx-75, cy-160), (cx-75+30, cy-160+70)],
                 fill=(255, 180, 100))
    draw.polygon([(cx-75-15, cy-160+55), (cx-75, cy-160+20), (cx-75+15, cy-160+55)],
                 fill=(255, 200, 180))
    # 虎斑纹
    draw.line([(cx-75-10, cy-160+40), (cx-75+10, cy-160+50)], fill=(230, 140, 70), width=3)

    # 右耳
    draw.polygon([(cx+75-30, cy-160+70), (cx+75, cy-160), (cx+75+30, cy-160+70)],
                 fill=(255, 180, 100))
    draw.polygon([(cx+75-15, cy-160+55), (cx+75, cy-160+20), (cx+75+15, cy-160+55)],
                 fill=(255, 200, 180))
    draw.line([(cx+75-10, cy-160+40), (cx+75+10, cy-160+50)], fill=(230, 140, 70), width=3)

    # 脸部阴影
    draw.ellipse([cx-148, cy-128, cx+148, cy+138], fill=(245, 200, 140))
    # 脸部主体 - 橘色
    draw.ellipse([cx-140, cy-130, cx+140, cy+130], fill=(255, 190, 110))

    # 虎斑纹
    stripe_color = (230, 150, 80)
    # 额头纹
    draw.arc([cx - 60, cy - 110, cx + 60, cy - 50], 0, 180, fill=stripe_color, width=4)
    draw.line([(cx - 40, cy - 90), (cx - 40, cy - 60)], fill=stripe_color, width=4)
    draw.line([(cx + 40, cy - 90), (cx + 40, cy - 60)], fill=stripe_color, width=4)

    # 大眼睛 - 琥珀色
    eye_colors = {
        'iris_light': (255, 220, 120),
        'iris_dark': (255, 170, 50)
    }
    draw_anime_eye(draw, cx - 55, cy - 15, 42, eye_colors)
    draw_anime_eye(draw, cx + 55, cy - 15, 42, eye_colors)

    # 鼻子
    draw.polygon([(cx, cy + 40), (cx - 12, cy + 55), (cx + 12, cy + 55)],
                 fill=(255, 150, 150))

    # 嘴巴 - 更开心的弧度
    draw.arc([cx - 30, cy + 58, cx, cy + 90], 200, 340, fill=(180, 140, 140), width=3)
    draw.arc([cx, cy + 58, cx + 30, cy + 90], 200, 340, fill=(180, 140, 140), width=3)

    # 腮红
    draw_fluffy_cheek(draw, cx - 110, cy + 25, 35, (255, 180, 170))
    draw_fluffy_cheek(draw, cx + 110, cy + 25, 35, (255, 180, 170))

    # 胡须
    whisker_color = (200, 170, 150)
    for i in range(3):
        wy = cy + 50 + i * 12
        draw.line([(cx - 85, wy), (cx - 140, wy - 8)], fill=whisker_color, width=2)
        draw.line([(cx + 85, wy), (cx + 140, wy - 8)], fill=whisker_color, width=2)

    # 扳手 - 在右下角
    w_x, w_y = cx + 120, cy + 100
    # 扳手柄
    draw.rectangle([w_x - 8, w_y - 60, w_x + 8, w_y + 40], fill=(100, 100, 110))
    # 扳手头
    draw.ellipse([w_x - 25, w_y - 80, w_x + 25, w_y - 40], fill=(100, 100, 110))
    draw.ellipse([w_x - 12, w_y - 70, w_x + 12, w_y - 50], fill=(255, 190, 110))  # 橙色手柄

    # 轻微柔化
    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(1.2)

    img.save(OUTPUT_DIR / "stack.png", 'PNG')
    print("  ✓ stack.png")


def draw_pixel_avatar():
    """Pixel咪 - 三花猫 + 贝雷帽"""
    img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 背景 - 粉紫渐变
    for y in range(SIZE):
        ratio = y / SIZE
        r = int(240 - ratio * 30)
        g = int(210 - ratio * 40)
        b = int(255 - ratio * 20)
        draw.line([(0, y), (SIZE, y)], fill=(r, g, b, 255))

    cx, cy = SIZE // 2, SIZE // 2 + 30

    # 贝雷帽（在耳朵上面）
    beret_color = (219, 112, 147)
    # 帽子主体
    draw.ellipse([cx - 100, cy - 200, cx + 100, cy - 120], fill=beret_color)
    # 帽子阴影
    draw.ellipse([cx - 90, cy - 185, cx + 90, cy - 130], fill=(240, 130, 165))
    # 帽球
    draw.ellipse([cx - 18, cy - 235, cx + 18, cy - 200], fill=beret_color)
    draw.ellipse([cx - 12, cy - 228, cx + 12, cy - 208], fill=(240, 130, 165))

    # 耳朵
    ear_size = 75
    # 左耳 - 带黑褐色
    draw.polygon([(cx-70-28, cy-155+65), (cx-70, cy-155), (cx-70+28, cy-155+65)],
                 fill=(180, 140, 120))
    draw.polygon([(cx-70-14, cy-155+50), (cx-70, cy-155+18), (cx-70+14, cy-155+50)],
                 fill=(255, 200, 210))
    # 右耳 - 白色
    draw.polygon([(cx+70-28, cy-155+65), (cx+70, cy-155), (cx+70+28, cy-155+65)],
                 fill=(255, 252, 250))
    draw.polygon([(cx+70-14, cy-155+50), (cx+70, cy-155+18), (cx+70+14, cy-155+50)],
                 fill=(255, 200, 210))

    # 脸部阴影
    draw.ellipse([cx-148, cy-128, cx+148, cy+138], fill=(248, 245, 240))
    # 脸部主体 - 白色
    draw.ellipse([cx-140, cy-130, cx+140, cy+130], fill=(255, 252, 250))

    # 三花斑块
    # 橘色斑块 - 右脸
    draw.ellipse([cx + 40, cy - 30, cx + 120, cy + 50], fill=(255, 180, 130))
    # 黑褐色斑块 - 左下
    draw.ellipse([cx - 110, cy + 20, cx - 40, cy + 90], fill=(160, 120, 100))

    # 大眼睛 - 紫色
    eye_colors = {
        'iris_light': (220, 180, 255),
        'iris_dark': (180, 130, 240)
    }
    draw_anime_eye(draw, cx - 55, cy - 15, 42, eye_colors)
    draw_anime_eye(draw, cx + 55, cy - 15, 42, eye_colors)

    # 鼻子
    draw.polygon([(cx, cy + 40), (cx - 12, cy + 55), (cx + 12, cy + 55)],
                 fill=(255, 180, 195))

    # 嘴巴 - 文艺微笑
    draw.arc([cx - 25, cy + 60, cx, cy + 88], 200, 340, fill=(180, 150, 160), width=3)
    draw.arc([cx, cy + 60, cx + 25, cy + 88], 200, 340, fill=(180, 150, 160), width=3)

    # 腮红
    draw_fluffy_cheek(draw, cx - 110, cy + 25, 35, (255, 190, 205))
    draw_fluffy_cheek(draw, cx + 110, cy + 25, 35, (255, 190, 205))

    # 画笔 - 在右下角
    brush_x, brush_y = cx + 130, cy + 90
    # 笔杆
    draw.rectangle([brush_x - 6, brush_y - 80, brush_x + 6, brush_y + 20], fill=(200, 160, 120))
    # 金属环
    draw.rectangle([brush_x - 10, brush_y - 25, brush_x + 10, brush_y - 15], fill=(180, 180, 190))
    # 笔刷毛 - 彩色
    draw.polygon([
        (brush_x - 12, brush_y - 25),
        (brush_x, brush_y - 70),
        (brush_x + 12, brush_y - 25)
    ], fill=(255, 150, 200))
    # 颜料点
    draw.ellipse([brush_x - 5, brush_y - 55, brush_x + 5, brush_y - 45], fill=(100, 200, 255))

    # 轻微柔化
    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(1.3)

    img.save(OUTPUT_DIR / "pixel.png", 'PNG')
    print("  ✓ pixel.png")


def main():
    print("🎨 生成可爱猫猫头像 v2...\n")
    print("=" * 50)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n📷 绘制 Arch酱（白色波斯猫 + 单片眼镜）")
    draw_arch_avatar()

    print("\n📷 绘制 Stack喵（橘猫 + 蓝色兜帽）")
    draw_stack_avatar()

    print("\n📷 绘制 Pixel咪（三花猫 + 贝雷帽）")
    draw_pixel_avatar()

    print("\n" + "=" * 50)
    print("✨ 头像生成完成！")
    print(f"📁 位置: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
