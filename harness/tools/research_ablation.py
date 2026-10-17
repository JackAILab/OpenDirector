"""One explicit model call for the common-format reference ablation protocol."""
from harness.models.research_planner import ResearchPlanner
from harness.research.reference_ablation import decision_messages, validate_decision
from harness.tools.research_transfer import TransferValidationError


async def decide_once(visible, reference, history, policy, remaining, model,
                      max_tokens, force_finish=False):
    messages = decision_messages(visible, reference, history, policy, remaining, force_finish)
    raw, usage = await ResearchPlanner(model, max_tokens=max_tokens).complete(messages)
    try:
        result = validate_decision(raw, visible, reference, policy, remaining, force_finish)
    except ValueError as exc:
        raise TransferValidationError(str(exc), raw, usage, validation_error=exc) from None
    return {'result':result,'usage':usage,'semantic_review':'pending','training_eligible':False}
