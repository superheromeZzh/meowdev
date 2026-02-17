"""
手绘超可爱 kawaii 风格猫猫头像
更大眼睛、更粉腮红、更萌表情！
"""

from PIL import Image, ImageDraw, ImageFilter
from pathlib import Path
import math

OUTPUT_DIR = Path(__file__).parent / "public" / "avatars"

def draw_gradient_background(img, draw, color1, color2, size=512):
    """绘制渐变背景"""
    for y in range(size):
        ratio = y / size
        r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
        g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
        b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
        draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

def draw_kawaii_eye(draw, cx, cy, eye_color, size=55):
    """绘制 kawaii 大眼睛 - 超大、多层高光"""
    # 眼白 - 超大
    draw.ellipse([
        cx - size, cy - size,
        cx + size, cy + size
    ], fill=(255, 255, 255))

    # 虹膜 - 大而圆
    iris_size = size * 0.75
    draw.ellipse([
        cx - iris_size, cy - iris_size,
        cx + iris_size, cy + iris_size
    ], fill=eye_color)

    # 瞳孔 - 大瞳孔更萌
    pupil_size = size * 0.45
    draw.ellipse([
        cx - pupil_size, cy - pupil_size + 5,
        cx + pupil_size, cy + pupil_size + 5
    ], fill=(20, 20, 30))

    # 主高光 - 大而亮
    highlight1_size = size * 0.35
    draw.ellipse([
        cx - highlight1_size - 8, cy - highlight1_size - 15,
        cx + highlight1_size - 8, cy + highlight1_size - 15
    ], fill=(255, 255, 255))

    # 第二高光 - 小一点
    highlight2_size = size * 0.2
    draw.ellipse([
        cx + 8, cy - 5,
        cx + 8 + highlight2_size * 2, cy - 5 + highlight2_size * 2
    ], fill=(255, 255, 255, 200))

    # 第三高光 - 最小的闪光点
    draw.ellipse([
        cx - 5, cy + 15,
        cx + 10, cy + 25
    ], fill=(255, 255, 255, 180))

def draw_cat_ears(draw, cx, cy, ear_color, inner_color=(255, 200, 210)):
    """绘制可爱的猫耳朵"""
    # 左耳 - 更圆润的三角形
    left_ear = [
        (cx - 130, cy - 80),
        (cx - 85, cy - 190),
        (cx - 25, cy - 90)
    ]
    draw.polygon(left_ear, fill=ear_color)

    # 左耳内部 - 粉嫩
    left_inner = [
        (cx - 110, cy - 95),
        (cx - 85, cy - 160),
        (cx - 45, cy - 100)
    ]
    draw.polygon(left_inner, fill=inner_color)

    # 右耳
    right_ear = [
        (cx + 130, cy - 80),
        (cx + 85, cy - 190),
        (cx + 25, cy - 90)
    ]
    draw.polygon(right_ear, fill=ear_color)

    right_inner = [
        (cx + 110, cy - 95),
        (cx + 85, cy - 160),
        (cx + 45, cy - 100)
    ]
    draw.polygon(right_inner, fill=inner_color)

def draw_cute_nose(draw, cx, cy, color=(255, 150, 170)):
    """绘制小鼻子"""
    # 更圆润的三角鼻子
    points = [
        (cx, cy - 12),
        (cx - 15, cy + 10),
        (cx + 15, cy + 10)
    ]
    draw.polygon(points, fill=color)

    # 鼻子高光
    draw.ellipse([
        cx - 5, cy - 8,
        cx + 5, cy
    ], fill=(255, 200, 210))

def draw_cat_mouth(draw, cx, cy):
    """绘制可爱的猫咪嘴巴"""
    # w 形嘴巴
    draw.arc([
        cx - 35, cy - 5,
        cx - 5, cy + 25
    ], 200, 340, fill=(100, 80, 90), width=3)

    draw.arc([
        cx + 5, cy - 5,
        cx + 35, cy + 25
    ], 200, 340, fill=(100, 80, 90), width=3)

    # 中间连接线
    draw.line([
        (cx - 5, cy + 5),
        (cx, cy + 15),
        (cx + 5, cy + 5)
    ], fill=(100, 80, 90), width=2)

def draw_blush(draw, cx, cy, color=(255, 150, 180, 150)):
    """绘制腮红 - 超粉嫩"""
    # 左腮红 - 更大更明显
    draw.ellipse([
        cx - 145, cy + 5,
        cx - 75, cy + 50
    ], fill=color)

    # 右腮红
    draw.ellipse([
        cx + 75, cy + 5,
        cx + 145, cy + 50
    ], fill=color)

def draw_arch_accessories(draw, cx, cy):
    """Arch酱的标志性单片眼镜"""
    eye_y = cy - 25

    # 单片眼镜框 - 金色
    draw.ellipse([
        cx - 70 - 45, eye_y - 45,
        cx - 70 + 45, eye_y + 45
    ], outline=(218, 165, 32), width=5)

    # 镜框内部装饰
    draw.ellipse([
        cx - 70 - 42, eye_y - 42,
        cx - 70 + 42, eye_y + 42
    ], outline=(255, 215, 0), width=2)

    # 金色链条 - 更精致
    chain_points = [
        (cx - 70 + 45, eye_y),
        (cx - 30, eye_y + 30),
        (cx, eye_y + 60),
        (cx + 30, eye_y + 100),
        (cx + 60, cy + 130)
    ]
    for i in range(len(chain_points) - 1):
        draw.line([chain_points[i], chain_points[i+1]],
                  fill=(218, 165, 32), width=3)

    # 链条小装饰
    draw.ellipse([
        cx + 55, cy + 125,
        cx + 75, cy + 145
    ], fill=(218, 165, 32))

def draw_stack_accessories(draw, cx, cy):
    """Stack喵的蓝色兜帽和扳手"""
    # 蓝灰色兜帽 - 在耳朵后面
    # 先画兜帽主体
    draw.arc([
        cx - 170, cy - 230,
        cx + 170, cy + 30
    ], 0, 180, fill=(90, 130, 180), width=35)

    # 兜帽边缘装饰线
    draw.arc([
        cx - 165, cy - 220,
        cx + 165, cy + 20
    ], 0, 180, fill=(70, 110, 160), width=3)

    # 扳手 - 在右下角
    wrench_x = cx + 120
    wrench_y = cy + 80

    # 扳手柄
    draw.rectangle([
        wrench_x - 8, wrench_y - 50,
        wrench_x + 8, wrench_y + 50
    ], fill=(255, 140, 50))

    # 扳手头
    draw.ellipse([
        wrench_x - 25, wrench_y - 65,
        wrench_x + 25, wrench_y - 35
    ], fill=(255, 140, 50))
    draw.ellipse([
        wrench_x - 15, wrench_y - 58,
        wrench_x + 15, wrench_y - 42
    ], fill=(90, 130, 180))  # 背景色填充

    # 扳手尾
    draw.ellipse([
        wrench_x - 20, wrench_y + 40,
        wrench_x + 20, wrench_y + 70
    ], fill=(255, 140, 50))
    draw.ellipse([
        wrench_x - 12, wrench_y + 48,
        wrench_x + 12, wrench_y + 62
    ], fill=(90, 130, 180))

def draw_pixel_accessories(draw, cx, cy):
    """Pixel咪的贝雷帽和画笔"""
    # 贝雷帽 - 粉紫色
    draw.ellipse([
        cx - 95, cy - 200,
        cx + 95, cy - 100
    ], fill=(200, 130, 180))

    # 贝雷帽边缘
    draw.ellipse([
        cx - 105, cy - 130,
        cx + 105, cy - 90
    ], fill=(180, 110, 160))

    # 小绒球
    draw.ellipse([
        cx - 18, cy - 225,
        cx + 18, cy - 195
    ], fill=(200, 130, 180))

    # 画笔 - 在右下角
    brush_x = cx + 110
    brush_y = cy + 70

    # 画笔杆
    draw.rectangle([
        brush_x - 5, brush_y - 80,
        brush_x + 10, brush_y + 30
    ], fill=(180, 120, 80))

    # 画笔金属环
    draw.rectangle([
        brush_x - 7, brush_y - 55,
        brush_x + 12, brush_y - 45
    ], fill=(200, 180, 100))

    # 画笔毛 - 粉色
    draw.ellipse([
        brush_x - 8, brush_y - 100,
        brush_x + 13, brush_y - 55
    ], fill=(255, 150, 180))

    # 画笔毛高光
    draw.ellipse([
        brush_x - 3, brush_y - 90,
        brush_x + 5, brush_y - 70
    ], fill=(255, 200, 220))

def create_arch_avatar():
    """创建 Arch酱 头像 - 白色波斯猫 + 单片眼镜"""
    size = 512
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 渐变背景 - 冰蓝色
    draw_gradient_background(img, draw, (220, 240, 255), (180, 210, 240))

    cx, cy = size // 2, size // 2 + 30

    # 猫脸 - 白色，超级圆润
    face_radius = 155
    draw.ellipse([
        cx - face_radius, cy - face_radius,
        cx + face_radius, cy + face_radius
    ], fill=(255, 255, 255))

    # 脸部阴影（边缘）
    draw.ellipse([
        cx - face_radius + 5, cy - face_radius + 5,
        cx + face_radius - 5, cy + face_radius - 5
    ], fill=(255, 255, 255))

    # 耳朵 - 白色
    draw_cat_ears(draw, cx, cy, (255, 255, 255), (255, 220, 230))

    # 眼睛 - 冰蓝色
    eye_y = cy - 25
    draw_kawaii_eye(draw, cx - 60, eye_y, (150, 210, 255))
    draw_kawaii_eye(draw, cx + 60, eye_y, (150, 210, 255))

    # 鼻子
    draw_cute_nose(draw, cx, cy + 35, (255, 180, 190))

    # 嘴巴
    draw_cat_mouth(draw, cx, cy + 55)

    # 腮红
    draw_blush(draw, cx, cy + 10, (255, 180, 200, 140))

    # 单片眼镜（会覆盖一部分眼睛）
    draw_arch_accessories(draw, cx, cy)

    # 轻微柔化
    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))

    return img

def create_stack_avatar():
    """创建 Stack喵 头像 - 橘猫 + 兜帽 + 扳手"""
    size = 512
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 渐变背景 - 奶油黄
    draw_gradient_background(img, draw, (255, 250, 230), (255, 235, 200))

    cx, cy = size // 2, size // 2 + 30

    # 兜帽（在脸后面）
    draw_stack_accessories(draw, cx, cy)

    # 猫脸 - 橘色
    face_radius = 155
    draw.ellipse([
        cx - face_radius, cy - face_radius,
        cx + face_radius, cy + face_radius
    ], fill=(255, 190, 120))

    # 脸部花纹 - 虎斑
    # 额头条纹
    for i, offset in enumerate([-30, 0, 30]):
        stripe_w = 12 - abs(i - 1) * 2
        draw.rectangle([
            cx + offset - stripe_w//2, cy - 100,
            cx + offset + stripe_w//2, cy - 70
        ], fill=(240, 160, 80))

    # 耳朵 - 深橘色
    draw_cat_ears(draw, cx, cy, (255, 160, 90), (255, 200, 180))

    # 眼睛 - 琥珀色
    eye_y = cy - 25
    draw_kawaii_eye(draw, cx - 60, eye_y, (255, 180, 80))
    draw_kawaii_eye(draw, cx + 60, eye_y, (255, 180, 80))

    # 鼻子 - 粉色
    draw_cute_nose(draw, cx, cy + 35, (255, 160, 160))

    # 嘴巴 - 更开心的笑容
    draw_cat_mouth(draw, cx, cy + 55)

    # 腮红
    draw_blush(draw, cx, cy + 10, (255, 160, 140, 150))

    # 白色下巴
    draw.ellipse([
        cx - 60, cy + 60,
        cx + 60, cy + 130
    ], fill=(255, 240, 220))

    # 轻微柔化
    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))

    return img

def create_pixel_avatar():
    """创建 Pixel咪 头像 - 三花猫 + 贝雷帽 + 画笔"""
    size = 512
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 渐变背景 - 粉紫色
    draw_gradient_background(img, draw, (240, 220, 255), (220, 200, 245))

    cx, cy = size // 2, size // 2 + 30

    # 猫脸 - 白色底
    face_radius = 155
    draw.ellipse([
        cx - face_radius, cy - face_radius,
        cx + face_radius, cy + face_radius
    ], fill=(255, 255, 255))

    # 三花图案 - 橘色斑块
    # 左边橘色斑块
    draw.ellipse([
        cx - 150, cy - 80,
        cx - 60, cy + 20
    ], fill=(255, 180, 100))

    # 右上黑色斑块
    draw.ellipse([
        cx + 50, cy - 130,
        cx + 140, cy - 50
    ], fill=(80, 70, 75))

    # 头顶橘色斑块
    draw.ellipse([
        cx - 40, cy - 150,
        cx + 60, cy - 90
    ], fill=(255, 180, 100))

    # 贝雷帽（在耳朵后面）
    draw_pixel_accessories(draw, cx, cy)

    # 耳朵 - 三花配色
    # 左耳 - 橘色
    draw_cat_ears(draw, cx, cy, (255, 180, 100), (255, 200, 180))
    # 覆盖右耳为黑褐色
    right_ear = [
        (cx + 130, cy - 80),
        (cx + 85, cy - 190),
        (cx + 25, cy - 90)
    ]
    draw.polygon(right_ear, fill=(80, 70, 75))
    right_inner = [
        (cx + 110, cy - 95),
        (cx + 85, cy - 160),
        (cx + 45, cy - 100)
    ]
    draw.polygon(right_inner, fill=(200, 180, 190))

    # 眼睛 - 紫粉色
    eye_y = cy - 25
    draw_kawaii_eye(draw, cx - 60, eye_y, (200, 160, 220))
    draw_kawaii_eye(draw, cx + 60, eye_y, (200, 160, 220))

    # 鼻子 - 粉色
    draw_cute_nose(draw, cx, cy + 35, (255, 170, 190))

    # 嘴巴
    draw_cat_mouth(draw, cx, cy + 55)

    # 腮红
    draw_blush(draw, cx, cy + 10, (255, 180, 200, 140))

    # 白色下巴
    draw.ellipse([
        cx - 55, cy + 55,
        cx + 55, cy + 120
    ], fill=(255, 255, 255))

    # 轻微柔化
    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))

    return img

def main():
    print("🎨 手绘超可爱 kawaii 猫猫头像！\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("📷 绘制 Arch酱（白色波斯猫 + 单片眼镜）...")
    arch_img = create_arch_avatar()
    arch_img.save(OUTPUT_DIR / "arch.png", "PNG")
    print("  ✓ 保存成功！")

    print("📷 绘制 Stack喵（橘猫 + 兜帽 + 扳手）...")
    stack_img = create_stack_avatar()
    stack_img.save(OUTPUT_DIR / "stack.png", "PNG")
    print("  ✓ 保存成功！")

    print("📷 绘制 Pixel咪（三花猫 + 贝雷帽 + 画笔）...")
    pixel_img = create_pixel_avatar()
    pixel_img.save(OUTPUT_DIR / "pixel.png", "PNG")
    print("  ✓ 保存成功！")

    print("\n✨ 全部完成！三只超可爱的猫猫头像已生成！")

if __name__ == "__main__":
    main()
