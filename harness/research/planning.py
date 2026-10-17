"""Research policy prompts, not production defaults or a complete transfer method."""
import json

PROMPT_VERSION = 'fact-sensitivity-smoke-v2'
CONDITIONS = ('direct', 'explicit_fact_check')
SYSTEM = '''你在虚构商品设定上规划15秒广告。只依据提供的商品事实，不编造功效、认证、价格或优惠；未知不是已支持。画面暗示同样需要事实依据。所有可读字幕后期生成。输出严格JSON，不输出私密推理。
输出格式：{"claim":"唯一主张","shots":[{"start":0,"end":5,"visual":"画面和动作","audio":"声音设计","caption":"字幕"},{"start":5,"end":10,"visual":"...","audio":"...","caption":"..."},{"start":10,"end":15,"visual":"...","audio":"...","caption":"..."}],"fact_basis":["实际采用的事实字段名"],"unresolved":["尚未解决的限制"]}。
shots数组必须恰好3项，只能使用0–5、5–10、10–15秒三个时间窗，每项5秒，总时长15秒。落版或品牌收束必须放在第三项内，不得添加第四项。禁止调用工具。请直接给出方案，不向用户提问。'''


def messages(visible, condition):
    if condition not in CONDITIONS:
        raise ValueError('Unknown smoke condition')
    instruction = '根据给定事实直接规划。'
    if condition == 'explicit_fact_check':
        instruction = ('先核对可能影响商品动作的能力及使用前提：支持、不支持或未知。'
                       '只有已支持且满足条件的能力才能作为证明动作；否则选择其他已知特点。'
                       '不把已有能力扩展到未测试环境。最终仍只输出相同JSON格式。')
    return [{'role':'system','content':SYSTEM},
            {'role':'user','content':json.dumps({'task':visible,'instruction':instruction},ensure_ascii=False)}]
