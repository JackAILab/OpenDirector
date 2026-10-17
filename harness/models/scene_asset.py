"""Provider-neutral 3D asset catalog.

The catalog deliberately reports availability instead of pretending that a
text/image-to-GLB provider is configured.  A real adapter can implement this
contract later without changing the scene API or its approval boundary.
"""
from typing import TypedDict


class SceneAssetModel(TypedDict):
    id: str
    label: str
    provider: str
    available: bool
    credits: int | None
    limitation: str


MODELS: tuple[SceneAssetModel, ...] = (
    {
        'id': 'meshforge-3d-pro',
        'label': '3D Asset Pro',
        'provider': 'unconfigured',
        'available': False,
        'credits': None,
        'limitation': '3D 供应商适配器尚未配置，当前不能提交生成',
    },
    {
        'id': 'meshforge-3d-fast',
        'label': '3D Asset Fast',
        'provider': 'unconfigured',
        'available': False,
        'credits': None,
        'limitation': '3D 供应商适配器尚未配置，当前不能提交生成',
    },
)


def model_spec(model: str) -> SceneAssetModel:
    for item in MODELS:
        if item['id'] == model:
            return dict(item)
    raise ValueError('所选 3D 资产模型未接入')


def quote_for(model: str) -> dict:
    """Return a non-purchasable quote until a paid provider is configured."""
    item = model_spec(model)
    return {
        'model': item['id'],
        'model_label': item['label'],
        'provider': item['provider'],
        'provider_available': item['available'],
        'credits': item['credits'],
        'currency': 'platform_credits',
        'limitation': item['limitation'],
    }


def task_status(intent: dict | None, quote: dict | None, *, stale: bool = False) -> dict:
    """Return a bounded, provider-neutral status for the 3D asset task.

    This is deliberately a state projection, not a provider poll.  A real
    adapter can populate the same quote fields after explicit approval without
    exposing credentials, raw provider payloads, or silently retrying work.
    """
    base = {
        'state': 'no_draft',
        'phase': 'draft',
        'label': '未创建 3D 资产草稿',
        'progress': None,
        'next_action': 'save_draft',
        'provider_task_id': None,
        'asset_id': None,
        'bound_object_id': None,
        'training_eligible': False,
        'stale': bool(stale),
    }
    if not isinstance(intent, dict):
        return base
    base.update(state='draft', label='草稿已保存 · 尚未检查供应商', next_action='prepare_quote')
    if stale:
        base.update(state='stale', phase='draft', label='草稿已过期 · 请重新保存', next_action='save_draft')
        return base
    if not isinstance(quote, dict):
        return base
    base['provider_task_id'] = str(quote.get('provider_task_id') or '')[:80] or None
    base['asset_id'] = str(quote.get('asset_id') or quote.get('result_asset_id') or '')[:32] or None
    base['bound_object_id'] = str(quote.get('bound_object_id') or '')[:48] or None
    progress = quote.get('provider_progress')
    if isinstance(progress, int) and 0 <= progress <= 100:
        base['progress'] = progress
    approval = str(quote.get('approval_state') or 'not_requested')
    provider_status = str(quote.get('provider_status') or '')
    if quote.get('provider_available') is False:
        base.update(state='blocked_provider_unconfigured', phase='blocked',
                    label='供应商未接入 · 未提交任务', next_action='configure_provider')
        return base
    if provider_status in ('failed', 'error', 'cancelled', 'canceled', 'uncertain'):
        base.update(state='provider_failed', phase='verification',
                    label='供应商任务未完成 · 需要人工处理', next_action='manual_review')
        return base
    if base['bound_object_id']:
        base.update(state='bound', phase='placement',
                    label='资产已绑定场景 · 等待站位核对', next_action='review_placement')
        return base
    if approval not in ('approved', 'submitted', 'completed', 'needs_review'):
        base.update(state='awaiting_approval', phase='approval',
                    label='报价已准备 · 等待明确确认', next_action='approve_quote')
        return base
    if base['asset_id']:
        base.update(state='needs_review', phase='verification',
                    label='资产已返回 · 等待 GLB 技术核验', next_action='verify_asset')
        return base
    if base['provider_task_id']:
        base.update(state='submitted', phase='generation',
                    label='任务已提交 · 等待供应商回执', next_action='refresh_status')
        return base
    base.update(state='ready_to_submit', phase='approval',
                label='确认已记录 · 等待适配器提交', next_action='submit_task')
    return base
