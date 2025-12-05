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

## 🐳 Docker

```bash
docker build -t visual-cortex .
docker run -p 43210:43210 --env-file .env visual-cortex
```

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
