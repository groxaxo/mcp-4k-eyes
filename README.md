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
*   **Support:** Works with `gpt-4o`, `vLLM` hosting Llama 3.2 Vision, or `LM Studio`.

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

## 🐳 Docker

```bash
docker build -t visual-cortex .
docker run -p 43210:43210 --env-file .env visual-cortex
```
