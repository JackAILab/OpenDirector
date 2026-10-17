import json
from tools.prepare_paper_plan_review import build
from harness.research.briefs import digest


def test_blind_review_keeps_each_plans_disclosed_facts_separate(tmp_path):
    run=tmp_path/'run';run.mkdir();initial={'brief':'A lamp ad','facts':{'known_features':'touch switch'}}
    conditions=['general_review','prerequisite_review']
    manifest={'conditions':conditions,'initial_prompts':{c:[{}, {'content':json.dumps({'task':initial})}] for c in conditions}}
    (run/'manifest.json').write_text(json.dumps(manifest))
    for index,condition in enumerate(conditions):
        facts=dict(initial['facts'])
        if index: facts['automatic_presence']='not supported'
        messages=[{}, {'content':json.dumps({'task':{**initial,'facts':facts}})}]
        observation={'result':{'claim':'Light','shots':[{'start':0,'end':15,'visual':'touch','audio':'music','caption':''}],'unresolved':[]}}
        event={'state':'completed','observation_sha256':digest(observation),'prompt_sha256':digest(messages)}
        for suffix,data in [('plan-input',{'messages':messages}),('plan-observation',observation),('plan-event',event)]:
            (run/f'{condition}-{suffix}.json').write_text(json.dumps(data))
    out=tmp_path/'packet';build(run,out,37)
    packet=json.loads((out/'packet.json').read_text())
    assert 'automatic_presence' not in packet['task']['facts']
    assert sum('automatic_presence' in p['disclosed_task']['facts'] for p in packet['plans'])==1
    html=(out/'review.html').read_text()
    assert all(c not in html for c in conditions)
    assert html.count('not supported')==1
