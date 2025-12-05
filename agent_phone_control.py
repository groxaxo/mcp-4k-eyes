import subprocess
import json
import base64
import time
import os
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.session import ClientSession

# Configuration
MCP_PYTHON = "/home/op/miniconda/envs/mcp-4k-eyes/bin/python"
MCP_SCRIPT = "/home/op/mcp-4k-eyes/grounding_server.py"
MCP_ENV = {
    "GROUNDING_PROVIDER": "openai",
    "BASE_URL": "http://100.85.200.52:1234/v1",
    "API_KEY": "dummy",
    "PYTHONUNBUFFERED": "1",
    **os.environ
}

def adb_shell(cmd):
    full_cmd = f"adb shell {cmd}"
    print(f"ADB: {cmd}")
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ADB Error: {result.stderr}")
    return result.stdout.strip()

def get_screenshot_base64():
    # Capture screenshot to device
    adb_shell("screencap -p /sdcard/screen.png")
    # Pull to local
    subprocess.run("adb pull /sdcard/screen.png ./screen.png", shell=True, check=True, capture_output=True)
    # Read as base64
    with open("screen.png", "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

async def run_agent():
    # Start MCP Server
    server_params = StdioServerParameters(
        command="/home/op/miniconda/envs/mcp-4k-eyes/bin/fastmcp",
        args=["run", "grounding_server.py"],
        env=MCP_ENV,
        cwd="/home/op/mcp-4k-eyes"
    )

    print("Starting MCP Client...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("MCP Session Initialized.")

            async def find_element(keywords, retries=3):
                for i in range(retries):
                    print(f"Scanning for {keywords} (Attempt {i+1}/{retries})...")
                    img_b64 = get_screenshot_base64()
                    result = await session.call_tool("analyze_screenshot", arguments={"image_base64": img_b64})
                    
                    try:
                        data = json.loads(result.content[0].text)
                        components = data.get("components", [])
                        
                        for c in components:
                            label = c.get("label", "").lower()
                            if any(k.lower() in label for k in keywords):
                                print(f"Found '{c['label']}' at {c['box_px']}")
                                return c
                    except Exception as e:
                        print(f"Error parsing response: {e}")
                    
                    if i < retries - 1:
                        time.sleep(2)
                return None

            # 1. Go to Home and Clear State
            print("Going Home...")
            adb_shell("input keyevent KEYCODE_HOME")
            time.sleep(1)
            adb_shell("am force-stop com.google.android.gm") # Force stop to ensure fresh start
            time.sleep(1)
            
            # 2. Open Gmail
            print("Launching Gmail...")
            adb_shell("am start -n com.google.android.gm/.ConversationListActivityGmail")
            time.sleep(5) # Wait for app to load

            # 3. Find and Click Compose
            print("Looking for Compose button...")
            compose_btn = await find_element(["compose", "write", "edit", "create"])
            
            if compose_btn:
                x, y = compose_btn['box_px']['center_x'], compose_btn['box_px']['center_y']
                print(f"Tapping Compose at {x}, {y}")
                adb_shell(f"input tap {x} {y}")
            else:
                print("Compose button not found! Trying fallback FAB location...")
                adb_shell("input tap 950 2000")
            
            time.sleep(3)

            # 4. Verify we are on Compose screen and Find 'To'
            print("Looking for 'To' field...")
            to_field = await find_element(["to", "recipient"])
            
            if to_field:
                x, y = to_field['box_px']['center_x'], to_field['box_px']['center_y']
                print(f"Tapping 'To' field at {x}, {y}")
                adb_shell(f"input tap {x} {y}")
            else:
                print("'To' field not found. Assuming focus is already there or trying top area...")
                adb_shell("input tap 200 300")
            
            time.sleep(1)
            print("Typing recipient...")
            adb_shell("input text luchorofo@gmail.com")
            adb_shell("input keyevent KEYCODE_ENTER")
            time.sleep(1)

            # 5. Find Subject
            print("Looking for 'Subject' field...")
            subject_field = await find_element(["subject"])
            
            if subject_field:
                x, y = subject_field['box_px']['center_x'], subject_field['box_px']['center_y']
                print(f"Tapping 'Subject' field at {x}, {y}")
                adb_shell(f"input tap {x} {y}")
            else:
                print("'Subject' field not found. Using Tab navigation...")
                adb_shell("input keyevent KEYCODE_TAB")
            
            time.sleep(1)
            print("Typing subject...")
            adb_shell("input text 'Test_Email'") # Underscore to avoid space issues
            
            # 6. Find Body
            print("Looking for Body/Compose field...")
            body_field = await find_element(["compose email", "body", "message"])
            
            if body_field:
                x, y = body_field['box_px']['center_x'], body_field['box_px']['center_y']
                print(f"Tapping Body field at {x}, {y}")
                adb_shell(f"input tap {x} {y}")
            else:
                print("Body field not found. Using Tab navigation...")
                adb_shell("input keyevent KEYCODE_TAB")

            time.sleep(1)
            print("Typing message...")
            adb_shell("input text 'hey%sbro'") 
            time.sleep(1)
            
            # 7. Send
            print("Looking for Send button...")
            send_btn = await find_element(["send"])
            
            if send_btn:
                x, y = send_btn['box_px']['center_x'], send_btn['box_px']['center_y']
                print(f"Tapping Send at {x}, {y}")
                adb_shell(f"input tap {x} {y}")
            else:
                print("Send button not found! Trying top right...")
                adb_shell("input tap 950 150")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_agent())
