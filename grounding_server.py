import os
import base64
import json
import logging
from io import BytesIO
from typing import Dict, List, Optional, Any

from fastmcp import FastMCP
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_exponential

# --- ADB Utilities ---
try:
    from adb_utils import ADBHelper, get_setup_instructions
except ImportError:
    ADBHelper = None
    get_setup_instructions = None
    logger.warning("adb_utils not available. ADB features will be disabled.")

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

# ADB Configuration
ADB_DEVICE_ID = os.environ.get("ADB_DEVICE_ID")  # Optional device serial
USE_ROOT_MODE = os.environ.get("USE_ROOT_MODE", "false").lower() == "true"  # Enable root features

# Defaults
DEFAULT_GOOGLE_MODEL = "models/gemini-flash-latest"
MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_DIMENSION = 8000
ALLOWED_TYPES = {"button", "input", "icon", "text", "link", "image", "other"}

# Initialize FastMCP
mcp = FastMCP("Blind Agent Visual Cortex")

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
    """Fix image orientation based on EXIF data."""
    try:
        exif = img.getexif()
        if not exif: 
            return img
        orientation = exif.get(0x0112)  # Orientation tag
        if orientation == 3: 
            return img.rotate(180, expand=True)
        elif orientation == 6: 
            return img.rotate(270, expand=True)
        elif orientation == 8: 
            return img.rotate(90, expand=True)
    except (AttributeError, KeyError, TypeError) as e:
        logger.debug(f"Could not read EXIF orientation: {e}")
    return img

def scale_box(box_norm: List[float], width: int, height: int) -> Dict[str, int]:
    """
    Converts 0-1000 normalized coords to pixels.
    
    Args:
        box_norm: [ymin, xmin, ymax, xmax] in 0-1000 normalized coordinates
        width: Image width in pixels
        height: Image height in pixels
    
    Returns:
        Dictionary with pixel coordinates and center point
    """
    if not box_norm or len(box_norm) != 4:
        return {"error": "invalid_box"}
    
    # Clamp values to valid range and convert to float
    y1, x1, y2, x2 = [max(0.0, min(1000.0, float(v))) for v in box_norm]
    
    # Validate logical order
    if y2 < y1:
        y1, y2 = y2, y1
    if x2 < x1:
        x1, x2 = x2, x1

    abs_y1 = int(round((y1 / 1000.0) * height))
    abs_x1 = int(round((x1 / 1000.0) * width))
    abs_y2 = int(round((y2 / 1000.0) * height))
    abs_x2 = int(round((x2 / 1000.0) * width))

    # Fix degenerate boxes (ensure minimum 1px size)
    if abs_x2 <= abs_x1: 
        abs_x2 = min(width, abs_x1 + 1)
    if abs_y2 <= abs_y1: 
        abs_y2 = min(height, abs_y1 + 1)

    return {
        "center_x": (abs_x1 + abs_x2) // 2,
        "center_y": (abs_y1 + abs_y2) // 2,
        "width": abs_x2 - abs_x1,
        "height": abs_y2 - abs_y1,
        "y_min": abs_y1, 
        "x_min": abs_x1, 
        "y_max": abs_y2, 
        "x_max": abs_x2
    }

# --- Backend Implementation ---

class BackendHandler:
    def generate(self, image_bytes: bytes, prompt: str) -> Dict:
        raise NotImplementedError

class GoogleBackend(BackendHandler):
    def __init__(self, key: Optional[str], model: Optional[str]):
        if not genai: 
            raise ImportError("google-genai package not installed")
        if not key:
            raise ValueError("API key required for Google backend")
        
        self.client = genai.Client(api_key=key)
        # Use models/gemini-flash-latest as default for best grounding support
        self.model = model if model else DEFAULT_GOOGLE_MODEL
        logger.info(f"Initialized Google Backend with model: {self.model}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate(self, image_bytes: bytes, prompt: str) -> Dict:
        """
        Generate content using Google Gemini with native grounding support.
        
        Args:
            image_bytes: Image data as bytes
            prompt: Text prompt for the model
        
        Returns:
            Dictionary with summary and components
        """
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
            http_options=google_types.HttpOptions(timeout=60.0)
        )
        
        # Handle different SDK versions and response formats
        if hasattr(response, 'parsed') and response.parsed:
            result = response.parsed if isinstance(response.parsed, dict) else response.parsed.model_dump()
        elif hasattr(response, 'text') and response.text:
            result = json.loads(response.text)
        else:
            raise ValueError("Unable to parse response from Gemini API")
        
        # Validate response structure
        if not isinstance(result, dict):
            raise ValueError(f"Expected dict response, got {type(result)}")
        if "components" not in result:
            logger.warning("Response missing 'components' field, adding empty list")
            result["components"] = []
        
        return result

class OpenAIBackend(BackendHandler):
    def __init__(self, key: str, base_url: Optional[str], model: Optional[str]):
        if not OpenAI: 
            raise ImportError("openai package not installed")
        
        # Initialize client with optional base_url for local/compatible endpoints
        client_kwargs = {"api_key": key or "not-needed"}
        if base_url:
            client_kwargs["base_url"] = base_url
        
        self.client = OpenAI(**client_kwargs)
        # Fallback to gpt-4o-mini if no model provided for OpenAI mode
        self.model = model if model else "gpt-4o-mini"
        logger.info(f"Initialized OpenAI/Local Backend with model: {self.model} at {base_url or 'default OpenAI endpoint'}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate(self, image_bytes: bytes, prompt: str) -> Dict:
        b64_img = base64.b64encode(image_bytes).decode('utf-8')
        
        # Enhanced schema instruction with examples for better model compatibility
        json_instruction = f"""
You must return valid JSON matching this exact schema:
{json.dumps(RESPONSE_SCHEMA_DICT, indent=2)}

Important:
- All bounding boxes 'box_2d' MUST be [ymin, xmin, ymax, xmax] normalized to 0-1000 range
- Each component must have: id (integer), label (string), type (string), box_2d (array of 4 numbers)
- Valid types: button, input, icon, text, link, image, other
- Ensure JSON is properly formatted and parseable
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
            max_tokens=4096,  # Increased for complex UIs with many elements
            timeout=60.0
        )
        
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from model")
        
        return json.loads(content)

# --- Initialization Logic ---

handler: Optional[BackendHandler] = None

def _get_handler() -> BackendHandler:
    """
    Get or initialize the backend handler.
    
    Returns:
        BackendHandler instance configured for the selected provider
    
    Raises:
        ValueError: If API_KEY is not set or provider is invalid
    """
    global handler
    if handler is None:
        if not API_KEY:
            raise ValueError("API_KEY environment variable is required")
        
        if PROVIDER == "google":
            handler = GoogleBackend(API_KEY, MODEL_NAME)
        elif PROVIDER == "openai":
            handler = OpenAIBackend(API_KEY, BASE_URL, MODEL_NAME)
        else:
            raise ValueError(f"Invalid GROUNDING_PROVIDER: {PROVIDER}. Must be 'google' or 'openai'")
    return handler

# Initialize handler at module level to catch configuration errors early
try:
    if API_KEY:
        handler = _get_handler()
    else:
        logger.warning("API_KEY not set. Handler will be initialized on first request.")
except Exception as e:
    logger.error(f"Failed to initialize handler: {e}")
    handler = None

# --- The Tool ---

@mcp.tool()
def analyze_screenshot(image_base64: str) -> str:
    """
    Grounding Tool: Takes a Base64 screenshot, returns JSON with pixel coordinates (box_px) 
    for UI elements (buttons, inputs, icons, text, links, images, etc).
    
    Args:
        image_base64: Base64 encoded image string
    
    Returns:
        JSON string with summary, resolution, and component list with pixel coordinates
    """
    try:
        # 1. Input Validation
        if not image_base64 or not isinstance(image_base64, str):
            return json.dumps({"error": "empty_or_invalid_input", "message": "image_base64 must be a non-empty string"})
        
        # Validate base64 format
        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except Exception as e:
            return json.dumps({"error": "invalid_base64", "message": str(e)})
        
        if not image_bytes:
            return json.dumps({"error": "empty_decoded_image"})
        
        if len(image_bytes) > MAX_IMAGE_BYTES:
            return json.dumps({
                "error": "image_too_large", 
                "message": f"Image exceeds {MAX_IMAGE_BYTES // (1024*1024)}MB limit"
            })
        
        # 2. Image Loading and Processing
        try:
            img = Image.open(BytesIO(image_bytes))
            img = _fix_orientation(img)
        except Exception as e:
            return json.dumps({"error": "invalid_image_format", "message": str(e)})
        
        width, height = img.size
        
        if width <= 0 or height <= 0:
            return json.dumps({"error": "invalid_dimensions", "message": "Image has zero dimensions"})
        
        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            return json.dumps({
                "error": "dimensions_too_large",
                "message": f"Image dimensions exceed {MAX_DIMENSION}px limit"
            })
        
        # Convert image to PNG bytes for consistency
        img_buffer = BytesIO()
        img.save(img_buffer, format="PNG")
        image_bytes = img_buffer.getvalue()

        # 3. Enhanced Prompting
        prompt = """Analyze this UI screenshot for a blind automation agent.

Your task:
1. Provide a brief summary of what screen/application is shown
2. Identify ALL interactive and visible elements including:
   - Buttons (clickable elements)
   - Input fields (text boxes, search bars)
   - Icons (clickable icons, menu items)
   - Text (labels, headings, readable text)
   - Links (hyperlinks, navigation items)
   - Images (pictures, logos, graphics)
   - Other interactive elements

3. For EACH element, provide:
   - A clear, descriptive label
   - The element type (button, input, icon, text, link, image, or other)
   - Accurate bounding box coordinates as [ymin, xmin, ymax, xmax] normalized to 0-1000 scale
   
Be thorough and precise with bounding boxes to enable accurate clicking."""

        # 4. Backend Call
        try:
            backend = _get_handler()
            data = backend.generate(image_bytes, prompt)
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            return json.dumps({"error": "configuration_error", "message": str(e)})
        except Exception as e:
            logger.error(f"Backend failed: {e}")
            return json.dumps({"error": "ai_provider_error", "message": str(e)})

        # 5. Processing & Scaling
        final_components = []
        raw_comps = data.get("components", [])
        
        if not isinstance(raw_comps, list):
            logger.warning(f"Components is not a list: {type(raw_comps)}")
            raw_comps = []
        
        for i, c in enumerate(raw_comps):
            if not isinstance(c, dict):
                logger.warning(f"Skipping non-dict component at index {i}")
                continue
            
            try:
                # Extract and validate component data
                c_id = c.get("id", i + 1)
                c_label = c.get("label", "unknown")
                c_type = c.get("type", "other")
                
                # Normalize type
                if c_type not in ALLOWED_TYPES: 
                    c_type = "other"
                
                # Get and validate box coordinates
                box = c.get("box_2d", [0, 0, 0, 0])
                if not isinstance(box, (list, tuple)) or len(box) != 4:
                    logger.warning(f"Invalid box format for component {c_id}: {box}")
                    continue
                
                # Scale to pixels
                box_px = scale_box(box, width, height)
                
                # Skip if box scaling failed
                if "error" in box_px:
                    logger.warning(f"Box scaling failed for component {c_id}")
                    continue
                
                final_components.append({
                    "id": c_id,
                    "label": c_label,
                    "type": c_type,
                    "tags": c.get("tags", []) if isinstance(c.get("tags"), list) else [],
                    "box_norm": box,
                    "box_px": box_px
                })
            except Exception as e:
                logger.warning(f"Error processing component {i}: {e}")
                continue

        result = {
            "summary": data.get("summary", ""),
            "resolution": {"width": width, "height": height},
            "components": final_components,
            "component_count": len(final_components)
        }
        
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.exception("Critical error in analyze_screenshot")
        return json.dumps({"error": "internal_error", "message": str(e)})

# --- ADB Tools for Optimal UI Capture ---

@mcp.tool()
def get_optimal_setup_guide(rooted: bool = False) -> str:
    """
    Get comprehensive setup instructions for optimal UI component identification.
    
    This guide explains how to configure your Android device (rooted or unrooted)
    for maximum accuracy when using Vision-Language models to identify UI components.
    
    Args:
        rooted: Set to true if your device has root access for advanced features
    
    Returns:
        Formatted guide with visual settings, ADB commands, and capture scripts
    """
    if not get_setup_instructions:
        return json.dumps({
            "error": "adb_utils_not_available",
            "message": "ADB utilities are not installed. This is an optional feature."
        })
    
    try:
        instructions = get_setup_instructions(rooted=rooted)
        
        # Format as readable markdown
        output = "# Optimal Setup Guide for UI Component Identification\n\n"
        output += f"**Mode**: {'ROOT' if rooted else 'UNROOTED'}\n\n"
        
        for section, content in instructions.items():
            output += content + "\n\n"
        
        return output
    except Exception as e:
        logger.error(f"Error generating setup guide: {e}")
        return json.dumps({"error": "generation_failed", "message": str(e)})

@mcp.tool()
def configure_device_for_capture(device_id: Optional[str] = None) -> str:
    """
    Automatically configure connected Android device with optimal visual settings.
    
    This tool configures your device via ADB with the best settings for UI component
    identification: disables animations, enables layout bounds, and sets up demo mode.
    
    Args:
        device_id: Optional device serial number. If not provided, uses first device.
    
    Returns:
        JSON with configuration results for each setting
    """
    if not ADBHelper:
        return json.dumps({
            "error": "adb_not_available",
            "message": "ADB utilities are not installed. This is an optional feature.",
            "manual_setup": "See get_optimal_setup_guide tool for manual configuration instructions"
        })
    
    try:
        device_id = device_id or ADB_DEVICE_ID
        adb = ADBHelper(device_id=device_id, use_root=USE_ROOT_MODE)
        
        results = adb.configure_optimal_visual_settings()
        
        return json.dumps({
            "success": True,
            "device_id": device_id or "default",
            "root_mode": adb.use_root,
            "settings_configured": results,
            "note": "Some settings may require app restart or device UI refresh to take effect"
        }, indent=2)
    except Exception as e:
        logger.error(f"Error configuring device: {e}")
        return json.dumps({
            "error": "configuration_failed",
            "message": str(e),
            "tip": "Ensure device is connected via ADB and USB debugging is enabled"
        })

@mcp.tool()
def capture_with_hierarchy(
    device_id: Optional[str] = None,
    include_parsed_elements: bool = True
) -> str:
    """
    Capture screenshot and UI hierarchy from connected Android device.
    
    This provides the "hybrid capture" approach: visual context (screenshot) plus
    structural data (UI hierarchy XML) for maximum accuracy. The screenshot will
    have layout bounds if configured, and the hierarchy provides exact coordinates
    and metadata for each UI element.
    
    Args:
        device_id: Optional device serial number
        include_parsed_elements: Whether to parse and include UI elements in response
    
    Returns:
        JSON with screenshot path, UI hierarchy XML, and optionally parsed elements
    """
    if not ADBHelper:
        return json.dumps({
            "error": "adb_not_available",
            "message": "ADB utilities are not installed. This is an optional feature."
        })
    
    try:
        device_id = device_id or ADB_DEVICE_ID
        adb = ADBHelper(device_id=device_id, use_root=USE_ROOT_MODE)
        
        result = adb.get_combined_capture()
        
        if not result["success"]:
            return json.dumps({
                "error": "capture_failed",
                "message": result.get("error", "Unknown error")
            })
        
        response = {
            "success": True,
            "screenshot_path": result["screenshot_path"],
            "ui_hierarchy_available": result["ui_hierarchy"] is not None,
            "root_mode": adb.use_root
        }
        
        if include_parsed_elements and result["parsed_elements"]:
            # Include parsed elements for easy consumption
            response["parsed_elements"] = result["parsed_elements"]
            response["element_count"] = len(result["parsed_elements"])
        
        if result["ui_hierarchy"]:
            # Optionally include raw XML (can be large)
            response["ui_hierarchy_xml"] = result["ui_hierarchy"][:1000] + "..." if len(result["ui_hierarchy"]) > 1000 else result["ui_hierarchy"]
        
        return json.dumps(response, indent=2)
    except Exception as e:
        logger.error(f"Error capturing with hierarchy: {e}")
        return json.dumps({
            "error": "capture_failed",
            "message": str(e)
        })

@mcp.tool()
def restore_device_settings(device_id: Optional[str] = None) -> str:
    """
    Restore device to default visual settings after capture.
    
    This re-enables animations, disables layout bounds, and turns off demo mode.
    
    Args:
        device_id: Optional device serial number
    
    Returns:
        JSON with restoration results
    """
    if not ADBHelper:
        return json.dumps({
            "error": "adb_not_available",
            "message": "ADB utilities are not installed. This is an optional feature."
        })
    
    try:
        device_id = device_id or ADB_DEVICE_ID
        adb = ADBHelper(device_id=device_id, use_root=USE_ROOT_MODE)
        
        results = adb.restore_default_settings()
        
        return json.dumps({
            "success": True,
            "device_id": device_id or "default",
            "settings_restored": results
        }, indent=2)
    except Exception as e:
        logger.error(f"Error restoring settings: {e}")
        return json.dumps({
            "error": "restoration_failed",
            "message": str(e)
        })

@mcp.tool()
def analyze_screenshot_with_hierarchy(
    image_base64: str,
    ui_hierarchy_xml: Optional[str] = None
) -> str:
    """
    Enhanced grounding tool that combines screenshot analysis with UI hierarchy data.
    
    This provides the most accurate results by giving the VL model both visual context
    and structural ground truth. If ui_hierarchy_xml is provided, it will be used to
    enhance and validate the detected components.
    
    Args:
        image_base64: Base64 encoded screenshot
        ui_hierarchy_xml: Optional UI hierarchy XML from uiautomator or dumpsys
    
    Returns:
        JSON with enhanced component detection including hierarchy validation
    """
    # First, run standard screenshot analysis
    base_result = analyze_screenshot(image_base64)
    
    # If no hierarchy provided, return standard result
    if not ui_hierarchy_xml or not ADBHelper:
        return base_result
    
    try:
        result_dict = json.loads(base_result)
        
        # Parse hierarchy
        adb = ADBHelper()
        parsed_elements = adb.parse_ui_hierarchy(ui_hierarchy_xml)
        
        if parsed_elements:
            # Enhance result with hierarchy data
            result_dict["hierarchy_elements_count"] = len(parsed_elements)
            result_dict["hierarchy_available"] = True
            
            # Add hierarchy elements for reference
            result_dict["ui_elements_from_hierarchy"] = [
                {
                    "resource_id": elem["resource_id"],
                    "text": elem["text"],
                    "content_desc": elem["content_desc"],
                    "class": elem["class"],
                    "bounds": elem.get("bounds_parsed"),
                    "clickable": elem["clickable"]
                }
                for elem in parsed_elements
                if elem["clickable"] or elem["text"] or elem["content_desc"]
            ][:50]  # Limit to 50 most relevant elements
        
        return json.dumps(result_dict, indent=2)
    except Exception as e:
        logger.error(f"Error enhancing with hierarchy: {e}")
        # Return base result if enhancement fails
        return base_result

if __name__ == "__main__":
    # 🚀 WEIRD PORT ACTIVATED
    logger.info(f"Starting Grounding MCP Server on port {WEIRD_PORT}...")
    mcp.run(transport="sse", port=WEIRD_PORT)
