"""
EditBlock Parser.

Parses SEARCH/REPLACE blocks from model responses.
This is the primary edit format for capable models (GPT-4, Claude, etc.).

Based on Aider's editblock_coder.py patterns.
"""

import re
import logging
from typing import List, Optional, Tuple

from ..core.models import Edit


logger = logging.getLogger(__name__)


class EditBlockParser:
    """
    Parses SEARCH/REPLACE blocks from model responses.
    
    Format:
    SEARCH
    ```
    [exact code to find]
    ```
    REPLACE
    ```
    [new code to replace it with]
    ```
    
    Multiple blocks can be in one response.
    """
    
    # Regex to find SEARCH/REPLACE blocks
    # Supports different fence styles: ```, ~~~, """
    SEARCH_REPLACE_PATTERN = re.compile(
        r'SEARCH\s*\n?(```|~~~|""")?\s*\n?(.*?)\n?\1?\s*\n?REPLACE\s*\n?(```|~~~|""")?\s*\n?(.*?)\n?\3',
        re.DOTALL
    )
    
    # Alternative: SEARCH/REPLACE with file paths
    # More specific: file path should look like a filename (ends with .py, .js, .txt, etc.)
    # or be a simple filename without special chars
    FILE_SEARCH_REPLACE_PATTERN = re.compile(
        r'^(\S+\.\w+|\w+)\s*\nSEARCH\s*\n?(```|~~~|""")?\s*\n?(.*?)\n?\2?\s*\n?REPLACE\s*\n?(```|~~~|""")?\s*\n?(.*?)\n?\4',
        re.DOTALL | re.MULTILINE
    )
    
    def __init__(self, require_exact_match: bool = False):
        """
        Initialize the parser.
        
        Args:
            require_exact_match: If True, search text must match exactly.
                                 If False, allows fuzzy matching.
        """
        self.require_exact_match = require_exact_match
        logger.info(f"EditBlockParser initialized (exact_match={require_exact_match})")
    
    async def parse(self, text: str, file_path: Optional[str] = None) -> List[Edit]:
        """
        Parse SEARCH/REPLACE blocks from text.
        
        Args:
            text: Model response text
            file_path: Optional default file path if not specified in blocks
            
        Returns:
            List of Edit objects
        """
        edits = []
        
        # Try file-specific format first: "file.py\nSEARCH...\nREPLACE..."
        file_edits = self._parse_file_specific_blocks(text)
        if file_edits:
            edits.extend(file_edits)
            logger.debug(f"Found {len(file_edits)} file-specific edit blocks")
        
        # Try generic SEARCH/REPLACE blocks
        generic_edits = self._parse_generic_blocks(text, file_path)
        if generic_edits:
            edits.extend(generic_edits)
            logger.debug(f"Found {len(generic_edits)} generic edit blocks")
        
        # If no blocks found, try to extract code blocks as whole file replacements
        if not edits:
            whole_file_edits = self._parse_whole_file_blocks(text, file_path)
            if whole_file_edits:
                edits.extend(whole_file_edits)
                logger.debug(f"Found {len(whole_file_edits)} whole-file edit blocks")
        
        logger.info(f"Parsed {len(edits)} edit blocks from response")
        return edits
    
    def _parse_file_specific_blocks(self, text: str) -> List[Edit]:
        """Parse blocks with explicit file paths."""
        edits = []
        
        for match in self.FILE_SEARCH_REPLACE_PATTERN.finditer(text):
            file_path = match.group(1).strip()
            fence_start = match.group(2) or '```'
            search_text = match.group(3).strip()
            fence_end = match.group(4) or fence_start
            replace_text = match.group(5).strip()
            
            # Clean up the texts
            search_text = self._clean_code_block(search_text, fence_start)
            replace_text = self._clean_code_block(replace_text, fence_end)
            
            if search_text or replace_text:
                edit = Edit(
                    file_path=file_path,
                    old_text=search_text,
                    new_text=replace_text,
                    search_context=self._extract_context(search_text),
                )
                edits.append(edit)
                logger.debug(f"Parsed file-specific edit for {file_path}")
        
        return edits
    
    def _parse_generic_blocks(self, text: str, default_file: Optional[str]) -> List[Edit]:
        """Parse generic SEARCH/REPLACE blocks."""
        if not default_file:
            logger.warning("No default file path for generic edit blocks")
            return []
        
        edits = []
        
        for match in self.SEARCH_REPLACE_PATTERN.finditer(text):
            fence_start = match.group(1) or '```'
            search_text = match.group(2).strip()
            fence_end = match.group(3) or fence_start
            replace_text = match.group(4).strip()
            
            # Clean up the texts
            search_text = self._clean_code_block(search_text, fence_start)
            replace_text = self._clean_code_block(replace_text, fence_end)
            
            if search_text or replace_text:
                edit = Edit(
                    file_path=default_file,
                    old_text=search_text,
                    new_text=replace_text,
                    search_context=self._extract_context(search_text),
                )
                edits.append(edit)
                logger.debug(f"Parsed generic edit for {default_file}")
        
        return edits
    
    def _parse_whole_file_blocks(self, text: str, default_file: Optional[str]) -> List[Edit]:
        """
        Parse code blocks as whole file replacements.
        
        Used when model doesn't use SEARCH/REPLACE format but provides
        complete file contents.
        """
        if not default_file:
            return []
        
        # Find all code blocks
        code_block_pattern = re.compile(r'```(?:\w+)?\n(.*?)\n```', re.DOTALL)
        code_blocks = code_block_pattern.findall(text)
        
        edits = []
        for i, code in enumerate(code_blocks):
            code = code.strip()
            if code and len(code) > 10:  # Minimum reasonable size
                # For whole file replacement, search is empty
                edit = Edit(
                    file_path=default_file,
                    old_text="",  # Empty search = create/replace whole file
                    new_text=code,
                    search_context=None,
                )
                edits.append(edit)
                logger.debug(f"Parsed whole-file edit block #{i+1} for {default_file}")
        
        return edits
    
    def _clean_code_block(self, text: str, fence: str) -> str:
        """Clean up code block text."""
        if not text:
            return ""
        
        # Remove the fence if it appears at start/end
        text = text.strip()
        
        # Remove trailing fence
        if text.endswith(fence):
            text = text[:-len(fence)].rstrip()
        
        # Remove leading fence (shouldn't happen with our regex, but just in case)
        if text.startswith(fence):
            text = text[len(fence):].lstrip()
        
        return text
    
    def _extract_context(self, search_text: str) -> Optional[str]:
        """
        Extract context lines from search text for better matching.
        
        Returns the first and last few lines as context.
        """
        if not search_text:
            return None
        
        lines = search_text.split('\n')
        if len(lines) <= 10:
            return search_text  # Short enough to use as-is
        
        # Take first 3 and last 3 lines as context
        context_lines = lines[:3] + ['...'] + lines[-3:]
        return '\n'.join(context_lines)
    
    def find_best_match(
        self,
        search_text: str,
        file_content: str,
        file_path: str = ""
    ) -> Optional[Tuple[int, int, str]]:
        """
        Find the best match for search text in file content.
        
        Args:
            search_text: Text to search for
            file_content: Content of the file to search in
            file_path: Path for logging
            
        Returns:
            Tuple of (start_index, end_index, matched_text) or None
        """
        if not search_text:
            # Empty search = insert at beginning
            return 0, 0, ""
        
        # Try exact match first
        if self.require_exact_match:
            index = file_content.find(search_text)
            if index != -1:
                logger.debug(f"Exact match found in {file_path} at position {index}")
                return index, index + len(search_text), search_text
            else:
                logger.warning(f"No exact match found in {file_path}")
                return None
        
        # Fuzzy matching logic (simplified version of Aider's algorithm)
        
        # 1. Try with normalized whitespace
        normalized_search = self._normalize_whitespace(search_text)
        normalized_content = self._normalize_whitespace(file_content)
        
        index = normalized_content.find(normalized_search)
        if index != -1:
            # Map back to original positions (approximate)
            # This is simplified - Aider has more sophisticated mapping
            original_index = self._map_normalized_to_original(
                index, normalized_search, file_content
            )
            if original_index is not None:
                logger.debug(f"Normalized match found in {file_path} at position {original_index}")
                return original_index, original_index + len(search_text), search_text
        
        # 2. Try line-by-line matching
        search_lines = search_text.split('\n')
        content_lines = file_content.split('\n')
        
        for i in range(len(content_lines) - len(search_lines) + 1):
            if content_lines[i:i+len(search_lines)] == search_lines:
                # Calculate position in original content
                start_pos = len('\n'.join(content_lines[:i]))
                if i > 0:
                    start_pos += 1  # Account for newline
                end_pos = start_pos + len(search_text)
                logger.debug(f"Line-by-line match found in {file_path} at line {i+1}")
                return start_pos, end_pos, search_text
        
        # 3. Try with context (first/last few lines)
        if len(search_lines) > 6:
            context = self._extract_context(search_text)
            if context:
                # Recursively try with context
                return self.find_best_match(context, file_content, file_path)
        
        logger.warning(f"No match found in {file_path} for search text")
        return None
    
    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace for fuzzy matching."""
        # Replace multiple spaces/newlines with single space
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _map_normalized_to_original(
        self,
        normalized_index: int,
        normalized_search: str,
        original_content: str
    ) -> Optional[int]:
        """
        Map position from normalized text back to original text.
        
        This is a simplified version. Aider has more sophisticated logic.
        """
        # Count characters in normalized text up to the index
        normalized_up_to_index = normalized_search[:normalized_index]
        
        # Try to find equivalent position in original
        # This is approximate and works better for small edits
        original_index = original_content.find(normalized_search[:min(50, len(normalized_search))])
        if original_index != -1:
            return original_index
        
        return None
    
    async def validate_edits(self, edits: List[Edit], file_contents: dict) -> List[str]:
        """
        Validate that edits can be applied to files.
        
        Args:
            edits: List of edits to validate
            file_contents: Dict mapping file_path to content
            
        Returns:
            List of error messages, empty if all valid
        """
        errors = []
        
        for edit in edits:
            if edit.file_path not in file_contents:
                if edit.old_text:  # Can't search in non-existent file
                    errors.append(f"File not found: {edit.file_path}")
                # If old_text is empty, it's creating a new file (OK)
                continue
            
            content = file_contents[edit.file_path]
            
            if edit.old_text:  # Search/replace edit
                match = self.find_best_match(edit.old_text, content, edit.file_path)
                if not match:
                    errors.append(
                        f"Could not find search text in {edit.file_path}:\n"
                        f"{edit.search_context or edit.old_text[:100]}..."
                    )
            # else: creating new file or replacing entire file (always valid)
        
        return errors