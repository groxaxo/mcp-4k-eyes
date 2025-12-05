"""
ADB Utilities for Optimal UI Component Identification

This module provides utilities to configure Android devices (rooted and unrooted)
for optimal Vision-Language model performance when identifying UI components.
"""

import os
import subprocess
import logging
import json
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger("adb_utils")


class ADBHelper:
    """Helper class for ADB operations supporting both rooted and unrooted devices."""
    
    def __init__(self, device_id: Optional[str] = None, use_root: bool = False):
        """
        Initialize ADB helper.
        
        Args:
            device_id: Optional device ID/serial. If None, uses first available device.
            use_root: Whether to use root commands (requires rooted device).
        """
        self.device_id = device_id
        self.use_root = use_root
        self.is_root_available = False
        
        if self.use_root:
            self.is_root_available = self._check_root_access()
            if not self.is_root_available:
                logger.warning("Root requested but not available. Falling back to non-root mode.")
                self.use_root = False
    
    def _build_adb_command(self, command: str, use_shell: bool = True) -> List[str]:
        """Build ADB command with device selection."""
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        if use_shell:
            cmd.append("shell")
        cmd.extend(command.split())
        return cmd
    
    def _run_command(self, command: str, use_shell: bool = True, timeout: int = 30) -> Tuple[bool, str]:
        """
        Execute ADB command.
        
        Args:
            command: Command to execute
            use_shell: Whether to use adb shell
            timeout: Command timeout in seconds
            
        Returns:
            Tuple of (success, output/error)
        """
        try:
            cmd = self._build_adb_command(command, use_shell)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                return False, result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, f"Command timed out after {timeout}s"
        except Exception as e:
            return False, str(e)
    
    def _check_root_access(self) -> bool:
        """Check if device has root access."""
        success, output = self._run_command("su -c 'id'")
        return success and "uid=0" in output
    
    def configure_optimal_visual_settings(self) -> Dict[str, bool]:
        """
        Configure optimal visual settings for UI component identification.
        
        Returns:
            Dictionary with status of each setting configuration
        """
        results = {}
        
        # 1. Enable Show Layout Bounds (MVP Setting)
        logger.info("Enabling layout bounds...")
        success, _ = self._run_command("setprop debug.layout true")
        results["layout_bounds"] = success
        
        # Alternative method for layout bounds
        success2, _ = self._run_command("settings put global debug_layout true")
        results["layout_bounds"] = results["layout_bounds"] or success2
        
        # 2. Disable all animations (zero latency)
        logger.info("Disabling animations...")
        anim_settings = [
            "settings put global window_animation_scale 0",
            "settings put global transition_animation_scale 0",
            "settings put global animator_duration_scale 0"
        ]
        anim_success = True
        for setting in anim_settings:
            success, _ = self._run_command(setting)
            anim_success = anim_success and success
        results["animations_disabled"] = anim_success
        
        # 3. Enable System UI Demo Mode (sanitizes status bar)
        logger.info("Enabling System UI demo mode...")
        demo_commands = [
            "settings put global sysui_demo_allowed 1",
            "am broadcast -a com.android.systemui.demo -e command clock -e hhmm 1200",
            "am broadcast -a com.android.systemui.demo -e command battery -e level 100 -e plugged false",
            "am broadcast -a com.android.systemui.demo -e command network -e wifi show -e level 4",
            "am broadcast -a com.android.systemui.demo -e command notifications -e visible false"
        ]
        demo_success = True
        for cmd in demo_commands:
            success, _ = self._run_command(cmd)
            demo_success = demo_success and success
        results["demo_mode"] = demo_success
        
        return results
    
    def restore_default_settings(self) -> Dict[str, bool]:
        """
        Restore default visual settings.
        
        Returns:
            Dictionary with status of each setting restoration
        """
        results = {}
        
        # Disable layout bounds
        success, _ = self._run_command("setprop debug.layout false")
        results["layout_bounds_restored"] = success
        
        # Restore animations
        anim_settings = [
            "settings put global window_animation_scale 1",
            "settings put global transition_animation_scale 1",
            "settings put global animator_duration_scale 1"
        ]
        anim_success = True
        for setting in anim_settings:
            success, _ = self._run_command(setting)
            anim_success = anim_success and success
        results["animations_restored"] = anim_success
        
        # Disable demo mode
        success, _ = self._run_command("settings put global sysui_demo_allowed 0")
        results["demo_mode_disabled"] = success
        
        return results
    
    def capture_screenshot(self, output_path: str = "/sdcard/screenshot.png") -> Tuple[bool, str]:
        """
        Capture screenshot from device.
        
        Args:
            output_path: Path on device to save screenshot
            
        Returns:
            Tuple of (success, local_path or error)
        """
        import tempfile
        import uuid
        
        # Capture screenshot on device
        success, output = self._run_command(f"screencap -p {output_path}")
        if not success:
            return False, f"Failed to capture screenshot: {output}"
        
        # Pull to local machine with unique filename
        unique_id = uuid.uuid4().hex[:8]
        local_path = os.path.join(tempfile.gettempdir(), f"screenshot_{unique_id}.png")
        success, output = self._run_command(f"pull {output_path} {local_path}", use_shell=False)
        if not success:
            return False, f"Failed to pull screenshot: {output}"
        
        return True, local_path
    
    def dump_ui_hierarchy(self, use_root_method: bool = None) -> Tuple[bool, Optional[str]]:
        """
        Dump UI hierarchy from device.
        
        Args:
            use_root_method: Override to force root or non-root method
            
        Returns:
            Tuple of (success, XML content or None)
        """
        use_root = use_root_method if use_root_method is not None else self.use_root
        
        if use_root and self.is_root_available:
            # Root method: Use dumpsys (faster, bypasses secure flags)
            logger.info("Dumping UI hierarchy using root method...")
            success, output = self._run_command('su -c "dumpsys activity top"')
            if success:
                return True, output
            else:
                logger.warning("Root method failed, falling back to uiautomator")
        
        # Standard method: Use uiautomator
        logger.info("Dumping UI hierarchy using uiautomator...")
        dump_path = "/data/local/tmp/uidump.xml"
        
        # Dump UI hierarchy
        success, output = self._run_command(f"uiautomator dump {dump_path}")
        if not success:
            return False, None
        
        # Read the XML content
        success, xml_content = self._run_command(f"cat {dump_path}")
        if not success:
            return False, None
        
        return True, xml_content
    
    def parse_ui_hierarchy(self, xml_content: str) -> Optional[List[Dict]]:
        """
        Parse UI hierarchy XML into structured format.
        
        Args:
            xml_content: XML content from UI dump
            
        Returns:
            List of UI elements with properties, or None if parsing fails
        """
        try:
            # Handle dumpsys output (contains XML within larger output)
            if "<?xml" in xml_content:
                xml_start = xml_content.find("<?xml")
                xml_content = xml_content[xml_start:]
            
            root = ET.fromstring(xml_content)
            elements = []
            
            def parse_node(node, depth=0):
                """Recursively parse XML nodes."""
                elem = {
                    "class": node.get("class", ""),
                    "resource_id": node.get("resource-id", ""),
                    "text": node.get("text", ""),
                    "content_desc": node.get("content-desc", ""),
                    "bounds": node.get("bounds", ""),
                    "clickable": node.get("clickable", "false") == "true",
                    "enabled": node.get("enabled", "false") == "true",
                    "focusable": node.get("focusable", "false") == "true",
                    "depth": depth
                }
                
                # Parse bounds [x1,y1][x2,y2] format
                if elem["bounds"]:
                    try:
                        bounds_str = elem["bounds"].replace("][", ",").replace("[", "").replace("]", "")
                        coords = [int(x) for x in bounds_str.split(",")]
                        elem["bounds_parsed"] = {
                            "x_min": coords[0],
                            "y_min": coords[1],
                            "x_max": coords[2],
                            "y_max": coords[3]
                        }
                    except Exception as e:
                        logger.debug(f"Failed to parse bounds: {e}")
                
                elements.append(elem)
                
                # Recursively parse children
                for child in node:
                    parse_node(child, depth + 1)
            
            # Start parsing from root
            for child in root:
                parse_node(child)
            
            return elements
        except Exception as e:
            logger.error(f"Failed to parse UI hierarchy: {e}")
            return None
    
    def get_combined_capture(self) -> Dict:
        """
        Get combined screenshot and UI hierarchy for maximum accuracy.
        
        Returns:
            Dictionary with screenshot path, UI hierarchy, and metadata
        """
        result = {
            "success": False,
            "screenshot_path": None,
            "ui_hierarchy": None,
            "parsed_elements": None,
            "error": None
        }
        
        # Capture screenshot
        success, screenshot_path = self.capture_screenshot()
        if not success:
            result["error"] = screenshot_path
            return result
        
        result["screenshot_path"] = screenshot_path
        
        # Dump UI hierarchy
        success, xml_content = self.dump_ui_hierarchy()
        if not success:
            result["error"] = "Failed to dump UI hierarchy"
            return result
        
        result["ui_hierarchy"] = xml_content
        
        # Parse hierarchy
        parsed = self.parse_ui_hierarchy(xml_content)
        if parsed:
            result["parsed_elements"] = parsed
        
        result["success"] = True
        return result


def get_setup_instructions(rooted: bool = False) -> Dict[str, str]:
    """
    Get setup instructions for optimal UI component identification.
    
    Args:
        rooted: Whether device is rooted
        
    Returns:
        Dictionary with instruction sections
    """
    instructions = {
        "visual_settings": """
## Visual Setup (Device Settings)

Configure these settings to make UI high-contrast, deterministic, and noise-free:

1. **Enable "Show Layout Bounds" (MVP Setting)**
   - Location: Settings > Developer Options > Drawing > Show layout bounds
   - Why: Draws red/blue rectangles around every view, effectively "tokenizing" the screen
   - Benefit: Drastically reduces hallucination of object boundaries

2. **Disable Animations (Zero Latency)**
   - Location: Settings > Developer Options > Drawing
   - Set ALL to "Animation off":
     * Window animation scale
     * Transition animation scale
     * Animator duration scale
   - Benefit: Ensures screenshots are never captured mid-transition

3. **Enable "System UI Demo Mode"**
   - Location: Settings > Developer Options > System UI demo mode
   - Why: Sanitizes status bar (fixes time, battery, signal, removes notifications)
   - Benefit: Removes visual noise and dynamic variables

4. **Enable "High Contrast Text"** (Optional)
   - Location: Settings > Accessibility > Text and display > High contrast text
   - Why: Adds stroke outline to text
   - Benefit: Helps OCR separate text from complex backgrounds
""",
        "avoid_settings": """
## Settings to AVOID

- ❌ "Show pointer location" - adds coordinate overlay noise
- ❌ "Show surface updates" / "Show GPU view updates" - flashes screen pink/green
- ❌ "Force Dark Mode" - can invert colors incorrectly on non-standard apps
""",
        "adb_visual_setup": """
## ADB Commands for Visual Setup

You can configure these settings programmatically via ADB:

```bash
# Disable all animations
adb shell settings put global window_animation_scale 0
adb shell settings put global transition_animation_scale 0
adb shell settings put global animator_duration_scale 0

# Enable layout bounds
adb shell setprop debug.layout true

# Enable System UI Demo Mode
adb shell settings put global sysui_demo_allowed 1
adb shell am broadcast -a com.android.systemui.demo -e command clock -e hhmm 1200
adb shell am broadcast -a com.android.systemui.demo -e command battery -e level 100
adb shell am broadcast -a com.android.systemui.demo -e command network -e wifi show -e level 4
adb shell am broadcast -a com.android.systemui.demo -e command notifications -e visible false
```
"""
    }
    
    if rooted:
        instructions["structural_setup"] = """
## Structural Setup (Root/ADB)

Since you have root access, provide the Ground Truth layout alongside the image:

### Standard Method (uiautomator)
```bash
# Dump UI hierarchy
adb shell uiautomator dump /data/local/tmp/uidump.xml
adb pull /data/local/tmp/uidump.xml
```

### Root Alternative (Faster, bypasses secure flags)
```bash
# Get detailed view hierarchy via dumpsys
adb shell su -c "dumpsys activity top"
```

**Pro Tip:** Feed this XML (or parsed JSON) into the VL model's context window for exact
`resource-id`, `text`, `content-desc`, and `bounds` coordinates.
"""
        
        instructions["ultimate_script"] = """
## Ultimate VL Capture Script (Root Mode)

```bash
#!/bin/bash
# Pre-flight: Configure settings
adb shell settings put global animator_duration_scale 0
adb shell setprop debug.layout true

# Optional: Restart app to apply layout bounds
# adb shell am force-stop <package_name>
# adb shell am start <package_name>/<activity_name>

# Capture
adb shell screencap -p /sdcard/screenshot.png
adb pull /sdcard/screenshot.png

# Dump hierarchy (choose one method)
# Method 1: Standard
adb shell uiautomator dump /data/local/tmp/uidump.xml
adb pull /data/local/tmp/uidump.xml

# Method 2: Root (faster)
adb shell su -c "dumpsys activity top" > view_hierarchy.txt

# Inference: Pass screenshot + hierarchy to VL model
```
"""
    else:
        instructions["structural_setup"] = """
## Structural Setup (Non-Root)

Without root, you can still capture UI hierarchy with some limitations:

### Standard Method (uiautomator)
```bash
# Dump UI hierarchy
adb shell uiautomator dump /data/local/tmp/uidump.xml
adb pull /data/local/tmp/uidump.xml
```

**Note:** Some apps with secure flags may block uiautomator. Root access bypasses these restrictions.
"""
        
        instructions["ultimate_script"] = """
## Ultimate VL Capture Script (Non-Root Mode)

```bash
#!/bin/bash
# Pre-flight: Configure settings
adb shell settings put global animator_duration_scale 0

# Note: Layout bounds may require manual device settings or restart
# adb shell setprop debug.layout true  # May not work without root on some devices

# Capture
adb shell screencap -p /sdcard/screenshot.png
adb pull /sdcard/screenshot.png

# Dump hierarchy
adb shell uiautomator dump /data/local/tmp/uidump.xml
adb pull /data/local/tmp/uidump.xml

# Inference: Pass screenshot + hierarchy to VL model
```
"""
    
    instructions["benefits"] = """
## Why This Hybrid Approach?

This setup gives the VL model "x-ray vision":
- **Screenshot with Layout Bounds**: Visual context with explicit component boundaries
- **UI Hierarchy (XML)**: Ground truth coordinates, IDs, and metadata
- **Result**: Highest possible accuracy for component identification

The model gets both pixel-level visual information AND structural semantic data.
"""
    
    return instructions
