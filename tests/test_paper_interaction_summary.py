import json
from pathlib import Path
import pytest
from harness.research.briefs import digest,visible_input
from tools.summarize_paper_interaction import summarize


def test_aggregation_counts_family_once_retains_missing_usage_and_rejects_duplicates(tmp_path):
    dataset_path=Path('data/research/advertising_goal_dependent_briefs_v1.json')
    dataset=json.loads(dataset_path.read_text());runs=[]
    for i,card in enumerate(dataset['cards'][:2]):
        run=tmp_path/str(i);run.mkdir();runs.append(run)
        prompt=[{'role':'system','content':'test'},{'role':'user','content':json.dumps({'task':visible_input(card,'underspecified')})}]
        manifest={'dataset_sha256':digest(dataset),'card_id':card['id'],'protocol_version':'test','model':'test',
            'reference_sha256':'reference','implementation_sha256':{'file':'same'},'conditions':['general_review'],
            'initial_prompts':{'general_review':prompt}}
        obs={'result':{},'usage':{'prompt_tokens':2,'completion_tokens':3,'total_tokens':5} if i==0 else {}}
        files={'manifest.json':manifest,'summary.json':{'conditions':[{'condition':'general_review','plan_completed':True,'questions_used':0}]},
            'general_review-plan-input.json':{'messages':prompt},'general_review-plan-observation.json':obs,
            'general_review-plan-event.json':{'stage':'plan','state':'completed','prompt_sha256':digest(prompt),
                'observation_sha256':digest(obs),'elapsed_seconds':1.2}}
        for name,value in files.items():(run/name).write_text(json.dumps(value))
    result=summarize(dataset_path,runs)
    assert result['calls']==2 and result['completed_plans']==2 and result['independent_family_count']==1
    assert result['distinct_initial_prompts_by_condition']=={'general_review':1}
    assert sum(r['calls_with_missing_usage'] for r in result['rows'])==1
    assert result['effectiveness_conclusion'] is None
    with pytest.raises(ValueError,match='Duplicate'):summarize(dataset_path,runs+[runs[0]])
    (runs[0]/'general_review-plan-observation.json').write_text('{}')
    with pytest.raises(ValueError,match='Observation digest mismatch'):summarize(dataset_path,runs)
