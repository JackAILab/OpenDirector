import json

from harness.core import AgentAction, HarnessRunner, Observation
from harness.tools import Tool, ToolRegistry
from harness.trajectory import TrajectoryRecorder, load_trajectory
from harness.agents import ScriptedAgent
from harness.tasks import Task


class PrivateObservationTool(Tool):
    name = 'private_observation'

    def invoke(self, arguments):
        return Observation(ok=True, content={
            'email': 'creator@example.com',
            'raw_payload': {'provider': 'must-not-persist'},
            'value': 3,
        })


def test_trajectory_redacts_personal_and_provider_payloads(tmp_path):
    registry = ToolRegistry()
    registry.register(PrivateObservationTool())
    result = HarnessRunner(registry, recorder=TrajectoryRecorder(tmp_path)).run(
        task=Task('privacy', 'contact creator@example.com at https://private.invalid/resource'),
        agent=ScriptedAgent([
            AgentAction.tool('private_observation', {'audio_prompt': 'secret voice direction'}),
            AgentAction.finish({}),
        ]), max_steps=2,
    )
    payload = load_trajectory(result.trajectory_path and __import__('pathlib').Path(result.trajectory_path))
    serialized = json.dumps(payload, ensure_ascii=False)
    assert 'creator@example.com' not in serialized
    assert 'private.invalid' not in serialized
    assert 'must-not-persist' not in serialized
    assert payload['steps'][0]['observation']['content']['value'] == 3
