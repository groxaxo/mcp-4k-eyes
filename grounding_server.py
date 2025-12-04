import os
import base64
import json
import logging
from io import BytesIO
from typing import Dict, List, Optional, Any

from fastmcp import FastMCP
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_exponential

# --- Backend SDKs ---
# We import these conditionally or handle errors if config is missing, 
# but for this script we assume requirements are installed.
try:
    from google import genai
    from google.genai import types as google_types
except ImportError:
    genai = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# --- Configuration & Logging ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("grounding_server")

# 🔧 CONFIGURATION
WEIRD_PORT = int(os.environ.get("PORT", 43210))  # Default Weird Port
PROVIDER = os.environ.get("GROUNDING_PROVIDER", "google").lower() # 'google' or 'openai'
API_KEY = os.environ.get("API_KEY")
BASE_URL = os.environ.get("BASE_URL") # Optional, for local LLMs
MODEL_NAME = os.environ.get("MODEL_NAME") # Overrides default if set

# Defaults
DEFAULT_GOOGLE_MODEL = "models/gemini-flash-latest"
MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_DIMENSION = 8000
ALLOWED_TYPES = {"button", "input", "icon", "text", "link", "image", "other"}

# Initialize FastMCP
mcp = FastMCP("Blind Agent Visual Cortex", dependencies=["google-genai", "openai", "pillow"])

# --- JSON Schema (Backend Agnostic) ---
RESPONSE_SCHEMA_DICT = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "components": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "label": {"type": "string"},
                    "type": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "box_2d": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "[ymin, xmin, ymax, xmax] normalized 0-1000"
                    }
                },
                "required": ["id", "label", "type", "box_2d"]
            }
        }
    },
    "required": ["summary", "components"]
}

# --- Image Helpers ---

def _fix_orientation(img: Image.Image) -> Image.Image:
    try:
        exif = img._getexif()
        if not exif: return img
        orientation = exif.get(274) # 274 is the Orientation tag ID
        if orientation == 3: return img.rotate(180, expand=True)
        elif orientation == 6: return img.rotate(270, expand=True)
        elif orientation == 8: return img.rotate(90, expand=True)
    except Exception:
        pass
    return img

def scale_box(box_norm: List[float], width: int, height: int) -> Dict[str, int]:
    """Converts 0-1000 normalized coords to pixels."""
    if not box_norm or len(box_norm) != 4:
        return {"error": "invalid_box"}
    
    y1, x1, y2, x2 = [max(0.0, min(1000.0, float(v))) for v in box_norm]

    abs_y1 = int(round((y1 / 1000.0) * height))
    abs_x1 = int(round((x1 / 1000.0) * width))
    abs_y2 = int(round((y2 / 1000.0) * height))
    abs_x2 = int(round((x2 / 1000.0) * width))

    # Fix degenerate
    if abs_x2 <= abs_x1: abs_x2 = min(width, abs_x1 + 1)
    if abs_y2 <= abs_y1: abs_y2 = min(height, abs_y1 + 1)

    return {
        "center_x": (abs_x1 + abs_x2) // 2,
        "center_y": (abs_y1 + abs_y2) // 2,
        "width": abs_x2 - abs_x1,
        "height": abs_y2 - abs_y1,
        "y_min": abs_y1, "x_min": abs_x1, "y_max": abs_y2, "x_max": abs_x2
    }

# --- Backend Implementation ---

class BackendHandler:
    def generate(self, image_bytes: bytes, prompt: str) -> Dict:
        raise NotImplementedError

class GoogleBackend(BackendHandler):
    def __init__(self, key: str, model: str):
        if not genai: raise ImportError("google-genai package not installed")
        self.client = genai.Client(api_key=key)
        # Requirement: "THE MODEl to use is models/gemini-flash-latest"
        self.model = model if model else DEFAULT_GOOGLE_MODEL
        logger.info(f"Initialized Google Backend with model: {self.model}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate(self, image_bytes: bytes, prompt: str) -> Dict:
        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                google_types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt
            ],
            config=google_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA_DICT,
                temperature=0.0
            ),
            http_options=google_types.HttpOptions(timeout=45.0)
        )
        
        # Handle different SDK versions parsing
        if hasattr(response, 'parsed') and response.parsed:
            return response.parsed if isinstance(response.parsed, dict) else response.parsed.model_dump()
        return json.loads(response.text)

class OpenAIBackend(BackendHandler):
    def __init__(self, key: str, base_url: str, model: str):
        if not OpenAI: raise ImportError("openai package not installed")
        self.client = OpenAI(api_key=key, base_url=base_url)
        # Fallback to gpt-4o-mini if no model provided for OpenAI mode
        self.model = model if model else "gpt-4o-mini"
        logger.info(f"Initialized OpenAI/Local Backend with model: {self.model} at {base_url or 'default url'}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate(self, image_bytes: bytes, prompt: str) -> Dict:
        b64_img = base64.b64encode(image_bytes).decode('utf-8')
        
        # Append schema instruction to prompt for generic models
        json_instruction = f"""
        You must return valid JSON. 
        Schema: {json.dumps(RESPONSE_SCHEMA_DICT)}
        Ensure all bounding boxes 'box_2d' are [ymin, xmin, ymax, xmax] normalized to 0-1000.
        """
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt + "\n" + json_instruction},
                    {
                        "type": "image_url", 
                        "image_url": {"url": f"data:image/png;base64,{b64_img}"}
                    }
                ]
            }
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=2048
        )
        return json.loads(response.choices[0].message.content)

# --- Initialization Logic ---

def _get_handler():
    """Lazy initialization of backend handler."""
    global handler
    if 'handler' not in globals() or handler is None:
        if not API_KEY:
            logger.warning("API_KEY is not set. Requests may fail.")
        
        if PROVIDER == "google":
            handler = GoogleBackend(API_KEY, MODEL_NAME)
        else:
            handler = OpenAIBackend(API_KEY, BASE_URL, MODEL_NAME)
    return handler

handler = None

# --- The Tool ---

@mcp.tool()
def analyze_screenshot(image_base64: str) -> str:
    """
    Grounding Tool: Takes a Base64 screenshot, returns JSON with pixel coordinates (box_px) 
    for UI elements (buttons, inputs, etc).
    """
    try:
        # 1. Image Loading
        if not image_base64: return json.dumps({"error": "empty_input"})
        image_bytes = base64.b64decode(image_base64)
        
        if len(image_bytes) > MAX_IMAGE_BYTES:
            return json.dumps({"error": "image_too_large_max_6mb"})
            
        img = Image.open(BytesIO(image_bytes))
        img = _fix_orientation(img)
        width, height = img.size
        
        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            return json.dumps({"error": "dimensions_too_large"})

        # 2. Prompting
        prompt = """
        Analyze this UI screenshot for a blind agent.
        1. Identify the screen context.
        2. Detect all interactive elements.
        3. Return JSON with 'box_2d' [ymin, xmin, ymax, xmax] in 0-1000 coordinates.
        """

        # 3. Backend Call
        try:
            backend = _get_handler()
            data = backend.generate(image_bytes, prompt)
        except Exception as e:
            logger.error(f"Backend failed: {e}")
            return json.dumps({"error": "ai_provider_error", "details": str(e)})

        # 4. Processing & Scaling
        final_components = []
        raw_comps = data.get("components", [])
        
        for i, c in enumerate(raw_comps):
            try:
                # Basic cleanup
                c_id = c.get("id", i+1)
                c_label = c.get("label", "unknown")
                c_type = c.get("type", "other")
                if c_type not in ALLOWED_TYPES: c_type = "other"
                
                # Scale
                box = c.get("box_2d", [0,0,0,0])
                box_px = scale_box(box, width, height)
                
                final_components.append({
                    "id": c_id,
                    "label": c_label,
                    "type": c_type,
                    "tags": c.get("tags", []),
                    "box_norm": box,
                    "box_px": box_px
                })
            except Exception:
                continue # Skip malformed items

        result = {
            "summary": data.get("summary", ""),
            "resolution": {"width": width, "height": height},
            "components": final_components
        }
        
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.exception("Critical error")
        return json.dumps({"error": "internal_error", "details": str(e)})

if __name__ == "__main__":
    # 🚀 WEIRD PORT ACTIVATED
    logger.info(f"Starting Grounding MCP Server on port {WEIRD_PORT}...")
    mcp.run(port=WEIRD_PORT)
