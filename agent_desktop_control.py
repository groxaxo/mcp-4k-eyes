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

SCREENSHOT_FILE = "desktop_screenshot.png"

def take_screenshot():
    print("Taking screenshot of desktop...")
    # Use ImageMagick 'import' to capture the root window
    cmd = ["import", "-window", "root", SCREENSHOT_FILE]
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

    print("Starting MCP Client for Desktop Automation...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("MCP Session Initialized.")

            async def find_element(keywords):
                print(f"Analyzing Desktop for: {keywords}")
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

            # Simulation Flow - Look for common Ubuntu desktop elements
            print("\n--- Step 1: Find 'Activities' or 'Applications' ---")
            activities_btn = await find_element(["activities", "applications", "menu", "start"])
            if activities_btn:
                x, y = activities_btn['box_px']['center_x'], activities_btn['box_px']['center_y']
                print(f"ACTION: Click at ({x}, {y})")
            else:
                print("❌ Activities/Menu button not found.")

            print("\n--- Step 2: Find 'Terminal' Icon ---")
            terminal_icon = await find_element(["terminal", "console", "shell", "command prompt"])
            if terminal_icon:
                x, y = terminal_icon['box_px']['center_x'], terminal_icon['box_px']['center_y']
                print(f"ACTION: Click at ({x}, {y})")
            else:
                print("❌ Terminal icon not found.")

            print("\n--- Step 3: Find 'File Manager' or 'Home' ---")
            files_icon = await find_element(["files", "file manager", "home", "folder"])
            if files_icon:
                x, y = files_icon['box_px']['center_x'], files_icon['box_px']['center_y']
                print(f"ACTION: Click at ({x}, {y})")
            else:
                print("❌ File Manager icon not found.")

if __name__ == "__main__":
    import asyncio
    # Clean up previous screenshot
    if os.path.exists(SCREENSHOT_FILE):
        os.remove(SCREENSHOT_FILE)
        
    asyncio.run(run_agent())
