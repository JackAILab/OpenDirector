"""Reserved LLM policy boundary; provider clients belong in harness.models."""

from harness.agents.base import Agent


class LLMAgent(Agent):
    def next_action(self, state):  # pragma: no cover - explicit extension point
        raise NotImplementedError("configure a concrete policy model before using LLMAgent")
