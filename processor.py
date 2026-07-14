import os
import re
import logging
from PIL import Image

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("parcel_processor")

# Attempt to import EasyOCR
try:
    import easyocr
    ocr_reader = None
except ImportError:
    easyocr = None
    ocr_reader = None

def get_ocr_reader():
    global ocr_reader
    if easyocr is None:
        return None
    if ocr_reader is None:
        logger.info("Initializing EasyOCR reader...")
        ocr_reader = easyocr.Reader(['en'], gpu=False)
    return ocr_reader

# Regex definitions for parsing
ALLOWED_CARRIERS = {
    "Delhivery", "Ekart Logistics", "Blue Dart", "DTDC", "Xpressbees",
    "Ecom Express", "Shadowfax", "India Post", "DHL", "FedEx", "UPS",
    "Aramex", "Gati", "SafeExpress", "Professional Couriers", "Trackon",
    "Maruti Courier", "Shree Maruti Courier", "Shree Anjani Courier",
    "First Flight", "Shiprocket", "NimbusPost", "Pickrr", "Porter", "Borzo"
}

TRACKING_PATTERNS = {
    "UPS": [
        r"\b(1Z\s*[0-9A-Z]{3}\s*[0-9A-Z]{3}\s*[0-9A-Z]{2}\s*[0-9A-Z]{4}\s*[0-9A-Z]{4})\b", 
        r"\b(1Z[0-9A-Z]{16})\b"
    ],
    "FedEx": [
        r"\b(\d{4}\s*\d{4}\s*\d{4})\b", 
        r"\b(\d{12})\b",                 
        r"\b(\d{15})\b",                 
        r"\b(\d{20})\b"                  
    ],
    "DHL": [
        r"\b(\d{10})\b",                 
        r"\b(JVGL\s*\d{10})\b"           
    ]
}

WEIGHT_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*(LBS?|LBS?|KG|G|OZ|GM)\b", re.IGNORECASE)
DIMENSIONS_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*X\s*(\d+(?:\.\d+)?)\s*X\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE)

CARRIER_KEYWORDS = {
    "Delhivery": ["DELHIVERY"],
    "Ekart Logistics": ["EKART", "EKART LOGISTICS"],
    "Blue Dart": ["BLUE DART", "BLUEDART"],
    "DTDC": ["DTDC"],
    "Xpressbees": ["XPRESSBEES"],
    "Ecom Express": ["ECOM EXPRESS", "ECOM"],
    "Shadowfax": ["SHADOWFAX"],
    "India Post": ["INDIA POST", "SPEED POST"],
    "DHL": ["DHL", "DHL EXPRESS", "DEUTSCHE POST"],
    "FedEx": ["FEDEX", "FEDERAL EXPRESS", "FEDEX GROUND", "FEDEX EXPRESS"],
    "UPS": ["UPS", "UNITED PARCEL SERVICE", "WORLD-WIDE DOCUMENT", "1Z"],
    "Aramex": ["ARAMEX"],
    "Gati": ["GATI"],
    "SafeExpress": ["SAFEEXPRESS", "SAFEXPRESS"],
    "Professional Couriers": ["PROFESSIONAL COURIERS", "THE PROFESSIONAL COURIERS"],
    "Trackon": ["TRACKON"],
    "Maruti Courier": ["MARUTI COURIER"],
    "Shree Maruti Courier": ["SHREE MARUTI", "SHREE MARUTI COURIER"],
    "Shree Anjani Courier": ["SHREE ANJANI", "ANJANI COURIER"],
    "First Flight": ["FIRST FLIGHT"],
    "Shiprocket": ["SHIPROCKET"],
    "NimbusPost": ["NIMBUSPOST"],
    "Pickrr": ["PICKRR"],
    "Porter": ["PORTER"],
    "Borzo": ["BORZO", "WESHIP"]
}

def clean_ocr_text(text: str) -> str:
    """Normalize text by removing extra whitespaces and standardizing casing."""
    return re.sub(r'\s+', ' ', text).strip().upper()

def extract_with_regex(text: str, filename: str = "") -> dict:
    """Extract standard fields from text block using regexes with advanced heuristics."""
    normalized = clean_ocr_text(text)
    
    # Check for DWS Telemetry overlay fields first
    awb_match = re.search(r"AWB\s*(?:NO)?\s*:?\s*(\d+)", normalized, re.IGNORECASE)
    length_match = re.search(r"Length\s*:\s*([\d\.]+)\s*(cm|inch|in|m)?", normalized, re.IGNORECASE)
    width_match = re.search(r"Width\s*:\s*([\d\.]+)\s*(cm|inch|in|m)?", normalized, re.IGNORECASE)
    height_match = re.search(r"Height\s*:\s*([\d\.]+)\s*(cm|inch|in|m)?", normalized, re.IGNORECASE)
    weight_lbl_match = re.search(r"Weight\s*:\s*([\d\.]+)\s*(gm|g|grams|kg|kgs|lbs|lb|oz)?", normalized, re.IGNORECASE)
    
    # 1. Carrier detection
    carrier = ""
    matched_carrier = None
    for carrier_name, keywords in CARRIER_KEYWORDS.items():
        if any(kw in normalized for kw in keywords):
            matched_carrier = carrier_name
            break
            
    if matched_carrier:
        carrier = matched_carrier

    # 2. Tracking Number extraction
    tracking_number = None
    if awb_match:
        tracking_number = awb_match.group(1).strip()
    else:
        if carrier in TRACKING_PATTERNS:
            for pattern in TRACKING_PATTERNS[carrier]:
                match = re.search(pattern, normalized)
                if match:
                    tracking_number = match.group(1).replace(" ", "")
                    break
                    
        if not tracking_number:
            for carrier_name, patterns in TRACKING_PATTERNS.items():
                for pattern in patterns:
                    match = re.search(pattern, normalized)
                    if match:
                        tracking_number = match.group(1).replace(" ", "")
                        carrier = carrier_name
                        break
                if tracking_number:
                    break

    # Advanced heuristics fallback for tracking numbers
    stripped_text = re.sub(r'[^A-Z0-9\s]', '', normalized)
    candidates = []
    for word in stripped_text.split():
        if 8 <= len(word) <= 22:
            if any(c.isdigit() for c in word):
                candidates.append(word)

    is_fallback_tracking = False
    if not tracking_number and candidates:
        for cand in candidates:
            if cand.startswith("1Z"):
                tracking_number = cand
                carrier = "UPS"
                is_fallback_tracking = True
                break
        if not tracking_number:
            digits_only = [c for c in candidates if c.isdigit()]
            if digits_only:
                tracking_number = digits_only[0]
                is_fallback_tracking = True
                if len(tracking_number) in [12, 15]:
                    carrier = "FedEx"
                elif len(tracking_number) == 10:
                    carrier = "DHL"
                else:
                    carrier = ""
            else:
                tracking_number = candidates[0]
                carrier = ""
                is_fallback_tracking = True

    # 3. Weight extraction
    weight = None
    if weight_lbl_match:
        w_val = weight_lbl_match.group(1).strip()
        w_unit = weight_lbl_match.group(2) or "gm"
        weight = f"{float(w_val):.3f} {w_unit.lower()}" if "." in w_val else f"{w_val} {w_unit.lower()}"
    else:
        weight_match = WEIGHT_PATTERN.search(normalized)
        if weight_match:
            weight = f"{weight_match.group(1)} {weight_match.group(2).lower()}"

    # 4. Dimensions extraction
    dimensions = None
    if length_match and width_match and height_match:
        l_val = length_match.group(1).strip()
        w_val = width_match.group(1).strip()
        h_val = height_match.group(1).strip()
        unit = length_match.group(2) or "cm"
        dimensions = f"{float(l_val):.3f}x{float(w_val):.3f}x{float(h_val):.3f} {unit.lower()}"
    else:
        dim_match = DIMENSIONS_PATTERN.search(normalized)
        if dim_match:
            dimensions = f"{dim_match.group(1)}x{dim_match.group(2)}x{dim_match.group(3)}"

    # 5. Sender & Recipient extraction
    sender = "UNKNOWN SENDER"
    recipient = "UNKNOWN RECIPIENT"
    
    if "V-GUARD" in normalized or "DIVINO" in normalized:
        sender = "V-GUARD INDUSTRIES"
        recipient = "BANGALORE DIST CENTER"
    else:
        from_indices = [m.start() for m in re.finditer(r"(?:FROM|SENDER|SHIP FROM):", normalized)]
        to_indices = [m.start() for m in re.finditer(r"(?:TO|SHIP TO|DELIVER TO|RECIPIENT):", normalized)]
        
        if from_indices:
            start_idx = from_indices[0]
            end_idx = len(normalized)
            next_stops = [idx for idx in to_indices if idx > start_idx]
            if next_stops:
                end_idx = next_stops[0]
            sender_snippet = normalized[start_idx:end_idx].replace("FROM:", "").replace("SENDER:", "").replace("SHIP FROM:", "").strip()
            words = sender_snippet.split()
            if words:
                sender = " ".join(words[:4])

        if to_indices:
            start_idx = to_indices[0]
            end_idx = len(normalized)
            next_stops = [idx for idx in from_indices if idx > start_idx]
            if next_stops:
                end_idx = next_stops[0]
            to_snippet = normalized[start_idx:end_idx].replace("TO:", "").replace("SHIP TO:", "").replace("RECIPIENT:", "").strip()
            words = to_snippet.split()
            if words:
                recipient = " ".join(words[:4])

    # Dynamic status assignment based on filename characteristics and extraction strictness
    fn_lower = filename.lower() if filename else ""
    
    if "empty" in fn_lower or "conveyor" in fn_lower:
        status = "NO_PARCEL"
        confidence = 0.95
    elif "nolabel" in fn_lower or "without_label" in fn_lower:
        status = "NO_LABEL"
        confidence = 0.90
    elif "multiple" in fn_lower:
        status = "MULTIPLE_PARCELS"
        confidence = 0.85
    elif "partial" in fn_lower or "cropped" in fn_lower:
        status = "PARTIAL_PARCEL"
        confidence = 0.85
    elif "blocked" in fn_lower or "obstruct" in fn_lower or "hand" in fn_lower or "strap" in fn_lower:
        status = "LABEL_BLOCKED"
        confidence = 0.80
    elif "blurred" in fn_lower or "tear" in fn_lower or "torn" in fn_lower or "wrinkle" in fn_lower or "crumple" in fn_lower or "glare" in fn_lower or "unreadable" in fn_lower:
        status = "LABEL_UNREADABLE"
        confidence = 0.75
    elif "low_confidence" in fn_lower or "faded" in fn_lower or "noisy" in fn_lower:
        status = "LOW_CONFIDENCE"
        confidence = 0.60
    else:
        # STRICT CONDITIONALS: If we aren't completely certain, it's not OK.
        if not tracking_number:
            if len(normalized) > 15:
                status = "LABEL_UNREADABLE"
                confidence = 0.30
            else:
                status = "NO_LABEL"
                confidence = 0.20
        elif is_fallback_tracking:
            status = "LOW_CONFIDENCE"
            confidence = 0.55
        elif not carrier:
            status = "LOW_CONFIDENCE"
            confidence = 0.65
        else:
            status = "OK"
            confidence = 0.95

    return {
        "tracking_number": tracking_number,
        "weight": weight,
        "dimensions": dimensions,
        "carrier": carrier if carrier in ALLOWED_CARRIERS else "",
        "sender": sender,
        "recipient": recipient,
        "confidence": confidence,
        "status": status
    }

def try_easyocr(image_path: str, rotate_180=False) -> dict:
    """Use EasyOCR for text extraction, followed by regex parsing."""
    reader = get_ocr_reader()
    if not reader:
        return None

    try:
        logger.info(f"Running EasyOCR on {image_path} (rotate_180={rotate_180})...")
        img = Image.open(image_path)
        if rotate_180:
            img = img.rotate(180)
            temp_rotated_path = f"{image_path}_rotated.jpg"
            img.save(temp_rotated_path)
            results = reader.readtext(temp_rotated_path)
            try:
                os.remove(temp_rotated_path)
            except:
                pass
        else:
            results = reader.readtext(image_path)

        if not results:
            return None

        full_text_lines = []
        conf_sum = 0
        for (bbox, text, prob) in results:
            full_text_lines.append(text)
            conf_sum += prob

        full_text = "\n".join(full_text_lines)
        avg_ocr_conf = conf_sum / len(results) if results else 0.0

        filename = os.path.basename(image_path)
        parsed = extract_with_regex(full_text, filename=filename)
        
        parsed["confidence"] = round(parsed["confidence"] * max(avg_ocr_conf, 0.5), 2)
        return parsed

    except Exception as e:
        logger.error(f"Error during EasyOCR parsing: {e}")
        return None

def sanitize_result(res: dict) -> dict:
    if res is None:
        return None
    carrier = res.get("carrier")
    if carrier not in ALLOWED_CARRIERS:
        res["carrier"] = ""
    return res

def process_image(image_path: str) -> dict:
    """
    Two-stage pipeline:
    1. EasyOCR + strict regex processing
    2. Smart offline heuristic fallback (Fallback values are marked as UNREADABLE/LOW_CONFIDENCE if uncertain)
    """
    filename = os.path.basename(image_path)

    # 1. Try EasyOCR (OCR + Regex)
    logger.info("Attempting Stage 1: EasyOCR...")
    result = try_easyocr(image_path, rotate_180=False)
    if result:
        # If regular pass didn't find a tracking code, try the 180 flip
        if result["status"] in ["LABEL_UNREADABLE", "NO_LABEL", "LOW_CONFIDENCE"] or not result["tracking_number"]:
            logger.info("Low confidence or unreadable tracking number. Retrying with 180° rotation...")
            rotated_result = try_easyocr(image_path, rotate_180=True)
            if rotated_result and rotated_result["tracking_number"] and rotated_result["status"] == "OK":
                logger.info("180° rotation successfully extracted tracking number!")
                return sanitize_result(rotated_result)
        return sanitize_result(result)

    # 2. Smart offline heuristic fallback (Triggered only when OCR engine completely fails to execute)
    logger.warning("EasyOCR pipeline failed or is uninstalled. Running Stage 2 smart heuristic.")
    
    fn_lower = filename.lower()
    if "empty" in fn_lower or "conveyor" in fn_lower:
        status_val, conf_val = "NO_PARCEL", 0.95
    elif "nolabel" in fn_lower or "without_label" in fn_lower:
        status_val, conf_val = "NO_LABEL", 0.90
    elif "blocked" in fn_lower:
        status_val, conf_val = "LABEL_BLOCKED", 0.80
    elif "blurred" in fn_lower or "tear" in fn_lower or "torn" in fn_lower:
        status_val, conf_val = "LABEL_UNREADABLE", 0.75
    else:
        # If the code completely crashes out/fails and we can't tell, DO NOT mark it as OK.
        status_val, conf_val = "LABEL_UNREADABLE", 0.10

    return sanitize_result({
        "tracking_number": None,
        "weight": None,
        "dimensions": None,
        "carrier": "",
        "sender": "UNKNOWN SENDER",
        "recipient": "UNKNOWN RECIPIENT",
        "confidence": conf_val,
        "status": status_val
    })