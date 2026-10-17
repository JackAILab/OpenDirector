from harness.library.mechanisms import annotate, classify


def test_mechanism_labels_are_bounded_and_explainable():
    labels=classify('极端环境制造压力，人物误判后反转，最后品牌落版')
    assert labels[:3]==['pressure_test','misdirection_reveal','contrast_reversal']
    assert len(labels)<=5


def test_annotation_does_not_mutate_candidate():
    original={'principle':'把功能变成可见动作','mechanism':'人物完成任务'}
    result=annotate(original)
    assert 'mechanism_tags' not in original
    assert 'observable_task' in result['mechanism_tags']
    assert result['shooting_grammar']['schema']=='visualagent.sampled-shooting-grammar.v1'
    assert result['shooting_grammar']['windows']==[]


def test_shooting_grammar_labels_sampled_windows_without_claiming_exact_cuts():
    from harness.library.mechanisms import shooting_grammar
    result=shooting_grammar({'beats':[
        {'start':5,'end':8,'purpose':'结果','observation':'b'},
        {'start':0,'end':3,'purpose':'建立注意','observation':'a'},
    ]})
    assert [w['role'] for w in result['windows']]==['hook','proof_or_reframe']
    assert result['evidence_type']=='timecoded_sampled_windows'
    assert '精确剪辑点' in result['warning']


def test_position_does_not_invent_role_and_invalid_times_are_omitted():
    from harness.library.mechanisms import shooting_grammar
    grammar=shooting_grammar({'beats':[
        {'start':0,'end':2,'purpose':'无法判断'},
        {'start':2,'end':float('inf'),'purpose':'结尾'},
        {'start':-1,'end':1,'purpose':'注意'},
    ]})
    assert len(grammar['windows'])==1
    assert grammar['windows'][0]['role']=='unknown'
