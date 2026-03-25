"""
Verifier Interface and Base Implementation.

Defines the interface for verification plugins (lint, test, type-check, etc.).
Based on the implementation strategy's verification pipeline concept.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of a verification run."""
    passed: bool
    errors: List[str]
    warnings: List[str]
    details: Dict[str, Any]
    name: str = ""


class Verifier(ABC):
    """
    Abstract base class for verifiers.
    
    Verifiers check code quality, correctness, security, etc.
    Examples: linter, test runner, type checker, security scanner.
    """
    
    def __init__(self, name: str, enabled: bool = True):
        """
        Initialize verifier.
        
        Args:
            name: Unique name for this verifier
            enabled: Whether this verifier is active
        """
        self.name = name
        self.enabled = enabled
        logger.info(f"Verifier '{name}' initialized (enabled={enabled})")
    
    @abstractmethod
    async def verify(self, files: List[str]) -> VerificationResult:
        """
        Verify the given files.
        
        Args:
            files: List of file paths to verify
            
        Returns:
            VerificationResult with pass/fail status and details
        """
        pass
    
    async def close(self) -> None:
        """Clean up resources."""
        pass


class NoOpVerifier(Verifier):
    """A verifier that does nothing (for testing)."""
    
    def __init__(self):
        super().__init__("noop", enabled=True)
    
    async def verify(self, files: List[str]) -> VerificationResult:
        """Always passes."""
        return VerificationResult(
            passed=True,
            errors=[],
            warnings=[],
            details={"files_checked": files},
            name=self.name,
        )


class VerificationPipeline:
    """
    Orchestrates multiple verifiers.
    
    Runs verifiers in sequence and combines results.
    """
    
    def __init__(self, verifiers: Optional[List[Verifier]] = None):
        """
        Initialize verification pipeline.
        
        Args:
            verifiers: List of verifiers to run (in order)
        """
        self.verifiers = verifiers or []
        logger.info(f"VerificationPipeline initialized with {len(self.verifiers)} verifiers")
    
    async def verify(self, files: List[str]) -> VerificationResult:
        """
        Run all verifiers on the given files.
        
        Args:
            files: List of file paths to verify
            
        Returns:
            Combined VerificationResult
        """
        if not files:
            logger.debug("No files to verify")
            return VerificationResult(
                passed=True,
                errors=[],
                warnings=[],
                details={},
                name="pipeline",
            )
        
        all_errors = []
        all_warnings = []
        details = {}
        
        for verifier in self.verifiers:
            if not verifier.enabled:
                logger.debug(f"Skipping disabled verifier: {verifier.name}")
                continue
            
            try:
                logger.info(f"Running verifier: {verifier.name}")
                result = await verifier.verify(files)
                
                all_errors.extend(result.errors)
                all_warnings.extend(result.warnings)
                details[verifier.name] = result.details
                
                logger.debug(f"Verifier {verifier.name}: passed={result.passed}, "
                           f"errors={len(result.errors)}, warnings={len(result.warnings)}")
                
            except Exception as e:
                error_msg = f"Verifier {verifier.name} failed: {e}"
                logger.error(error_msg)
                all_errors.append(error_msg)
                details[verifier.name] = {"error": str(e)}
        
        passed = len(all_errors) == 0
        
        return VerificationResult(
            passed=passed,
            errors=all_errors,
            warnings=all_warnings,
            details=details,
            name="pipeline",
        )
    
    def add_verifier(self, verifier: Verifier) -> None:
        """Add a verifier to the pipeline."""
        self.verifiers.append(verifier)
        logger.info(f"Added verifier: {verifier.name}")
    
    async def close(self) -> None:
        """Close all verifiers."""
        for verifier in self.verifiers:
            try:
                await verifier.close()
            except Exception as e:
                logger.error(f"Error closing verifier {verifier.name}: {e}")
        
        logger.info("VerificationPipeline closed")