"""
Tests for ADB utilities module.

Note: These tests mock ADB commands and don't require a real device.
For integration testing with a real device, run with REAL_DEVICE=true environment variable.
"""

import os
import pytest
from unittest.mock import MagicMock, patch, call
from adb_utils import ADBHelper, get_setup_instructions


class TestADBHelper:
    """Tests for ADBHelper class."""
    
    def test_init_without_root(self):
        """Test ADBHelper initialization in non-root mode."""
        helper = ADBHelper(device_id="test_device", use_root=False)
        assert helper.device_id == "test_device"
        assert helper.use_root is False
        assert helper.is_root_available is False
    
    @patch('adb_utils.ADBHelper._check_root_access')
    def test_init_with_root_available(self, mock_check_root):
        """Test ADBHelper initialization when root is available."""
        mock_check_root.return_value = True
        helper = ADBHelper(device_id=None, use_root=True)
        assert helper.use_root is True
        assert helper.is_root_available is True
    
    @patch('adb_utils.ADBHelper._check_root_access')
    def test_init_with_root_unavailable(self, mock_check_root):
        """Test ADBHelper fallback when root is requested but unavailable."""
        mock_check_root.return_value = False
        helper = ADBHelper(use_root=True)
        assert helper.use_root is False
        assert helper.is_root_available is False
    
    def test_build_adb_command_with_device(self):
        """Test ADB command building with specific device."""
        helper = ADBHelper(device_id="test123")
        cmd = helper._build_adb_command("screencap -p", use_shell=True)
        assert cmd == ["adb", "-s", "test123", "shell", "screencap", "-p"]
    
    def test_build_adb_command_without_device(self):
        """Test ADB command building without device ID."""
        helper = ADBHelper()
        cmd = helper._build_adb_command("screencap -p", use_shell=True)
        assert cmd == ["adb", "shell", "screencap", "-p"]
    
    def test_build_adb_command_no_shell(self):
        """Test ADB command building without shell."""
        helper = ADBHelper()
        cmd = helper._build_adb_command("devices", use_shell=False)
        assert cmd == ["adb", "devices"]
    
    @patch('subprocess.run')
    def test_run_command_success(self, mock_run):
        """Test successful command execution."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="command output",
            stderr=""
        )
        
        helper = ADBHelper()
        success, output = helper._run_command("test command")
        
        assert success is True
        assert output == "command output"
    
    @patch('subprocess.run')
    def test_run_command_failure(self, mock_run):
        """Test failed command execution."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error message"
        )
        
        helper = ADBHelper()
        success, output = helper._run_command("test command")
        
        assert success is False
        assert output == "error message"
    
    @patch('subprocess.run')
    def test_configure_optimal_visual_settings(self, mock_run):
        """Test device configuration for optimal capture."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        helper = ADBHelper()
        results = helper.configure_optimal_visual_settings()
        
        # Should attempt to configure multiple settings
        assert "layout_bounds" in results
        assert "animations_disabled" in results
        assert "demo_mode" in results
        
        # Verify ADB commands were called
        assert mock_run.call_count >= 5
    
    @patch('subprocess.run')
    def test_restore_default_settings(self, mock_run):
        """Test restoration of default device settings."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        helper = ADBHelper()
        results = helper.restore_default_settings()
        
        assert "layout_bounds_restored" in results
        assert "animations_restored" in results
        assert "demo_mode_disabled" in results
    
    @patch('subprocess.run')
    def test_dump_ui_hierarchy_standard(self, mock_run):
        """Test UI hierarchy dump using standard method."""
        # Mock uiautomator dump
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="UI dumped\n", stderr=""),
            MagicMock(returncode=0, stdout="<?xml version='1.0'?><hierarchy></hierarchy>", stderr="")
        ]
        
        helper = ADBHelper(use_root=False)
        success, xml_content = helper.dump_ui_hierarchy()
        
        assert success is True
        assert xml_content.startswith("<?xml")
    
    @patch('subprocess.run')
    def test_dump_ui_hierarchy_root(self, mock_run):
        """Test UI hierarchy dump using root method."""
        # Mock root check and dumpsys
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="uid=0(root)", stderr=""),  # Root check
            MagicMock(returncode=0, stdout="View hierarchy data", stderr="")  # Dumpsys
        ]
        
        helper = ADBHelper(use_root=True)
        success, output = helper.dump_ui_hierarchy()
        
        assert success is True
        assert "View hierarchy" in output
    
    def test_parse_ui_hierarchy_valid_xml(self):
        """Test parsing valid UI hierarchy XML."""
        xml = '''<?xml version="1.0"?>
        <hierarchy rotation="0">
            <node index="0" text="Login" resource-id="com.app:id/login" 
                  class="android.widget.Button" clickable="true" enabled="true"
                  bounds="[100,200][300,400]"/>
            <node index="1" text="Username" resource-id="com.app:id/username"
                  class="android.widget.EditText" clickable="false" enabled="true"
                  bounds="[50,100][350,150]"/>
        </hierarchy>'''
        
        helper = ADBHelper()
        elements = helper.parse_ui_hierarchy(xml)
        
        assert elements is not None
        assert len(elements) == 2
        
        # Check first element
        assert elements[0]["text"] == "Login"
        assert elements[0]["resource_id"] == "com.app:id/login"
        assert elements[0]["clickable"] is True
        assert "bounds_parsed" in elements[0]
        assert elements[0]["bounds_parsed"]["x_min"] == 100
        assert elements[0]["bounds_parsed"]["y_min"] == 200
    
    def test_parse_ui_hierarchy_invalid_xml(self):
        """Test parsing invalid XML returns None."""
        helper = ADBHelper()
        elements = helper.parse_ui_hierarchy("not valid xml")
        assert elements is None
    
    def test_parse_ui_hierarchy_nested_elements(self):
        """Test parsing nested XML structure."""
        xml = '''<?xml version="1.0"?>
        <hierarchy>
            <node index="0" class="android.widget.FrameLayout" bounds="[0,0][1000,2000]">
                <node index="1" text="Child" class="android.widget.TextView" bounds="[10,10][100,100]"/>
            </node>
        </hierarchy>'''
        
        helper = ADBHelper()
        elements = helper.parse_ui_hierarchy(xml)
        
        assert elements is not None
        assert len(elements) == 2  # Parent and child
        assert elements[0]["depth"] == 0
        assert elements[1]["depth"] == 1
        assert elements[1]["text"] == "Child"


class TestSetupInstructions:
    """Tests for setup instruction generation."""
    
    def test_get_instructions_unrooted(self):
        """Test setup instructions for unrooted device."""
        instructions = get_setup_instructions(rooted=False)
        
        assert "visual_settings" in instructions
        assert "avoid_settings" in instructions
        assert "adb_visual_setup" in instructions
        assert "structural_setup" in instructions
        assert "ultimate_script" in instructions
        assert "benefits" in instructions
        
        # Check that unrooted content is appropriate
        assert "uiautomator" in instructions["structural_setup"]
        assert "Non-Root Mode" in instructions["ultimate_script"]
    
    def test_get_instructions_rooted(self):
        """Test setup instructions for rooted device."""
        instructions = get_setup_instructions(rooted=True)
        
        assert "structural_setup" in instructions
        assert "ultimate_script" in instructions
        
        # Check that rooted content includes root features
        assert "su -c" in instructions["structural_setup"]
        assert "Root Mode" in instructions["ultimate_script"]
        assert "dumpsys" in instructions["structural_setup"]
    
    def test_instructions_contain_key_settings(self):
        """Test that instructions mention key settings."""
        instructions = get_setup_instructions(rooted=False)
        visual = instructions["visual_settings"]
        
        # Check for key settings
        assert "Layout Bounds" in visual
        assert "Disable Animations" in visual
        assert "Demo Mode" in visual
        assert "High Contrast Text" in visual
    
    def test_instructions_contain_warnings(self):
        """Test that instructions include warnings about bad settings."""
        instructions = get_setup_instructions(rooted=False)
        avoid = instructions["avoid_settings"]
        
        assert "pointer location" in avoid
        assert "surface updates" in avoid
        assert "Force Dark Mode" in avoid


class TestIntegrationScenarios:
    """Integration-style tests for complete workflows."""
    
    @patch('subprocess.run')
    def test_complete_capture_workflow(self, mock_run):
        """Test complete workflow: configure, capture, restore."""
        # Mock all subprocess calls as successful
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="success",
            stderr=""
        )
        
        helper = ADBHelper()
        
        # Configure
        config_result = helper.configure_optimal_visual_settings()
        assert config_result["layout_bounds"]
        
        # Capture screenshot - will succeed because subprocess is mocked
        success, path = helper.capture_screenshot()
        assert success
        
        # Dump hierarchy - will succeed because subprocess is mocked  
        success, xml = helper.dump_ui_hierarchy()
        assert success
        
        # Restore
        restore_result = helper.restore_default_settings()
        assert restore_result["animations_restored"]


# Integration tests that require real device
@pytest.mark.skipif(
    os.environ.get("REAL_DEVICE") != "true",
    reason="Requires real Android device connected via ADB"
)
class TestRealDevice:
    """Tests that require a real device. Run with REAL_DEVICE=true."""
    
    def test_real_device_configuration(self):
        """Test configuration on real device."""
        helper = ADBHelper()
        results = helper.configure_optimal_visual_settings()
        
        # At least some settings should succeed
        assert any(results.values())
    
    def test_real_device_hierarchy_dump(self):
        """Test hierarchy dump on real device."""
        helper = ADBHelper()
        success, xml = helper.dump_ui_hierarchy()
        
        if success:
            # If successful, should be valid XML
            assert xml is not None
            assert "<?xml" in xml or "hierarchy" in xml.lower()
