"""Generate synthetic sample: never use real customer data."""
from PIL import Image, ImageDraw, ImageFont

im = Image.new("RGB", (1100, 330), "white")
draw = ImageDraw.Draw(im)
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34)
except OSError:
    font = ImageFont.load_default()
for i, line in enumerate(["OCR SERVICE EXPERIMENT", "DEMO-2026-001", "TOTAL: 12345.67"]):
    draw.text((30, 25 + i * 85), line, font=font, fill="black")
im.save("sample.png")
print("sample.png")
