# 👁️ Visual Cortex MCP Server

A specialized MCP server that provides "vision" to blind AI agents. It detects UI elements and returns **pixel-perfect coordinates** for automation.

It runs on the **Weird Port 43210** by default.

## 🚀 Supported Backends

### 1. Google Gemini (Default & Best)
*   **Model:** `models/gemini-flash-latest`
*   **Performance:** Fastest, native 2D grounding support.
*   **Cost:** Extremely low.

### 2. OpenAI / Local Compatible
*   **Model:** Configurable (User defined).
*   **Support:** Works with `gpt-4o`, **Qwen3 8 VL**, `vLLM` hosting vision models, or `LM Studio`.
*   **Features:** Enhanced prompt engineering for better compatibility with various vision models.

## 🛠️ Installation

1.  **Clone & Install:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configure Environment:**
    Copy `.env.example` to `.env` and set your provider.

    *For Google:*
    ```bash
    export GROUNDING_PROVIDER=google
    export API_KEY=your_gemini_key
    ```

    *For Local LLM:*
    ```bash
    export GROUNDING_PROVIDER=openai
    export BASE_URL=http://localhost:1234/v1
    export MODEL_NAME=llama-3.2-vision
    export API_KEY=local
    ```

3.  **Run:**
    ```bash
    python grounding_server.py
    ```
    *Server listening on port 43210*

## 🤖 Usage

**Input:** Base64 Encoded Image.
**Output:** JSON with `box_px` (Absolute pixel coordinates).

### Agent Instruction
> "Use `analyze_screenshot` to see. The tool returns a list of components. Use the `center_x` and `center_y` inside `box_px` to click elements."

## ✨ Recent Improvements

### Enhanced Compatibility & Robustness
- ✅ **Full OpenAI API compatibility** - Works seamlessly with Qwen3 8 VL and other vision models
- ✅ **Improved error handling** - Comprehensive validation and specific error messages
- ✅ **Better response parsing** - Handles various model output formats gracefully
- ✅ **Enhanced prompts** - Optimized for both Gemini and OpenAI-compatible models
- ✅ **Increased token limit** - Now supports up to 4096 tokens for complex UIs (was 2048)
- ✅ **Robust image handling** - Better EXIF orientation support and format detection
- ✅ **Input validation** - Validates base64 format, image dimensions, and file sizes
- ✅ **Box coordinate validation** - Auto-corrects inverted coordinates and validates ranges
- ✅ **Type hints** - Full type annotations for better IDE support and code quality

### 🎯 NEW: Optimal UI Capture for Maximum Accuracy

- ✅ **Root & Unrooted Support** - Works with both rooted and standard Android devices
- ✅ **Automated Device Configuration** - ADB tools to configure optimal visual settings
- ✅ **Hybrid Capture Mode** - Combines screenshot + UI hierarchy for ground truth accuracy
- ✅ **Layout Bounds Support** - Visual tokenization of UI components
- ✅ **Setup Guides** - Comprehensive instructions for both modes

## 🐳 Docker

```bash
docker build -t visual-cortex .
docker run -p 43210:43210 --env-file .env visual-cortex
```

## 📱 Android Device Setup (Optional but Recommended)

For **maximum accuracy** in UI component identification, configure your Android device with optimal visual settings. This works for both **rooted** and **unrooted** devices.

### Quick Setup via ADB

The server provides tools to automatically configure your device:

```python
# Get setup instructions for your device type
get_optimal_setup_guide(rooted=False)  # or True for rooted devices

# Automatically configure connected device
configure_device_for_capture()

# Capture screenshot + UI hierarchy for enhanced accuracy
capture_with_hierarchy()

# Restore device to normal settings when done
restore_device_settings()
```

### What Gets Configured?

1. **Layout Bounds** - Visual rectangles around every UI element (the MVP setting!)
2. **Animation Disable** - Zero-latency captures (no mid-transition blurriness)
3. **Demo Mode** - Clean status bar (fixed time, battery, no notifications)
4. **Hierarchy Dump** - Ground truth coordinates and metadata

### Manual Setup

If you prefer manual configuration or ADB is unavailable, use the `get_optimal_setup_guide` tool to get detailed step-by-step instructions.

## 🎯 Enhanced Analysis with UI Hierarchy

Use the hybrid approach for best results:

```python
# Standard analysis (screenshot only)
analyze_screenshot(image_base64)

# Enhanced analysis (screenshot + UI hierarchy)
analyze_screenshot_with_hierarchy(image_base64, ui_hierarchy_xml)
```

The hybrid approach gives the VL model:
- **Visual Context**: Screenshot with layout bounds
- **Ground Truth**: Exact coordinates, resource IDs, and text from XML
- **Result**: Highest possible accuracy and reduced hallucination

## 🔧 Available MCP Tools

| Tool | Description |
|------|-------------|
| `analyze_screenshot` | Standard UI component detection from screenshot |
| `analyze_screenshot_with_hierarchy` | Enhanced detection using screenshot + UI hierarchy |
| `get_optimal_setup_guide` | Get setup instructions for rooted/unrooted devices |
| `configure_device_for_capture` | Auto-configure device via ADB |
| `capture_with_hierarchy` | Capture screenshot + UI hierarchy from device |
| `restore_device_settings` | Restore device to default settings |

## 🧪 Testing

Run the test suite to verify functionality:

```bash
pytest test_grounding.py -v
```

Tests cover:
- Box coordinate scaling and validation
- Backend initialization (Google & OpenAI)
- Image format handling
- Error handling and edge cases

## 📚 Why This Hybrid Approach?

The "best mode" for VL models isn't a single switch, but a configuration that creates a **"clean but semantically dense" visual feed**:

1. **Layout Bounds**: Explicit red/blue rectangles "tokenize" the screen
2. **No Animations**: Ensures crisp, deterministic captures
3. **Demo Mode**: Removes visual noise from status bar
4. **UI Hierarchy**: Provides ground truth that eliminates guesswork

This combination gives the model "X-ray vision" - both pixel-level visuals AND structural semantics.
