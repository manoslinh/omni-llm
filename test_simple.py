"""Simple test to verify pytest-asyncio works."""

import pytest


@pytest.mark.asyncio
async def test_simple():
    """Simple async test."""
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
