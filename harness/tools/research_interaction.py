"""Bounded decision action, distinct from the model adapter and oracle action."""
from harness.models.research_planner import ResearchPlanner
from harness.research.interaction import validate_decision
from harness.tools.research_transfer import TransferValidationError


async def decide_once(messages,model,visible,reference,condition,max_tokens):
    raw,usage=await ResearchPlanner(model,max_tokens=max_tokens).complete(messages)
    try:result=validate_decision(raw,visible,reference,condition)
    except ValueError as e:raise TransferValidationError(str(e),raw,usage,validation_error=e) from None
    return {'result':result,'usage':usage,'semantic_review':'pending','training_eligible':False}
