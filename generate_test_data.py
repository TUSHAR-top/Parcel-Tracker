import os
import json
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def create_cardboard_bg(width, height):
    """Generates a textured brown cardboard box background."""
    img = Image.new("RGB", (width, height), (180, 130, 80))
    draw = ImageDraw.Draw(img)
    # Add subtle fiber textures
    for _ in range(300):
        x1 = random.randint(0, width - 1)
        y1 = random.randint(0, height - 1)
        x2 = x1 + random.randint(-5, 5)
        y2 = y1 + random.randint(-5, 5)
        draw.line([x1, y1, x2, y2], fill=(160, 115, 65), width=1)
    return img

def draw_fake_barcode(draw, x, y, width, height):
    """Draws a vertical barcode pattern of varying widths."""
    curr_x = x
    while curr_x < x + width:
        bar_w = random.choice([2, 4, 6, 8])
        space_w = random.choice([2, 4, 6])
        draw.rectangle([curr_x, y, curr_x + bar_w, y + height], fill=(0, 0, 0))
        curr_x += bar_w + space_w

def generate_label_image(status_type, filename, output_dir):
    """Generates a mock parcel image based on scanner status types."""
    width, height = 800, 600
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, filename)

    # 1. Empty Conveyor State
    if status_type == "empty_conveyor":
        # Steel/gray metallic background representing a conveyor belt
        img = Image.new("RGB", (width, height), (80, 85, 90))
        draw = ImageDraw.Draw(img)
        # Conveyor roller lines
        for y in range(0, height, 80):
            draw.line([0, y, width, y], fill=(50, 52, 55), width=8)
            draw.line([0, y + 4, width, y + 4], fill=(110, 115, 120), width=2)
        img.save(file_path, "JPEG")
        return file_path

    # Standard starting point: Cardboard Box base
    img = create_cardboard_bg(width, height)
    draw = ImageDraw.Draw(img)

    # 2. Parcel without label
    if status_type == "parcel_without_label":
        # Draw tape flaps representing a plain box with no label
        draw.line([0, height//2, width, height//2], fill=(110, 80, 50), width=4)
        img.save(file_path, "JPEG")
        return file_path

    # 3. Partial Parcel
    if status_type == "partial_parcel":
        # Crop package showing only a portion in the corner
        label_bg = Image.new("RGB", (250, 200), (245, 245, 245))
        lbl_draw = ImageDraw.Draw(label_bg)
        lbl_draw.text((10, 10), "PARTIAL LABEL", fill=(0, 0, 0))
        draw_fake_barcode(lbl_draw, 10, 50, 200, 60)
        img.paste(label_bg, (-50, -50)) # Pasted off-screen
        img.save(file_path, "JPEG")
        return file_path

    # 4. Multiple Parcels
    if status_type == "multiple_parcels":
        # Draw multiple small boxes/labels in different corners
        # Box 1
        draw.rectangle([50, 50, 350, 500], fill=(160, 115, 65), outline=(100, 70, 40), width=5)
        # Label 1
        draw.rectangle([80, 80, 320, 320], fill=(255, 255, 255))
        draw_fake_barcode(draw, 100, 100, 200, 80)
        # Box 2
        draw.rectangle([420, 100, 750, 550], fill=(150, 110, 60), outline=(90, 65, 35), width=5)
        # Label 2
        draw.rectangle([450, 150, 720, 400], fill=(250, 250, 250))
        draw_fake_barcode(draw, 470, 180, 220, 80)
        img.save(file_path, "JPEG")
        return file_path

    # Standard single label setup
    label_w, label_h = 420, 320
    label_x = (width - label_w) // 2
    label_y = (height - label_h) // 2

    # Draw the white label background
    draw.rectangle([label_x, label_y, label_x + label_w, label_y + label_h], fill=(255, 255, 255), outline=(50, 50, 50), width=2)
    lbl_img = Image.new("RGB", (label_w, label_h), (255, 255, 255))
    lbl_draw = ImageDraw.Draw(lbl_img)

    # Pre-generate label contents
    carriers = ["UPS", "FedEx", "USPS", "DHL"]
    carrier = random.choice(carriers)

    if carrier == "UPS":
        lbl_draw.rectangle([0, 0, label_w, 40], fill=(74, 43, 30)) # Brown top
        lbl_draw.text((10, 10), "UPS GROUND", fill=(255, 255, 255))
        tracking = f"1Z999AA1012345{random.randint(100, 999)}4"
        weight = f"{random.randint(5, 45)}.5 LBS"
    elif carrier == "FedEx":
        lbl_draw.rectangle([0, 0, label_w, 40], fill=(78, 20, 140)) # FedEx Purple
        lbl_draw.text((10, 10), "FEDEX EXPRESS", fill=(255, 255, 255))
        tracking = f"{random.randint(4000, 4999)} {random.randint(5000, 5999)} {random.randint(6000, 6999)}"
        weight = f"{random.randint(1, 20)} LBS"
    elif carrier == "USPS":
        lbl_draw.rectangle([0, 0, label_w, 40], fill=(25, 49, 107)) # Navy blue
        lbl_draw.text((10, 10), "USPS PRIORITY MAIL", fill=(255, 255, 255))
        tracking = f"94001118995627228{random.randint(100, 999)}3"
        weight = f"{random.randint(2, 10)}.2 LBS"
    else: # DHL
        lbl_draw.rectangle([0, 0, label_w, 40], fill=(255, 204, 0)) # DHL Yellow
        lbl_draw.text((10, 10), "DHL EXPRESS", fill=(212, 5, 17)) # Red text
        tracking = f"42055{random.randint(1000000, 9999999)}"
        weight = f"{random.randint(1, 15)} KG"

    sender_name = random.choice(["AMAZON DISTRIB", "SHOPIFY CENTER", "TARGET DIRECT", "ZIPLINE INC", "LOGISTICS ACME"])
    recipient_name = random.choice(["HELEN SMITH", "GARY CHEN", "ROBERT JOHNSON", "EMILY DAVIS", "SARAH CONNOR"])
    dims = f"{random.randint(10, 24)}X{random.randint(8, 16)}X{random.randint(6, 12)}"

    lbl_draw.text((10, 50), f"FROM: {sender_name}", fill=(0, 0, 0))
    lbl_draw.text((10, 65), "100 MAIN STREET, INDUSTRIAL PARK", fill=(80, 80, 80))
    
    lbl_draw.text((10, 90), f"TO: {recipient_name}", fill=(0, 0, 0))
    lbl_draw.text((10, 105), f"APT {random.randint(1, 50)}, {random.randint(100, 999)} SUNSET BLVD, CA 90025", fill=(0, 0, 0))
    
    lbl_draw.text((10, 130), f"WEIGHT: {weight}", fill=(0, 0, 0))
    lbl_draw.text((200, 130), f"DIMS: {dims}", fill=(0, 0, 0))

    # Draw fake barcode
    draw_fake_barcode(lbl_draw, 10, 165, label_w - 20, 90)
    lbl_draw.text((10, 265), f"TRACKING: {tracking}", fill=(0, 0, 0))

    # Apply special states to standard labels
    if status_type == "clean_label":
        img.paste(lbl_img, (label_x, label_y))
    elif status_type == "blurred":
        img.paste(lbl_img, (label_x, label_y))
        # Blur the entire composite to represent camera motion/defocus
        img = img.filter(ImageFilter.GaussianBlur(radius=6))
    elif status_type == "blocked_label":
        # Draw a black marker line or tape band over the barcode and tracking text
        img.paste(lbl_img, (label_x, label_y))
        draw_comp = ImageDraw.Draw(img)
        # Block the barcode
        draw_comp.rectangle([label_x + 50, label_y + 180, label_x + label_w - 50, label_y + 240], fill=(20, 22, 25))
        # Block carrier logo or sender info
        draw_comp.polygon([(label_x, label_y), (label_x + 200, label_y), (label_x + 100, label_y + 80)], fill=(40, 42, 45))
    elif status_type == "low_confidence":
        # Add high levels of visual noise or compression lines
        img.paste(lbl_img, (label_x, label_y))
        draw_comp = ImageDraw.Draw(img)
        for i in range(0, width, 5):
            draw_comp.line([i, 0, i, height], fill=(130, 130, 130), width=1) # Scanning lines
        # Apply slight blur to degrade text
        img = img.filter(ImageFilter.GaussianBlur(radius=2))

    img.save(file_path, "JPEG", quality=85)
    return file_path

def generate_all_test_data(output_dir="test_images"):
    """Generates exactly 18 test images matching requirement counts."""
    # Count maps
    counts = {
        "clean_label": 10,
        "blurred": 3,
        "empty_conveyor": 2,
        "blocked_label": 1,
        "multiple_parcels": 1,
        "partial_parcel": 1,
        "parcel_without_label": 1
    }

    manifest = []
    index = 1

    for state_type, count in counts.items():
        for i in range(count):
            filename = f"test_parcel_{index:02d}_{state_type}.jpg"
            file_path = generate_label_image(state_type, filename, output_dir)
            manifest.append({
                "index": index,
                "filename": filename,
                "type": state_type,
                "path": file_path
            })
            index += 1

    # Write manifest file
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Print manifest summary
    print("\n" + "="*50)
    print("PARCEL TEST IMAGES MANIFEST")
    print("="*50)
    for item in manifest:
        print(f"[{item['index']:02d}] Type: {item['type']:25} -> {item['filename']}")
    print("="*50)
    print(f"Total images generated: {len(manifest)}")
    print(f"Manifest written to: {manifest_path}")
    print("="*50 + "\n")

if __name__ == "__main__":
    generate_all_test_data()
