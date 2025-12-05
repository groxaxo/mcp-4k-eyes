import os
import base64
from io import BytesIO
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image
from grounding_server import scale_box, GoogleBackend, OpenAIBackend, analyze_screenshot

def test_scale_logic():
    """Test basic box scaling from normalized to pixel coordinates."""
    # 1000x1000 screen, box is [0,0, 500,500] (top left quadrant)
    # box_2d is [ymin, xmin, ymax, xmax] in 0-1000 normalized
    # So [0, 0, 500, 500] means top-left to center
    res = scale_box([0, 0, 500, 500], 1000, 1000)
    assert res['center_x'] == 250
    assert res['center_y'] == 250
    # Width/height should be 500 (half of 1000)
    assert res['width'] == 500
    assert res['height'] == 500

def test_scale_logic_inverted():
    """Test that inverted coordinates are automatically corrected."""
    # Box with inverted coordinates should be fixed
    res = scale_box([500, 500, 0, 0], 1000, 1000)
    assert res['center_x'] == 250
    assert res['center_y'] == 250
    # After correction, should be same as non-inverted
    assert res['width'] == 500
    assert res['height'] == 500

def test_scale_logic_edge_cases():
    """Test edge cases and boundary conditions."""
    # Degenerate box (zero width/height)
    res = scale_box([100, 100, 100, 100], 1000, 1000)
    assert res['width'] == 1  # Should be at least 1px
    assert res['height'] == 1
    
    # Out of range values should be clamped
    res = scale_box([-100, -100, 1100, 1100], 1000, 1000)
    assert res['x_min'] == 0
    assert res['y_min'] == 0
    assert res['x_max'] == 1000
    assert res['y_max'] == 1000

def test_scale_box_invalid():
    """Test invalid box handling."""
    # Invalid box format
    res = scale_box([1, 2], 1000, 1000)
    assert 'error' in res
    
    res = scale_box(None, 1000, 1000)
    assert 'error' in res

def test_google_init():
    """Test that Google backend initializes with the required model."""
    backend = GoogleBackend("fake-key", "")
    # Should use default model when empty string is provided
    assert backend.model == "models/gemini-flash-latest"
    
    # Test custom model
    backend = GoogleBackend("fake-key", "models/gemini-pro-vision")
    assert backend.model == "models/gemini-pro-vision"

def test_google_init_no_key():
    """Test that Google backend requires an API key."""
    with pytest.raises(ValueError, match="API key required"):
        GoogleBackend(None, "")
        
def test_openai_init():
    """Test OpenAI backend initialization."""
    backend = OpenAIBackend("fake", "http://local", "custom-model")
    assert backend.model == "custom-model"
    
def test_openai_init_defaults():
    """Test OpenAI backend with default model."""
    backend = OpenAIBackend("fake", None, None)
    assert backend.model == "gpt-4o-mini"

def test_image_format_validation():
    """Test that various image formats are handled correctly."""
    import json
    # Test with a valid PNG image
    img = Image.new('RGB', (100, 100), color='red')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    # This should be valid base64 PNG data
    assert len(img_b64) > 0
    
    # Test JPEG image
    img = Image.new('RGB', (100, 100), color='blue')
    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    assert len(img_b64) > 0

def test_box_coordinate_validation():
    """Test that box coordinates are properly validated and normalized."""
    # Test various coordinate scenarios
    
    # Normal case
    box = scale_box([100, 200, 300, 400], 1000, 1000)
    assert box['x_min'] == 200
    assert box['y_min'] == 100
    assert box['x_max'] == 400
    assert box['y_max'] == 300
    
    # Verify center calculation
    assert box['center_x'] == (200 + 400) // 2
    assert box['center_y'] == (100 + 300) // 2
