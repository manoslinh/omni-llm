"""
Tests for the EditBlock parser.
"""

import pytest
import asyncio

from omni.edits.editblock import EditBlockParser
from omni.core.edit_loop import Edit


class TestEditBlockParser:
    """Tests for the EditBlockParser class."""
    
    @pytest.fixture
    def parser(self):
        """Create a parser for testing."""
        return EditBlockParser()
    
    @pytest.mark.asyncio
    async def test_parse_simple_search_replace(self, parser):
        """Test parsing simple SEARCH/REPLACE blocks."""
        text = """Here's the fix:

SEARCH
```
def old_function():
    return "old"
```
REPLACE
```
def new_function():
    return "new"
```

That should work."""
        
        edits = await parser.parse(text, "test.py")
        
        assert len(edits) == 1
        edit = edits[0]
        assert edit.file_path == "test.py"
        assert edit.old_text == 'def old_function():\n    return "old"'
        assert edit.new_text == 'def new_function():\n    return "new"'
    
    @pytest.mark.asyncio
    async def test_parse_file_specific(self, parser):
        """Test parsing blocks with file paths."""
        text = """test.py
SEARCH
```
print("hello")
```
REPLACE
```
print("world")
```

utils.py
SEARCH
```
def add(a, b):
    return a + b
```
REPLACE
```
def add(a, b):
    return a + b
```"""
        
        edits = await parser.parse(text)
        
        assert len(edits) == 2
        assert edits[0].file_path == "test.py"
        assert edits[0].old_text == 'print("hello")'
        assert edits[0].new_text == 'print("world")'
        
        assert edits[1].file_path == "utils.py"
        assert "def add" in edits[1].old_text
    
    @pytest.mark.asyncio
    async def test_parse_multiple_blocks(self, parser):
        """Test parsing multiple SEARCH/REPLACE blocks."""
        text = """SEARCH
```
line1
line2
```
REPLACE
```
new1
new2
```

SEARCH
```
line3
```
REPLACE
```
new3
```"""
        
        edits = await parser.parse(text, "multi.py")
        
        assert len(edits) == 2
        assert edits[0].old_text == "line1\nline2"
        assert edits[0].new_text == "new1\nnew2"
        assert edits[1].old_text == "line3"
        assert edits[1].new_text == "new3"
    
    @pytest.mark.asyncio
    async def test_parse_different_fences(self, parser):
        """Test parsing with different fence styles."""
        # Triple backticks
        text1 = """SEARCH
```
old
```
REPLACE
```
new
```"""
        
        # Triple tildes
        text2 = """SEARCH
~~~
old
~~~
REPLACE
~~~
new
~~~"""
        
        # Triple quotes
        text3 = '''SEARCH
"""
old
"""
REPLACE
"""
new
"""'''
        
        edits1 = await parser.parse(text1, "test.py")
        edits2 = await parser.parse(text2, "test.py")
        edits3 = await parser.parse(text3, "test.py")
        
        assert len(edits1) == 1
        assert edits1[0].old_text == "old"
        assert edits1[0].new_text == "new"
        
        assert len(edits2) == 1
        assert edits2[0].old_text == "old"
        
        assert len(edits3) == 1
        assert edits3[0].old_text == "old"
    
    @pytest.mark.asyncio
    async def test_parse_whole_file(self, parser):
        """Test parsing whole file code blocks."""
        text = """Here's the complete file:

```python
def main():
    print("Hello, world!")

if __name__ == "__main__":
    main()
```"""
        
        edits = await parser.parse(text, "main.py")
        
        assert len(edits) == 1
        assert edit.old_text == ""  # Empty search = whole file
        assert "def main()" in edit.new_text
        assert '__name__ == "__main__"' in edit.new_text
    
    @pytest.mark.asyncio
    async def test_find_best_match_exact(self, parser):
        """Test finding exact matches."""
        search = "hello world"
        content = "prefix hello world suffix"
        
        match = parser.find_best_match(search, content, "test.txt")
        
        assert match is not None
        start, end, matched = match
        assert start == 7  # "prefix " is 7 chars
        assert end == 18   # 7 + 11 ("hello world")
        assert matched == search
    
    def test_extract_context(self, parser):
        """Test extracting context from search text."""
        # Short text - returns as-is
        short = "line1\nline2"
        context = parser._extract_context(short)
        assert context == short
        
        # Long text - extracts first/last lines
        long_text = "\n".join(f"line{i}" for i in range(20))
        context = parser._extract_context(long_text)
        
        lines = context.split("\n")
        assert "line0" in lines[0]
        assert "line1" in lines[1]
        assert "line2" in lines[2]
        assert "..." in lines[3]
        assert "line17" in lines[4]
        assert "line18" in lines[5]
        assert "line19" in lines[6]
    
    def test_clean_code_block(self, parser):
        """Test cleaning code block text."""
        # Already clean
        assert parser._clean_code_block("code", "```") == "code"
        
        # With fence at end
        assert parser._clean_code_block("code\n```", "```") == "code"
        
        # With fence at start (shouldn't happen but handle it)
        assert parser._clean_code_block("```\ncode", "```") == "code"
        
        # Empty
        assert parser._clean_code_block("", "```") == ""
    
    @pytest.mark.asyncio
    async def test_validate_edits(self, parser):
        """Test validating edits against file contents."""
        edits = [
            Edit(file_path="test.py", old_text="find me", new_text="replaced"),
            Edit(file_path="new.py", old_text="", new_text="new content"),
        ]
        
        file_contents = {
            "test.py": "some text\nfind me\nmore text",
            "other.py": "different file",
        }
        
        errors = await parser.validate_edits(edits, file_contents)
        
        # Should have error for new.py (file doesn't exist for search)
        assert len(errors) == 1
        assert "File not found" in errors[0]
        
        # Test with all files existing
        file_contents["new.py"] = ""
        errors = await parser.validate_edits(edits, file_contents)
        assert len(errors) == 0  # Empty search is OK for existing file