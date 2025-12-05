import subprocess
import json
import base64
import time
import os
import sys
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.session import ClientSession

# Configuration
MCP_ENV = {
    "GROUNDING_PROVIDER": "openai",
    "BASE_URL": "http://100.85.200.52:1234/v1",
    "API_KEY": "dummy",
    "PYTHONUNBUFFERED": "1",
    **os.environ
}

HTML_FILE = os.path.abspath("login_mockup.html")
SCREENSHOT_FILE = "web_screenshot.png"

def take_screenshot():
    print("Taking screenshot of login page...")
    # Use google-chrome headless to take a screenshot
    cmd = [
        "google-chrome",
        "--headless",
        "--disable-gpu",
        f"--screenshot={SCREENSHOT_FILE}",
        "--window-size=1280,720",
        f"file://{HTML_FILE}"
    ]
    subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
    
    with open(SCREENSHOT_FILE, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

async def run_agent():
    # Start MCP Server
    server_params = StdioServerParameters(
        command="/home/op/miniconda/envs/mcp-4k-eyes/bin/fastmcp",
        args=["run", "grounding_server.py"],
        env=MCP_ENV,
        cwd="/home/op/mcp-4k-eyes"
    )

    print("Starting MCP Client for Web Automation...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("MCP Session Initialized.")

            async def find_element(keywords):
                print(f"Analyzing UI for: {keywords}")
                img_b64 = take_screenshot()
                result = await session.call_tool("analyze_screenshot", arguments={"image_base64": img_b64})
                
                try:
                    data = json.loads(result.content[0].text)
                    components = data.get("components", [])
                    
                    for c in components:
                        label = c.get("label", "").lower()
                        if any(k.lower() in label for k in keywords):
                            print(f"✅ Found '{c['label']}' at {c['box_px']}")
                            return c
                except Exception as e:
                    print(f"Error parsing response: {e}")
                return None

            # Simulation Flow
            print("\n--- Step 1: Enter Username ---")
            username_field = await find_element(["username", "user"])
            if username_field:
                x, y = username_field['box_px']['center_x'], username_field['box_px']['center_y']
                print(f"ACTION: Click at ({x}, {y})")
                print(f"ACTION: Type 'demo_user'")
            else:
                print("❌ Username field not found.")

            print("\n--- Step 2: Enter Password ---")
            password_field = await find_element(["password", "pass"])
            if password_field:
                x, y = password_field['box_px']['center_x'], password_field['box_px']['center_y']
                print(f"ACTION: Click at ({x}, {y})")
                print(f"ACTION: Type 'secret123'")
            else:
                print("❌ Password field not found.")

            print("\n--- Step 3: Click Login ---")
            login_btn = await find_element(["sign in", "login", "submit"])
            if login_btn:
                x, y = login_btn['box_px']['center_x'], login_btn['box_px']['center_y']
                print(f"ACTION: Click at ({x}, {y})")
            else:
                print("❌ Login button not found.")

if __name__ == "__main__":
    import asyncio
    # Clean up previous screenshot
    if os.path.exists(SCREENSHOT_FILE):
        os.remove(SCREENSHOT_FILE)
        
    asyncio.run(run_agent())
