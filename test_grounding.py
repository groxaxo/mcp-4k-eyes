import os
from unittest.mock import MagicMock
import pytest
from grounding_server import scale_box, GoogleBackend, OpenAIBackend

def test_scale_logic():
    # 1000x1000 screen, box is [0,0, 500,500] (top left quadrant)
    res = scale_box([0, 0, 500, 500], 1000, 1000)
    assert res['center_x'] == 250
    assert res['center_y'] == 250

def test_google_init():
    # Test that Google backend initializes with the required model
    backend = GoogleBackend("fake-key", "")
    # Should use default model when empty string is provided
    assert backend.model == "models/gemini-flash-latest"
        
def test_openai_init():
    backend = OpenAIBackend("fake", "http://local", "custom-model")
    assert backend.model == "custom-model"
