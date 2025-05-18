import pytest
import logging
from cot_proxy import convert_param_value, PARAM_TYPES

# Test cases for successful conversions
@pytest.mark.parametrize("key, value_str, expected_value", [
    # Float parameters
    ("temperature", "0.7", 0.7),
    ("top_p", "1.0", 1.0),
    ("presence_penalty", "0.0", 0.0),
    ("frequency_penalty", "-0.5", -0.5), # Assuming negative values are valid for some penalties
    ("repetition_penalty", "1.1", 1.1),
    # Integer parameters
    ("top_k", "40", 40),
    ("max_tokens", "1024", 1024),
    ("n", "1", 1),
    ("seed", "12345", 12345),
    ("num_ctx", "2048", 2048),
    ("num_predict", "512", 512),
    ("repeat_last_n", "64", 64),
    ("batch_size", "8", 8),
    # Boolean parameters
    ("echo", "true", True),
    ("echo", "True", True),
    ("echo", "TRUE", True),
    ("stream", "false", False),
    ("stream", "False", False),
    ("stream", "FALSE", False),
    ("mirostat", "1", False), # Mirostat is bool, current logic '1'.lower() == 'true' is False
    ("mirostat", "true", True),
    # Test with a key not in PARAM_TYPES
    ("unknown_param", "some_string_value", "some_string_value"),
    ("unknown_numeric_looking_param", "123.45", "123.45"), # Should remain string
])
def test_convert_param_value_successful(key, value_str, expected_value):
    """Test successful conversion of parameter values."""
    assert convert_param_value(key, value_str) == expected_value
    # For boolean, also check type
    if isinstance(expected_value, bool):
        assert isinstance(convert_param_value(key, value_str), bool)

# Test cases for 'null' and empty string
@pytest.mark.parametrize("key, value_str, expected_value", [
    ("temperature", "null", None),
    ("temperature", "NULL", None),
    ("top_k", "", None),
    ("stream", "null", None),
    ("unknown_param", "null", None), # null should always convert to None
    ("unknown_param", "", None),     # empty string should always convert to None
])
def test_convert_param_value_null_and_empty(key, value_str, expected_value):
    """Test 'null' and empty string conversions."""
    assert convert_param_value(key, value_str) is expected_value

# Test cases for conversion failures (should log warning and return original string)
@pytest.mark.parametrize("key, value_str", [
    ("temperature", "not_a_float"),
    ("top_k", "10.5"), # int param, float string
    ("top_k", "not_an_int"),
    ("max_tokens", "true"), # int param, bool string
    # Boolean conversion is specific: only 'true' (case-insensitive) is True. Others are False or original if not bool type.
    # The current convert_param_value for bool returns value.lower() == 'true'.
    # So, for a bool key, "not_true" would become False, not a conversion failure in the try-except.
    # Let's test a non-bool key that expects a number but gets a string that can't be converted.
])
def test_convert_param_value_conversion_failure(key, value_str, caplog):
    """Test conversion failures, expecting a warning and original string return."""
    caplog.clear() # Clear any previous logs
    param_type = PARAM_TYPES.get(key)
    
    # We only expect a warning if a specific type conversion is attempted and fails.
    # If param_type is None (unknown key), it returns value directly, no warning.
    if param_type and param_type != bool : # Bool conversion doesn't raise ValueError in the same way
        with caplog.at_level(logging.WARNING):
            result = convert_param_value(key, value_str)
        
        assert result == value_str # Should return original string
        assert len(caplog.records) == 1
        assert "Failed to convert parameter" in caplog.text
        assert f"'{key}'" in caplog.text
        assert f"'{value_str}'" in caplog.text
        assert param_type.__name__ in caplog.text
    elif param_type == bool:
        # For boolean, 'not_true' becomes False, 'true' becomes True. No ValueError.
        # This case is covered by successful conversion tests.
        # If we wanted to test a scenario where bool conversion itself could fail (not current logic),
        # this would be different.
        pass
    else: # Unknown key, no conversion attempted, no warning
        result = convert_param_value(key, value_str)
        assert result == value_str
        assert len(caplog.records) == 0


def test_convert_param_value_bool_specifics():
    """Test specific boolean conversion cases."""
    assert convert_param_value("stream", "True") is True
    assert convert_param_value("stream", "TRUE") is True
    assert convert_param_value("stream", "true") is True
    assert convert_param_value("stream", "False") is False
    assert convert_param_value("stream", "FALSE") is False
    assert convert_param_value("stream", "false") is False
    assert convert_param_value("stream", "0") is False # "0".lower() == 'true' is False
    assert convert_param_value("stream", "1") is False # "1".lower() == 'true' is False
    assert convert_param_value("stream", "yes") is False # "yes".lower() == 'true' is False
    assert convert_param_value("stream", "any_other_string") is False

def test_convert_param_value_unknown_key():
    """Test that an unknown key returns the value as a string without conversion attempt."""
    assert convert_param_value("new_unknown_parameter", "123") == "123"
    assert convert_param_value("another_one", "true_string") == "true_string"