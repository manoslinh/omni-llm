"""
Edit Loop Service.

The core send → parse → apply → verify → reflect cycle.
This orchestrates the entire AI coding workflow.
"""

import logging
from datetime import datetime

from ..edits.editblock import EditBlockParser
from ..git.repository import GitRepository
from ..models.provider import Message, MessageRole, ModelProvider
from .edit_applier import EditApplier
from .models import CycleResult, Edit, VerificationResult
from .verifier import NoOpVerifier, VerificationPipeline, Verifier

logger = logging.getLogger(__name__)


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
        git_repo: GitRepository | None = None,
        edit_parser: EditBlockParser | None = None,
        edit_applier: EditApplier | None = None,
        verifiers: list[Verifier] | None = None,  # None default avoids mutable default argument bug
        max_reflections: int = 3,
        base_path: str | None = None,
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
        self.edit_parser = edit_parser or EditBlockParser()
        self.edit_applier = edit_applier or EditApplier(base_path=base_path)
        self.verifiers = verifiers or [NoOpVerifier()]  # Create new list if None to avoid shared mutable default
        self.verification_pipeline = VerificationPipeline(self.verifiers)
        self.max_reflections = max_reflections

        self.reflection_count = 0
        self.total_cost = 0.0

        logger.info("EditLoop initialized")

    async def run_cycle(
        self,
        user_input: str,
        model: str = "openai/gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int | None = None,
        files_to_include: list[str] | None = None,
        create_feature_branch: bool = False,
        branch_name: str | None = None,
        merge_back: bool = True,
    ) -> CycleResult:
        """
        Run a complete edit cycle.

        Args:
            user_input: User's request/prompt
            model: Model to use for completion
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            files_to_include: Specific files to include in context
            create_feature_branch: Whether to create a feature branch for this edit
            branch_name: Name for the feature branch (auto-generated if not provided)
            merge_back: If creating a feature branch, whether to merge it back to original

        Returns:
            CycleResult with details of the cycle
        """
        try:
            # Create feature branch if requested
            original_branch = None
            if create_feature_branch and self.git_repo:
                original_branch = await self._create_feature_branch(branch_name, user_input)

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

            # Return to original branch if we created a feature branch
            if original_branch and self.git_repo:
                await self.git_repo.checkout_branch(original_branch)
                logger.info(f"Returned to original branch: {original_branch}")

            return result

        except Exception as e:
            logger.error(f"Edit cycle failed: {e}")

            # Still try to return to original branch even on error
            if original_branch and self.git_repo:
                try:
                    await self.git_repo.checkout_branch(original_branch)
                    logger.info(f"Returned to original branch after error: {original_branch}")
                except Exception as checkout_error:
                    logger.error(f"Failed to return to original branch: {checkout_error}")

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
        max_tokens: int | None,
        files_to_include: list[str] | None,
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
        # 1. Check for dirty changes and auto-commit if needed
        if self.git_repo:
            # Always call commit_dirty_changes to save current commit for undo
            # It will check for dirty changes internally and commit if needed
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_message = f"Auto-commit: {timestamp} - Uncommitted changes before AI edit"
            await self.git_repo.commit_dirty_changes(commit_message)

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
        default_file = files_to_include[0] if files_to_include else None
        edits = await self.edit_parser.parse(completion.content, file_path=default_file)

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
        files_to_include: list[str] | None,
        is_reflection: bool,
    ) -> list[Message]:
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
            role=MessageRole.SYSTEM,
            content=system_prompt,
        ))

        # TODO: Add RepoMap context
        # TODO: Add file contents
        # TODO: Add conversation history

        # User input
        messages.append(Message(
            role=MessageRole.USER,
            content=user_input,
        ))

        return messages

    async def _run_verifications(self, files: list[str]) -> VerificationResult:
        """
        Run all verifiers on modified files.

        Returns:
            VerificationResult with combined results
        """
        return await self.verification_pipeline.verify(files)

    def _build_reflection_prompt(
        self,
        original_input: str,
        verification_errors: list[str],
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
        edits: list[Edit],
        user_input: str,
    ) -> str:
        """Generate a commit message from edits and user input."""
        # Summarize what was changed
        files_changed = list({edit.file_path for edit in edits})

        if len(files_changed) == 1:
            summary = f"Update {files_changed[0]}"
        elif len(files_changed) <= 3:
            summary = f"Update {', '.join(files_changed)}"
        else:
            summary = f"Update {len(files_changed)} files"

        # Truncate user input for commit body
        body = user_input[:100] + ("..." if len(user_input) > 100 else "")

        return f"{summary}\n\n{body}"

    async def _create_feature_branch(
        self,
        branch_name: str | None,
        user_input: str,
    ) -> str | None:
        """
        Create a feature branch for this edit cycle.

        Args:
            branch_name: Optional custom branch name
            user_input: User input for generating branch name

        Returns:
            Original branch name if a feature branch was created, None otherwise
        """
        if not self.git_repo:
            return None

        # Get current branch
        original_branch = await self.git_repo.get_current_branch()

        # Generate branch name if not provided
        if not branch_name:
            # Create a sanitized branch name from user input
            import hashlib
            import re

            # Take first few words of user input
            words = user_input.split()[:5]
            sanitized = "_".join(re.sub(r'[^a-zA-Z0-9]', '', word.lower()) for word in words if word)

            # Add hash for uniqueness
            hash_part = hashlib.md5(user_input.encode()).hexdigest()[:8]

            branch_name = f"feature/{sanitized}_{hash_part}" if sanitized else f"feature/{hash_part}"

        # Create and checkout branch
        success = await self.git_repo.create_branch(branch_name, checkout=True)
        if success:
            logger.info(f"Created feature branch: {branch_name} (from {original_branch})")
            return original_branch
        else:
            logger.warning(f"Failed to create feature branch: {branch_name}")
            return None

    # Removed placeholder methods - using real implementations now

    async def close(self) -> None:
        """Clean up resources."""
        if self.git_repo:
            await self.git_repo.close()

        await self.verification_pipeline.close()

        logger.info(f"EditLoop closed (total cost: ${self.total_cost:.4f})")
