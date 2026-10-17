"""Mute is independent of gain and protected from automatic edit proposals."""
import copy
import pytest
from harness.tools.creative_edit import validate_edit
from harness.tools.creative_edit_review import build_review
from harness.evaluators.creative_edit import evaluate_edit_proposal

CATALOG={'v':dict(sha256='hash',duration=3,kind='video',has_audio=True,width=320,height=180)}


def document():
    return dict(sources={'v':'hash'},clips=[dict(source='v',start=0,end=3,gain=.6)],
                audio=[dict(source='v',start=0,end=3,at=0,gain=.3,fade_in=.2,fade_out=.3)],captions=[])


def test_mute_preserves_gain_envelope_and_legacy_defaults():
    raw=document(); clean=validate_edit(raw,catalog=CATALOG)
    assert clean['clips'][0]['muted'] is False and clean['audio'][0]['muted'] is False
    for kind in ('clips','audio'):raw[kind][0]['muted']=True
    muted=validate_edit(raw,catalog=CATALOG)
    for kind in ('clips','audio'):
        assert muted[kind][0]['muted'] is True
        assert {k:v for k,v in muted[kind][0].items() if k!='muted'}=={k:v for k,v in clean[kind][0].items() if k!='muted'}
    assert build_review(muted,CATALOG,'16:9')['technical']['audio_track']['status']!='passed'
    muted['audio'][0]['muted']=False
    assert build_review(muted,CATALOG,'16:9')['technical']['audio_track']['status']=='passed'


@pytest.mark.parametrize('kind',['clips','audio'])
@pytest.mark.parametrize('value',['false',1,None,[],{}])
def test_mute_requires_explicit_boolean(kind,value):
    raw=document();raw[kind][0]['muted']=value
    with pytest.raises(ValueError,match='静音'):validate_edit(raw,catalog=CATALOG)


@pytest.mark.parametrize('kind',['clips','audio'])
def test_agent_cannot_unmute_user_choice(kind):
    raw=document();raw[kind][0]['muted']=True
    original=validate_edit(raw,catalog=CATALOG)
    proposal=dict(spec=copy.deepcopy(original),summary='保留选择',reasons=[dict(text='首帧',frames=['frame_1'])])
    frames=[dict(id='frame_1',source='v',time=0)]
    assert evaluate_edit_proposal(proposal,original,CATALOG,frames)['qa']['training_eligible'] is False
    proposal['spec'][kind][0]['muted']=False
    with pytest.raises(ValueError):evaluate_edit_proposal(proposal,original,CATALOG,frames)
