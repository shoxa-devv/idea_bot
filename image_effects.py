from PIL import Image, ImageFilter, ImageEnhance, ImageDraw, ImageFont
import io
import random
import math


def apply_glitch_effect(image_bytes: bytes) -> bytes:
    """Apply a glitch/distortion effect to an image."""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert('RGB')
    width, height = img.size
    
    result = img.copy()
    pixels = result.load()
    
    # Add random horizontal shifts
    for _ in range(random.randint(5, 15)):
        y = random.randint(0, height - 1)
        shift_height = random.randint(1, max(2, height // 20))
        shift_x = random.randint(-width // 4, width // 4)
        
        for dy in range(shift_height):
            if y + dy >= height:
                break
            for x in range(width):
                src_x = (x - shift_x) % width
                pixels[x, y + dy] = img.getpixel((src_x, y + dy))
    
    # Add RGB channel separation
    r, g, b = result.split()
    r_shifted = Image.new('L', (width, height))
    r_pixels = r_shifted.load()
    r_orig = r.load()
    shift = random.randint(3, 8)
    for y_pos in range(height):
        for x_pos in range(width):
            src_x = (x_pos + shift) % width
            r_pixels[x_pos, y_pos] = r_orig[src_x, y_pos]
    
    result = Image.merge('RGB', (r_shifted, g, b))
    
    # Add random colored lines
    draw = ImageDraw.Draw(result)
    for _ in range(random.randint(3, 8)):
        y_line = random.randint(0, height - 1)
        color = random.choice([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255)])
        draw.line([(0, y_line), (width, y_line)], fill=color, width=1)
    
    output = io.BytesIO()
    result.save(output, format='PNG')
    output.seek(0)
    return output.getvalue()


def apply_matrix_effect(image_bytes: bytes) -> bytes:
    """Apply a Matrix-style green tint effect."""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert('RGB')
    width, height = img.size
    
    # Convert to green channel only
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(0.5)
    
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            gray = int(0.299 * r + 0.587 * g + 0.114 * b)
            pixels[x, y] = (0, min(255, int(gray * 1.5)), 0)
    
    # Add "rain" characters
    draw = ImageDraw.Draw(img)
    chars = "01アイウエオカキクケコサシスセソ"
    for _ in range(width // 3):
        x_pos = random.randint(0, width - 1)
        y_start = random.randint(0, height - 1)
        length = random.randint(3, 10)
        for j in range(length):
            y_pos = y_start + j * 12
            if y_pos >= height:
                break
            char = random.choice(chars)
            brightness = max(0, 255 - j * 25)
            draw.text((x_pos, y_pos), char, fill=(0, brightness, 0))
    
    output = io.BytesIO()
    img.save(output, format='PNG')
    output.seek(0)
    return output.getvalue()


def apply_hacker_effect(image_bytes: bytes) -> bytes:
    """Apply a hacker/terminal style effect."""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert('RGB')
    width, height = img.size
    
    # Make it darker with green tint
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(0.3)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            gray = int(0.299 * r + 0.587 * g + 0.114 * b)
            pixels[x, y] = (0, gray, int(gray * 0.3))
    
    # Add scanlines
    draw = ImageDraw.Draw(img)
    for y_line in range(0, height, 3):
        draw.line([(0, y_line), (width, y_line)], fill=(0, 0, 0), width=1)
    
    # Add corner brackets (like targeting)
    bracket_size = min(width, height) // 6
    bracket_width = 3
    green = (0, 255, 0)
    
    # Top-left
    draw.line([(20, 20), (20 + bracket_size, 20)], fill=green, width=bracket_width)
    draw.line([(20, 20), (20, 20 + bracket_size)], fill=green, width=bracket_width)
    # Top-right
    draw.line([(width - 20 - bracket_size, 20), (width - 20, 20)], fill=green, width=bracket_width)
    draw.line([(width - 20, 20), (width - 20, 20 + bracket_size)], fill=green, width=bracket_width)
    # Bottom-left
    draw.line([(20, height - 20), (20 + bracket_size, height - 20)], fill=green, width=bracket_width)
    draw.line([(20, height - 20 - bracket_size), (20, height - 20)], fill=green, width=bracket_width)
    # Bottom-right
    draw.line([(width - 20 - bracket_size, height - 20), (width - 20, height - 20)], fill=green, width=bracket_width)
    draw.line([(width - 20, height - 20 - bracket_size), (width - 20, height - 20)], fill=green, width=bracket_width)
    
    # Add text overlays
    texts = ["ACCESSING...", "TARGET LOCKED", "SCANNING...", "DECRYPTING...", "BREACH DETECTED"]
    text = random.choice(texts)
    draw.text((30, height - 50), text, fill=(0, 255, 0))
    draw.text((30, 30), f"ID: {random.randint(10000, 99999)}", fill=(0, 255, 0))
    
    output = io.BytesIO()
    img.save(output, format='PNG')
    output.seek(0)
    return output.getvalue()


def apply_pixel_effect(image_bytes: bytes) -> bytes:
    """Apply a pixelation effect."""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert('RGB')
    width, height = img.size
    
    pixel_size = max(width, height) // 30
    small = img.resize((width // pixel_size, height // pixel_size), Image.NEAREST)
    result = small.resize((width, height), Image.NEAREST)
    
    output = io.BytesIO()
    result.save(output, format='PNG')
    output.seek(0)
    return output.getvalue()


def apply_negative_effect(image_bytes: bytes) -> bytes:
    """Apply a negative/invert effect."""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert('RGB')
    width, height = img.size
    
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            pixels[x, y] = (255 - r, 255 - g, 255 - b)
    
    output = io.BytesIO()
    img.save(output, format='PNG')
    output.seek(0)
    return output.getvalue()


def apply_red_alert_effect(image_bytes: bytes) -> bytes:
    """Apply a red alert/danger effect."""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert('RGB')
    width, height = img.size
    
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)
    
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            gray = int(0.299 * r + 0.587 * g + 0.114 * b)
            pixels[x, y] = (min(255, int(gray * 1.5 + 50)), int(gray * 0.2), int(gray * 0.1))
    
    draw = ImageDraw.Draw(img)
    
    # Add warning borders
    for i in range(5):
        draw.rectangle(
            [(i * 3, i * 3), (width - 1 - i * 3, height - 1 - i * 3)],
            outline=(255, 0, 0),
            width=2
        )
    
    # Add warning text
    draw.text((width // 2 - 60, 20), "⚠ DANGER ⚠", fill=(255, 255, 0))
    draw.text((width // 2 - 50, height - 40), "ALERT!", fill=(255, 0, 0))
    
    output = io.BytesIO()
    img.save(output, format='PNG')
    output.seek(0)
    return output.getvalue()


def apply_ghost_effect(image_bytes: bytes) -> bytes:
    """Apply a ghostly/spooky effect."""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert('RGB')
    width, height = img.size
    
    # Make it blue-ish and dark
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(0.4)
    
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            gray = int(0.299 * r + 0.587 * g + 0.114 * b)
            pixels[x, y] = (int(gray * 0.3), int(gray * 0.3), min(255, int(gray * 1.2)))
    
    # Add blur for ghostly feel
    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    
    # Add some "ghost" circles
    draw = ImageDraw.Draw(img)
    for _ in range(3):
        cx = random.randint(width // 4, 3 * width // 4)
        cy = random.randint(height // 4, 3 * height // 4)
        radius = random.randint(20, 50)
        for r in range(radius, 0, -1):
            alpha = int(30 * (1 - r / radius))
            draw.ellipse(
                [(cx - r, cy - r), (cx + r, cy + r)],
                outline=(200, 200, 255),
                width=1
            )
    
    output = io.BytesIO()
    img.save(output, format='PNG')
    output.seek(0)
    return output.getvalue()


def apply_spy_effect(image_bytes: bytes) -> bytes:
    """Apply a spy camera/surveillance effect."""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert('RGB')
    width, height = img.size
    
    # Slight green tint like night vision
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            gray = int(0.299 * r + 0.587 * g + 0.114 * b)
            noise = random.randint(-10, 10)
            pixels[x, y] = (
                max(0, min(255, int(gray * 0.6) + noise)),
                max(0, min(255, int(gray * 1.1) + noise)),
                max(0, min(255, int(gray * 0.6) + noise))
            )
    
    draw = ImageDraw.Draw(img)
    
    # Add crosshair
    cx, cy = width // 2, height // 2
    cross_size = min(width, height) // 8
    draw.line([(cx - cross_size, cy), (cx + cross_size, cy)], fill=(0, 255, 0), width=1)
    draw.line([(cx, cy - cross_size), (cx, cy + cross_size)], fill=(0, 255, 0), width=1)
    draw.ellipse(
        [(cx - cross_size // 2, cy - cross_size // 2), (cx + cross_size // 2, cy + cross_size // 2)],
        outline=(0, 255, 0), width=1
    )
    
    # Add "REC" indicator
    draw.ellipse([(15, 15), (25, 25)], fill=(255, 0, 0))
    draw.text((30, 12), "REC", fill=(255, 0, 0))
    
    # Add timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    draw.text((width - 180, height - 25), timestamp, fill=(255, 255, 255))
    
    # Add "CAM" label
    draw.text((width - 80, 12), f"CAM-{random.randint(1, 99):02d}", fill=(255, 255, 255))
    
    output = io.BytesIO()
    img.save(output, format='PNG')
    output.seek(0)
    return output.getvalue()


# Map effect names to functions
EFFECT_FUNCTIONS = {
    'glitch': apply_glitch_effect,
    'matrix': apply_matrix_effect,
    'hacker': apply_hacker_effect,
    'pixel': apply_pixel_effect,
    'negative': apply_negative_effect,
    'red_alert': apply_red_alert_effect,
    'ghost': apply_ghost_effect,
    'spy': apply_spy_effect,
}


def process_image(image_bytes: bytes, effect_name: str) -> bytes:
    """Process an image with the specified effect."""
    if effect_name in EFFECT_FUNCTIONS:
        return EFFECT_FUNCTIONS[effect_name](image_bytes)
    raise ValueError(f"Unknown effect: {effect_name}")
