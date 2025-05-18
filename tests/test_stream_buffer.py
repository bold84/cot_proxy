import pytest
from cot_proxy import StreamBuffer # Assuming StreamBuffer is accessible from cot_proxy

# Default tags for most tests, can be overridden
DEFAULT_START_TAG = "<think>"
DEFAULT_END_TAG = "</think>"

@pytest.fixture
def buffer():
    """Returns a StreamBuffer instance with default tags."""
    return StreamBuffer(DEFAULT_START_TAG, DEFAULT_END_TAG)

@pytest.fixture
def custom_tag_buffer():
    """Returns a StreamBuffer instance with custom tags."""
    return StreamBuffer("<custom_start>", "</custom_end>")

def test_buffer_init(buffer):
    assert buffer.buffer == ""
    assert buffer.start_tag == DEFAULT_START_TAG
    assert buffer.end_tag == DEFAULT_END_TAG

def test_process_chunk_no_tags(buffer):
    chunk = b"This is a simple chunk."
    output = buffer.process_chunk(chunk)
    output += buffer.flush()
    assert output == chunk

def test_process_chunk_complete_tag_in_one_chunk(buffer):
    chunk = b"Hello <think>some thoughts</think> world!"
    output = buffer.process_chunk(chunk)
    output += buffer.flush()
    assert output == b"Hello  world!"

def test_process_chunk_tag_split_across_chunks(buffer):
    chunk1 = b"Hello <th"
    chunk2 = b"ink>some thoughts</th"
    chunk3 = b"ink> world!"
    
    output = b""
    output += buffer.process_chunk(chunk1)
    output += buffer.process_chunk(chunk2)
    output += buffer.process_chunk(chunk3)
    output += buffer.flush()
    assert output == b"Hello  world!"


def test_multiple_tags_in_one_chunk(buffer):
    chunk = b"A<think>1</think>B<think>2</think>C"
    output = buffer.process_chunk(chunk)
    output += buffer.flush()
    assert output == b"ABC"

def test_content_before_between_after_tags(buffer):
    chunk = b"Prefix <think>thought1</think> Infix <think>thought2</think> Suffix"
    output = buffer.process_chunk(chunk)
    output += buffer.flush()
    assert output == b"Prefix  Infix  Suffix"

def test_partial_start_tag_at_end_of_chunk(buffer):
    chunk1 = b"Text before <thi"
    chunk2 = b"nk>thought</think> and after."
    
    output = b""
    output += buffer.process_chunk(chunk1)
    # Check intermediate buffer state if necessary, but focus on final combined output
    # assert buffer.buffer == "Text before <thi"
    output += buffer.process_chunk(chunk2)
    output += buffer.flush()
    assert output == b"Text before  and after."

def test_partial_end_tag_at_end_of_chunk(buffer):
    chunk1 = b"Text <think>thought1</th"
    chunk2 = b"ink> and after."

    output = b""
    output += buffer.process_chunk(chunk1)
    output += buffer.process_chunk(chunk2)
    output += buffer.flush()
    assert output == b"Text  and after."

def test_flush_empty_buffer(buffer):
    assert buffer.flush() == b""

def test_flush_remaining_content_no_tags(buffer):
    buffer.buffer = "Remaining content"
    assert buffer.flush() == b"Remaining content"

def test_flush_remaining_content_with_incomplete_start_tag(buffer):
    buffer.buffer = "Content <think partial"
    assert buffer.flush() == b"Content <think partial" # Incomplete tag should be flushed as is

def test_flush_remaining_content_with_incomplete_end_tag(buffer):
    # This implies a start tag was found and removed, or it's complex.
    # If buffer is "<think>content</thin"
    buffer.buffer = "<think>content</thin" # Assume it got into this state
    assert buffer.flush() == b"<think>content</thin" # Flushed as is

def test_custom_tags(custom_tag_buffer):
    chunk = b"Data <custom_start>secret</custom_end> more data"
    output = custom_tag_buffer.process_chunk(chunk)
    output += custom_tag_buffer.flush()
    assert output == b"Data  more data"

def test_buffer_heuristic_long_unclosed_tag(buffer):
    # Test the heuristic: if len(self.buffer) > (len(self.start_tag) + 4096)
    # This part of the code currently has `pass # Keep in buffer`
    # So, it should just keep buffering.
    long_text_without_end = DEFAULT_START_TAG + "a" * 5000
    chunk = long_text_without_end.encode("utf-8")
    
    processed_output = buffer.process_chunk(chunk)
    # The current logic of process_chunk:
    # if start == -1 (no start_tag found):
    #   if len(self.buffer) > 1024: output += self.buffer[:-1024]; self.buffer = self.buffer[-1024:]
    # if start != -1 (start_tag found):
    #   output += self.buffer[:start]; self.buffer = self.buffer[start:]
    #   end = self.buffer.find(self.end_tag, start)
    #   if end == -1 (no end_tag):
    #     if len(self.buffer) > (len(self.start_tag) + 4096): pass # Keep in buffer
    #     break
    # So, if a start tag is found, and no end tag, and buffer gets very long, it stays in buffer.
    # `process_chunk` itself might not return anything in this case if the start tag was at index 0.
    
    assert processed_output == b"" # Because start_tag is at index 0, no preceding text.
    assert buffer.buffer == long_text_without_end
    
    # If we flush, it should come out.
    assert buffer.flush() == chunk

def test_buffer_clearing_after_processing_and_flushing(buffer):
    chunk = b"<think>text</think>"
    buffer.process_chunk(chunk)
    buffer.flush()
    assert buffer.buffer == "" # Buffer should be empty after flush

def test_unicode_characters_in_tags_and_content(buffer):
    start_tag_uni = "<คิด>"
    end_tag_uni = "</คิด>"
    buffer_uni = StreamBuffer(start_tag_uni, end_tag_uni)
    
    content_uni = "ข้อมูล <คิด>ความคิดเห็น</คิด> เพิ่มเติม".encode("utf-8")
    output = buffer_uni.process_chunk(content_uni)
    output += buffer_uni.flush()
    assert output == "ข้อมูล  เพิ่มเติม".encode("utf-8")

def test_empty_chunk_processing(buffer):
    buffer.buffer = "some data"
    processed = buffer.process_chunk(b"") # Empty chunk
    # process_chunk with empty input should still process existing buffer
    # but the return value depends on the 1024 rule.
    # Let's check buffer state.
    assert buffer.buffer == "some data" # No change if no tags and not > 1024
    assert processed == b"" # Or part of "some data" if it were > 1024 and no tags
    
    buffer.buffer = "<think>abc</think>def"
    processed_after_empty_chunk = buffer.process_chunk(b"")
    # This should process the "<think>abc</think>" part.
    # Output "def" might be held back by 1024 rule or if it's the remainder.
    # Let's check flushed output.
    assert buffer.flush() == b"def"
    # And processed_after_empty_chunk should be empty because "def" is after the tag.
    # No, process_chunk returns what's processed *before* a potential partial tag.
    # If "<think>abc</think>" is processed, buffer becomes "def".
    # The output of process_chunk would be "" if "def" is all that's left and small.
    # This is getting complicated. Let's simplify:
    
    buffer_test = StreamBuffer(DEFAULT_START_TAG, DEFAULT_END_TAG)
    buffer_test.buffer = "<think>data</think>remaining"
    # Calling process_chunk(b"") should process the buffered content.
    # 1. Finds "<think>" at 0. Buffer is "<think>data</think>remaining". Output ""
    # 2. Finds "</think>" at 12. Removes tag. Buffer becomes "remaining".
    # 3. Loop again. No "<think>" in "remaining".
    #    If len("remaining") > 1024, it would output part of it. Here, no.
    # So, process_chunk(b"") would return b"" in this case.
    assert buffer_test.process_chunk(b"") == b""
    assert buffer_test.buffer == "remaining" # Correctly processed the tag.
    assert buffer_test.flush() == b"remaining"


def test_edge_case_tag_is_entire_chunk(buffer):
    chunk = b"<think>content</think>"
    output = buffer.process_chunk(chunk)
    output += buffer.flush()
    assert output == b""

def test_edge_case_only_start_tag(buffer):
    chunk = b"<think>"
    output = buffer.process_chunk(chunk)
    output += buffer.flush()
    assert output == b"<think>"

def test_edge_case_only_end_tag(buffer):
    chunk = b"</think>"
    output = buffer.process_chunk(chunk)
    output += buffer.flush()
    assert output == b"</think>"

def test_edge_case_nested_like_tags_incorrectly_but_should_be_greedy(buffer):
    # The current implementation is greedy and doesn't handle true nesting.
    # It finds first start, then first end after that.
    chunk = b"<think>outer<think>inner</think>outer_end</think>"
    # Expected: Finds first "<think>", then first "</think>" (which is inner's).
    # So, "outer<think>inner" is removed. Remaining: "outer_end</think>"
    output = buffer.process_chunk(chunk)
    output += buffer.flush()
    assert output == b"outer_end</think>"

def test_max_buffer_retention_logic(buffer):
    # Test the `if len(self.buffer) > 1024:` part when no tags are found.
    long_initial_text = "a" * 2000
    buffer.buffer = long_initial_text
    
    # Process an empty chunk to trigger the buffer check without adding new data
    processed = buffer.process_chunk(b"")
    
    # Expected: output = buffer[:-1024], buffer = buffer[-1024:]
    expected_output = long_initial_text[:-1024]
    expected_remaining_buffer = long_initial_text[-1024:]
    
    assert processed == expected_output.encode("utf-8")
    assert buffer.buffer == expected_remaining_buffer
    assert buffer.flush() == expected_remaining_buffer.encode("utf-8")