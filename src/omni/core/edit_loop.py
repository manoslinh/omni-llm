"""
Edit Loop Service.

The core send → parse → apply → verify → reflect cycle.
This orchestrates the entire AI coding workflow.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..models.provider import ModelProvider, Message, CompletionResult
from ..git.repository import GitRepository  # Coming soon
from .edit_parser import EditParser  # Coming soon
from .edit_applier import EditApplier  # Coming soon
from .verifier import Verifier  # Coming soon


logger = logging.getLogger(__name__)


@dataclass
class Edit:
    """A single edit to apply to a file."""
    file_path: str
    old_text: str
    new_text: str
    search_context: Optional[str] = None


@dataclass
class ApplyResult:
    """Result of applying edits."""
    files_modified: List[str]
    files_created: List[str]
    files_deleted: List[str]
    errors: List[str]


@dataclass
class VerificationResult:
    """Result of verification pipeline."""
    passed: bool
    errors: List[str]
    warnings: List[str]
    details: Dict[str, Any]


@dataclass
class CycleResult:
    """Result of a complete edit cycle."""
    edits: List[Edit]
    verification: VerificationResult
    cost: float
    reflections: int
    success: bool


class EditLoop:
    """
    Orchestrates the edit loop cycle.
    
    This is the core engine that:
    1. Builds context from user input and codebase
    2. Sends to model for completion
    3. Parses the response into edits
    4. Applies edits to files
    5. Verifies with lint/test/etc.
    6. Reflects on errors if needed
    """
    
    def __init__(
        self,
        model_provider: ModelProvider,
        git_repo: Optional[Any] = None,  # GitRepository coming soon
        edit_parser: Optional[Any] = None,  # EditParser coming soon
        edit_applier: Optional[Any] = None,  # EditApplier coming soon
        verifiers: Optional[List[Any]] = None,  # List[Verifier] coming soon
        max_reflections: int = 3,
    ):
        """
        Initialize the edit loop.
        
        Args:
            model_provider: Provider for model completions
            git_repo: Git repository manager
            edit_parser: Parser for model responses
            edit_applier: Applier for edits to files
            verifiers: List of verifiers (lint, test, etc.)
            max_reflections: Maximum number of reflection cycles
        """
        self.model_provider = model_provider
        self.git_repo = git_repo
        self.edit_parser = edit_parser or self._create_default_parser()
        self.edit_applier = edit_applier or self._create_default_applier()
        self.verifiers = verifiers or []
        self.max_reflections = max_reflections
        
        self.reflection_count = 0
        self.total_cost = 0.0
        
        logger.info("EditLoop initialized")
    
    async def run_cycle(
        self,
        user_input: str,
        model: str = "openai/gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        files_to_include: Optional[List[str]] = None,
    ) -> CycleResult:
        """
        Run a complete edit cycle.
        
        Args:
            user_input: User's request/prompt
            model: Model to use for completion
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            files_to_include: Specific files to include in context
            
        Returns:
            CycleResult with details of the cycle
        """
        try:
            # Reset reflection count for new cycle
            self.reflection_count = 0
            
            # Start with initial attempt
            result = await self._run_single_attempt(
                user_input=user_input,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                files_to_include=files_to_include,
                is_reflection=False,
            )
            
            # Handle reflections if verification failed
            while (not result.verification.passed and 
                   self.reflection_count < self.max_reflections):
                
                self.reflection_count += 1
                logger.info(f"Starting reflection #{self.reflection_count}")
                
                # Build reflection prompt
                reflection_prompt = self._build_reflection_prompt(
                    original_input=user_input,
                    verification_errors=result.verification.errors,
                )
                
                # Run reflection attempt
                reflection_result = await self._run_single_attempt(
                    user_input=reflection_prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    files_to_include=files_to_include,
                    is_reflection=True,
                )
                
                # Update result
                result = reflection_result
            
            # Finalize
            result.success = result.verification.passed
            return result
            
        except Exception as e:
            logger.error(f"Edit cycle failed: {e}")
            return CycleResult(
                edits=[],
                verification=VerificationResult(
                    passed=False,
                    errors=[f"Edit cycle failed: {e}"],
                    warnings=[],
                    details={},
                ),
                cost=self.total_cost,
                reflections=self.reflection_count,
                success=False,
            )
    
    async def _run_single_attempt(
        self,
        user_input: str,
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        files_to_include: Optional[List[str]],
        is_reflection: bool,
    ) -> CycleResult:
        """
        Run a single attempt (no reflections).
        
        This is the core workflow:
        1. Build context
        2. Get model completion
        3. Parse edits
        4. Apply edits
        5. Verify results
        """
        # 1. Save dirty state (git commit)
        if self.git_repo:
            await self.git_repo.dirty_commit()
        
        # 2. Build context messages
        messages = await self._build_context_messages(
            user_input=user_input,
            files_to_include=files_to_include,
            is_reflection=is_reflection,
        )
        
        # 3. Get model completion
        completion = await self.model_provider.complete(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        # 4. Track cost
        cost = self.model_provider.estimate_cost(
            completion.usage.prompt_tokens,
            completion.usage.completion_tokens,
            model,
        )
        self.total_cost += cost
        
        # 5. Parse edits from completion
        edits = await self.edit_parser.parse(completion.content)
        
        if not edits:
            logger.warning("No edits parsed from model response")
            return CycleResult(
                edits=[],
                verification=VerificationResult(
                    passed=False,
                    errors=["No edits could be parsed from model response"],
                    warnings=[],
                    details={},
                ),
                cost=cost,
                reflections=self.reflection_count,
                success=False,
            )
        
        # 6. Apply edits
        apply_result = await self.edit_applier.apply(edits)
        
        if apply_result.errors:
            logger.warning(f"Errors applying edits: {apply_result.errors}")
            return CycleResult(
                edits=edits,
                verification=VerificationResult(
                    passed=False,
                    errors=apply_result.errors,
                    warnings=[],
                    details={"apply_result": apply_result},
                ),
                cost=cost,
                reflections=self.reflection_count,
                success=False,
            )
        
        # 7. Verify results
        verification = await self._run_verifications(
            files=apply_result.files_modified,
        )
        
        # 8. Commit if successful
        if verification.passed and self.git_repo and apply_result.files_modified:
            await self.git_repo.commit(
                files=apply_result.files_modified,
                message=self._generate_commit_message(edits, user_input),
                ai_attributed=True,
            )
        
        return CycleResult(
            edits=edits,
            verification=verification,
            cost=cost,
            reflections=self.reflection_count,
            success=verification.passed,
        )
    
    async def _build_context_messages(
        self,
        user_input: str,
        files_to_include: Optional[List[str]],
        is_reflection: bool,
    ) -> List[Message]:
        """
        Build context messages for the model.
        
        This assembles:
        - System prompt
        - Codebase context (RepoMap)
        - File contents
        - Conversation history
        - User input
        """
        messages = []
        
        # System prompt
        system_prompt = self._get_system_prompt(is_reflection)
        messages.append(Message(
            role="system",
            content=system_prompt,
        ))
        
        # TODO: Add RepoMap context
        # TODO: Add file contents
        # TODO: Add conversation history
        
        # User input
        messages.append(Message(
            role="user",
            content=user_input,
        ))
        
        return messages
    
    async def _run_verifications(self, files: List[str]) -> VerificationResult:
        """
        Run all verifiers on modified files.
        
        Returns:
            VerificationResult with combined results
        """
        all_errors = []
        all_warnings = []
        details = {}
        
        for verifier in self.verifiers:
            try:
                result = await verifier.verify(files)
                all_errors.extend(result.errors)
                all_warnings.extend(result.warnings)
                details[verifier.name] = result.details
            except Exception as e:
                logger.error(f"Verifier {verifier.name} failed: {e}")
                all_errors.append(f"Verifier {verifier.name} failed: {e}")
        
        passed = len(all_errors) == 0
        
        return VerificationResult(
            passed=passed,
            errors=all_errors,
            warnings=all_warnings,
            details=details,
        )
    
    def _build_reflection_prompt(
        self,
        original_input: str,
        verification_errors: List[str],
    ) -> str:
        """Build a reflection prompt from verification errors."""
        errors_text = "\n".join(f"- {error}" for error in verification_errors)
        
        return f"""The previous attempt failed verification. Please fix the issues and try again.

Original request: {original_input}

Verification errors:
{errors_text}

Please provide corrected code that addresses all the issues above."""
    
    def _get_system_prompt(self, is_reflection: bool) -> str:
        """Get the system prompt for the model."""
        if is_reflection:
            return """You are an AI coding assistant that fixes errors in code. 
You previously generated code that failed verification. Please fix the issues and provide corrected code.
Respond with SEARCH/REPLACE blocks to make the necessary changes."""
        
        return """You are an AI coding assistant. You help users write and modify code.
Respond with SEARCH/REPLACE blocks to make the requested changes.
Format your response as:

SEARCH
```
[exact code to find]
```
REPLACE
```
[new code to replace it with]
```

If you need to make changes to multiple files, use multiple SEARCH/REPLACE blocks.
If you're adding a new file, use a SEARCH block with an empty search.
Be precise and only change what's necessary."""
    
    def _generate_commit_message(
        self,
        edits: List[Edit],
        user_input: str,
    ) -> str:
        """Generate a commit message from edits and user input."""
        # Summarize what was changed
        files_changed = list(set(edit.file_path for edit in edits))
        
        if len(files_changed) == 1:
            summary = f"Update {files_changed[0]}"
        elif len(files_changed) <= 3:
            summary = f"Update {', '.join(files_changed)}"
        else:
            summary = f"Update {len(files_changed)} files"
        
        # Truncate user input for commit body
        body = user_input[:100] + ("..." if len(user_input) > 100 else "")
        
        return f"{summary}\n\n{body}"
    
    def _create_default_parser(self):
        """Create a default edit parser (placeholder)."""
        # This will be replaced with actual EditParser implementation
        class DefaultParser:
            async def parse(self, text: str) -> List[Edit]:
                logger.warning("Using default parser (no-op)")
                return []
        
        return DefaultParser()
    
    def _create_default_applier(self):
        """Create a default edit applier (placeholder)."""
        # This will be replaced with actual EditApplier implementation
        class DefaultApplier:
            async def apply(self, edits: List[Edit]) -> ApplyResult:
                logger.warning("Using default applier (no-op)")
                return ApplyResult(
                    files_modified=[],
                    files_created=[],
                    files_deleted=[],
                    errors=["No applier configured"],
                )
        
        return DefaultApplier()
    
    async def close(self):
        """Clean up resources."""
        if self.git_repo:
            await self.git_repo.close()
        
        logger.info(f"EditLoop closed (total cost: ${self.total_cost:.4f})")