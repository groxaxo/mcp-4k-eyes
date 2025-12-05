# Usage Examples

This document provides practical examples of using the MCP server with the new root/unrooted mode features.

## Quick Start

### 1. Basic Screenshot Analysis (No Device Required)

```python
# Standard use case - analyze any screenshot
analyze_screenshot(image_base64)
```

This works with any screenshot from any source. You don't need a connected Android device.

### 2. Get Setup Instructions

```python
# For unrooted devices
get_optimal_setup_guide(rooted=False)

# For rooted devices  
get_optimal_setup_guide(rooted=True)
```

This returns comprehensive markdown documentation with:
- Visual settings to configure
- ADB commands to run
- Settings to avoid
- Complete capture scripts

### 3. Auto-Configure Connected Device

```python
# Configure device with optimal settings
configure_device_for_capture()

# Returns:
# {
#   "success": true,
#   "device_id": "default",
#   "root_mode": false,
#   "settings_configured": {
#     "layout_bounds": true,
#     "animations_disabled": true,
#     "demo_mode": true
#   }
# }
```

### 4. Hybrid Capture (Maximum Accuracy)

```python
# Capture screenshot + UI hierarchy from device
result = capture_with_hierarchy(include_parsed_elements=True)

# Returns:
# {
#   "success": true,
#   "screenshot_path": "/tmp/screenshot_abc123.png",
#   "ui_hierarchy_available": true,
#   "parsed_elements": [...],
#   "element_count": 42
# }

# Then analyze with both visual and structural data
with open(result["screenshot_path"], "rb") as f:
    screenshot_base64 = base64.b64encode(f.read()).decode()

analyze_screenshot_with_hierarchy(
    screenshot_base64,
    result["ui_hierarchy_xml"]
)
```

### 5. Restore Device Settings

```python
# Restore device to defaults when done
restore_device_settings()
```

## Complete Workflow Examples

### Example 1: Manual Setup with Auto-Configure

```python
# 1. Get instructions
guide = get_optimal_setup_guide(rooted=False)
print(guide)  # Read and understand the setup

# 2. Auto-configure device
result = configure_device_for_capture()
if not result["success"]:
    print("Manual configuration required")

# 3. Manually enable "Show Layout Bounds" in device settings
# (This step can't be automated on unrooted devices)

# 4. Capture and analyze
capture_result = capture_with_hierarchy()
with open(capture_result["screenshot_path"], "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

analysis = analyze_screenshot_with_hierarchy(
    img_b64,
    capture_result["ui_hierarchy_xml"]
)

# 5. Clean up
restore_device_settings()
```

### Example 2: Rooted Device Full Auto

```bash
# Set environment variable for root mode
export USE_ROOT_MODE=true
```

```python
# With root mode enabled, everything can be automated
configure_device_for_capture()  # Configures ALL settings

# Capture with fast root method
result = capture_with_hierarchy()  # Uses dumpsys for faster capture

# Analyze
with open(result["screenshot_path"], "rb") as f:
    analysis = analyze_screenshot_with_hierarchy(
        base64.b64encode(f.read()).decode(),
        result["ui_hierarchy_xml"]
    )

# Restore
restore_device_settings()
```

### Example 3: Offline Analysis (No Device)

If you already have screenshots and XML dumps:

```python
# Load your files
with open("screenshot.png", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

with open("uidump.xml", "r") as f:
    ui_xml = f.read()

# Analyze with both
result = analyze_screenshot_with_hierarchy(img_b64, ui_xml)
print(json.loads(result))
```

### Example 4: Batch Processing

```python
import time

# Configure device once
configure_device_for_capture()

# Capture multiple screens
screens = []
for i in range(5):
    # Navigate to next screen in your app...
    time.sleep(2)  # Wait for screen to settle
    
    capture = capture_with_hierarchy()
    screens.append(capture)

# Analyze all screens
results = []
for screen in screens:
    with open(screen["screenshot_path"], "rb") as f:
        result = analyze_screenshot_with_hierarchy(
            base64.b64encode(f.read()).decode(),
            screen["ui_hierarchy_xml"]
        )
        results.append(json.loads(result))

# Restore device
restore_device_settings()
```

## Environment Variables

Configure in `.env`:

```bash
# Basic configuration
GROUNDING_PROVIDER=google
API_KEY=your_key

# ADB configuration (optional)
ADB_DEVICE_ID=emulator-5554  # Optional: specific device
USE_ROOT_MODE=true           # Enable root features
```

## Command Line Examples

### Using ADB Directly

If you prefer manual control:

```bash
# Configure device
adb shell settings put global animator_duration_scale 0
adb shell settings put global window_animation_scale 0
adb shell settings put global transition_animation_scale 0
adb shell setprop debug.layout true

# Capture
adb shell screencap -p /sdcard/screen.png
adb pull /sdcard/screen.png

# Dump hierarchy
adb shell uiautomator dump /data/local/tmp/ui.xml
adb pull /data/local/tmp/ui.xml

# Restore
adb shell settings put global animator_duration_scale 1
adb shell settings put global window_animation_scale 1
adb shell settings put global transition_animation_scale 1
```

### Root Commands

```bash
# Fast hierarchy dump with root
adb shell su -c "dumpsys activity top" > hierarchy.txt
```

## Troubleshooting

### Device Not Found

```python
# Check connected devices
import subprocess
result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
print(result.stdout)

# Use specific device
configure_device_for_capture(device_id="emulator-5554")
```

### Permission Denied

```bash
# Restart ADB server
adb kill-server
adb start-server

# Check USB debugging is enabled on device
adb devices
```

### Layout Bounds Not Showing

On unrooted devices, `setprop debug.layout true` may not work. You must:
1. Manually enable in Settings > Developer Options > Show layout bounds
2. Or restart the app: `adb shell am force-stop <package>` then relaunch

### Hierarchy Dump Fails

Some apps block uiautomator with secure flags. Solutions:
- Use root mode: `USE_ROOT_MODE=true`
- Or accept that hierarchy won't be available for those screens
- The screenshot analysis will still work

## Performance Tips

1. **Disable animations** - Saves ~1-2 seconds per capture
2. **Use root mode** - Hierarchy dump is 4x faster (~0.5s vs 2-3s)
3. **Batch captures** - Configure once, capture multiple times
4. **Cache parsed hierarchy** - Parse XML once if analyzing multiple times

## Best Practices

1. ✅ Always configure device before batch operations
2. ✅ Always restore settings when done (for real devices)
3. ✅ Use hybrid capture for maximum accuracy
4. ✅ Check settings_configured response to verify success
5. ❌ Don't enable "pointer location" or "GPU updates"
6. ❌ Don't forget to restore animations on real devices

## Integration with Automation Frameworks

### With Appium

```python
# Use alongside Appium for enhanced accuracy
from appium import webdriver

driver = webdriver.Remote('http://localhost:4723/wd/hub', caps)

# Navigate with Appium
driver.find_element_by_id("login_button").click()

# Verify with visual cortex
capture = capture_with_hierarchy()
# ... analyze to verify UI state
```

### With Playwright

```python
# For web apps on Android WebView
# Capture device screen while Playwright controls the WebView
```

## Support

For issues or questions:
- Check ANDROID_SETUP_GUIDE.md for detailed configuration help
- Review README.md for general server documentation
- Test with `get_optimal_setup_guide()` to verify your setup
