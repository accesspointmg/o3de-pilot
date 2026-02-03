#!/usr/bin/env python3
"""Generate icons for O3DE Pilot application."""

from PIL import Image, ImageDraw, ImageFont
import os

# Icon size
SIZE = 64
ICONS_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "gui", "Resources", "icons")

# O3DE brand colors
O3DE_BLUE = (0, 120, 212)
O3DE_DARK = (30, 30, 30)
O3DE_LIGHT = (240, 240, 240)
O3DE_ACCENT = (0, 200, 150)
AI_PURPLE = (138, 43, 226)
GEM_TEAL = (0, 180, 180)
TEMPLATE_ORANGE = (255, 140, 0)
SETTINGS_GRAY = (100, 100, 100)


def create_app_icon():
    """Main application icon - stylized 'P' for Pilot with AI sparkle."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Background circle
    draw.ellipse([4, 4, SIZE-4, SIZE-4], fill=O3DE_BLUE)
    
    # Draw 'P' shape
    draw.rectangle([18, 16, 26, 48], fill="white")  # Vertical stem
    draw.arc([18, 14, 44, 36], start=270, end=90, fill="white", width=8)  # Arc of P
    
    # AI sparkle in corner
    sparkle_color = (255, 215, 0)
    draw.polygon([(48, 8), (52, 16), (48, 24), (44, 16)], fill=sparkle_color)
    draw.polygon([(44, 12), (52, 12), (52, 20), (44, 20)], fill=sparkle_color)
    
    return img


def create_project_icon():
    """Project icon - folder with code brackets."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Folder shape
    draw.rectangle([6, 18, 58, 54], fill=O3DE_BLUE)
    draw.polygon([(6, 18), (24, 18), (28, 10), (6, 10)], fill=O3DE_BLUE)
    
    # Code brackets < >
    draw.line([(22, 30), (16, 38), (22, 46)], fill="white", width=3)
    draw.line([(42, 30), (48, 38), (42, 46)], fill="white", width=3)
    
    return img


def create_gem_icon():
    """Gem icon - diamond/gem shape (O3DE gems are modules/plugins)."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Diamond shape
    points = [
        (SIZE//2, 6),       # Top
        (SIZE-8, SIZE//3),  # Upper right
        (SIZE//2, SIZE-6),  # Bottom
        (8, SIZE//3),       # Upper left
    ]
    draw.polygon(points, fill=GEM_TEAL)
    
    # Facet lines
    draw.line([(SIZE//2, 6), (SIZE//2, SIZE-6)], fill=(0, 140, 140), width=2)
    draw.line([(8, SIZE//3), (SIZE-8, SIZE//3)], fill=(0, 140, 140), width=2)
    draw.line([(SIZE//2, 6), (8, SIZE//3)], fill=(0, 220, 220), width=2)
    draw.line([(SIZE//2, 6), (SIZE-8, SIZE//3)], fill=(0, 140, 140), width=2)
    
    # Shine
    draw.polygon([(SIZE//2, 10), (14, SIZE//3-2), (SIZE//2, SIZE//3+4)], fill=(100, 220, 220))
    
    return img


def create_template_icon():
    """Template icon - document with layout grid."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Document shape with folded corner
    draw.rectangle([12, 6, 52, 58], fill=TEMPLATE_ORANGE)
    draw.polygon([(40, 6), (52, 18), (40, 18)], fill=(200, 110, 0))
    
    # Layout lines
    draw.rectangle([18, 24, 46, 32], fill="white")  # Header
    draw.rectangle([18, 38, 30, 50], fill="white")  # Left column
    draw.rectangle([34, 38, 46, 50], fill="white")  # Right column
    
    return img


def create_settings_icon():
    """Settings icon - gear/cog."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Outer gear
    center = SIZE // 2
    outer_r = 24
    inner_r = 10
    
    # Draw gear teeth
    import math
    teeth = 8
    for i in range(teeth):
        angle = i * (360 / teeth) * math.pi / 180
        next_angle = (i + 0.5) * (360 / teeth) * math.pi / 180
        
        x1 = center + outer_r * math.cos(angle)
        y1 = center + outer_r * math.sin(angle)
        x2 = center + (outer_r - 6) * math.cos(next_angle)
        y2 = center + (outer_r - 6) * math.sin(next_angle)
        
        draw.ellipse([x1-5, y1-5, x1+5, y1+5], fill=SETTINGS_GRAY)
    
    # Main gear body
    draw.ellipse([center-18, center-18, center+18, center+18], fill=SETTINGS_GRAY)
    
    # Center hole
    draw.ellipse([center-8, center-8, center+8, center+8], fill=(60, 60, 60))
    draw.ellipse([center-5, center-5, center+5, center+5], fill=SETTINGS_GRAY)
    
    return img


def create_ai_icon():
    """AI icon - brain/neural network with sparkles."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Brain shape (simplified)
    draw.ellipse([10, 14, 54, 50], fill=AI_PURPLE)
    
    # Neural network nodes
    nodes = [(20, 24), (32, 20), (44, 24), (16, 34), (32, 32), (48, 34), (24, 44), (40, 44)]
    for x, y in nodes:
        draw.ellipse([x-4, y-4, x+4, y+4], fill="white")
    
    # Connections
    connections = [
        ((20, 24), (32, 32)), ((32, 20), (32, 32)), ((44, 24), (32, 32)),
        ((16, 34), (32, 32)), ((48, 34), (32, 32)),
        ((32, 32), (24, 44)), ((32, 32), (40, 44))
    ]
    for (x1, y1), (x2, y2) in connections:
        draw.line([(x1, y1), (x2, y2)], fill=(180, 130, 255), width=2)
    
    # Sparkles
    sparkle_color = (255, 215, 0)
    for sx, sy in [(8, 8), (52, 6), (56, 50)]:
        draw.polygon([(sx, sy-4), (sx+3, sy), (sx, sy+4), (sx-3, sy)], fill=sparkle_color)
    
    return img


def main():
    os.makedirs(ICONS_DIR, exist_ok=True)
    
    icons = {
        "app_icon.png": create_app_icon(),
        "project.png": create_project_icon(),
        "gem.png": create_gem_icon(),
        "template.png": create_template_icon(),
        "settings.png": create_settings_icon(),
        "ai.png": create_ai_icon(),
    }
    
    for name, img in icons.items():
        path = os.path.join(ICONS_DIR, name)
        img.save(path, "PNG")
        print(f"Created: {path}")
    
    print("\nAll icons generated successfully!")


if __name__ == "__main__":
    main()
