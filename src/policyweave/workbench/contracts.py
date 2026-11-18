"""Trusted application integration boundary; never supplied by the model or browser."""

from typing import Callable, Protocol


class ApplicationAdapter(Protocol):
    name: str
    revision: str
    policy_origin: str
    policy_hash: str
    binding: dict
    documents: list[dict]
    setup_fields: list[dict]

    def reference(self) -> dict:
        """Return the initial pinned review with its actual reference/model origin."""
        ...

    def validate_setup(self, setup: dict) -> None:
        """Validate the supported scenario setup before any execution."""
        ...

    def run(
        self, scenario: dict, mode: str, seed: int, emit: Callable[[dict], None]
    ) -> dict:
        """Reset state for each call and execute the original or protected application.

        Emit actual operation-boundary events. Return completed (bool or None),
        initialStateHash and configurationHash. Model usage is optional, measured
        metadata; never substitute fabricated token counts.
        """
        ...

    def inspect(self, snapshot: dict, question: str) -> dict:
        """Optional registered read-only question over captured evidence."""
        ...
