"""icon_generator.py - Generate a simple ICO icon for the installer."""

from PIL import Image, ImageDraw
import os


def make_icon() -> Image.Image:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Outer circle
    d.ellipse([10, 10, 246, 246], fill=(60, 200, 120, 255),
              outline=(20, 60, 30, 255), width=8)
    # Fan blades (4 quadrants, white)
    blade = (255, 255, 255, 240)
    d.pieslice([40, 40, 216, 216], 0,   90,   fill=blade)
    d.pieslice([40, 40, 216, 216], 90,  180,  fill=blade)
    d.pieslice([40, 40, 216, 216], 180, 270,  fill=blade)
    d.pieslice([40, 40, 216, 216], 270, 360,  fill=blade)
    # Center hub
    d.ellipse([100, 100, 156, 156], fill=(60, 200, 120, 255),
              outline=(20, 60, 30, 255), width=4)
    # "G" badge bottom-right (Game Mode indicator)
    d.ellipse([150, 150, 240, 240], fill=(220, 30, 30, 255),
              outline=(255, 255, 255, 255), width=6)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arial.ttf", 80)
    except Exception:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), "G", font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text((195 - w // 2, 195 - h // 2), "G",
           fill=(255, 255, 255, 255), font=font)
    return img


if __name__ == "__main__":
    icon = make_icon()
    # Save as multi-size ICO
    icon.save("icon.ico", format="ICO",
              sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon.ico created (256x256, multi-resolution)")
