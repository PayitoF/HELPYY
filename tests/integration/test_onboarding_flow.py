"""Integration test — full onboarding flow from web widget to account creation."""

import pytest


@pytest.mark.integration
class TestOnboardingFlow:
    """E2E: user arrives → gives data → ML scores → account opens."""

    def test_happy_path_account_created(self):
        """User with good income completes onboarding and gets account."""
        # TODO: simulate conversation: name → cedula → income → ML approves → account created
        pass

    def test_rejection_path_with_plan(self):
        """User with low income gets rejection + improvement plan."""
        # TODO: simulate: low income → ML rejects → handoff to advisor → plan created
        pass

    def test_handles_messy_input(self):
        """Agent handles all data in one message: 'soy juan y mi cc es 123'."""
        # TODO: verify agent extracts name and cedula from unstructured input
        pass
