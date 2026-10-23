"""Canvas ownership, plan invalidation, and real director reference flow."""
import io
import pytest
from PIL import Image
from harness.tools.creative_canvas import validate_graph, director_inputs
from harness.studio import store
from test_creative_studio import client, ready


def graph(revision, text='展示产品细节', x=30):
    return {'revision':revision,'nodes':[{'id':'note','kind':'text','text':text,'label':'产品要求','x':x,'y':40}], 'edges':[{'source':'note','target':'director'}]}


def test_connected_change_invalidates_paid_plan_and_stale_save_fails(client):
    p=ready(client);url='/creative/api/projects/'+p['id']
    result=client.put(url+'/canvas',json=graph(p['revision']))
    assert result.status_code==200
    p=result.json();assert p['state']=='intake' and p['shots']==[]
    assert client.post(url+'/execute',json={'revision':p['revision'],'approved_credits':6}).status_code==409
    assert client.put(url+'/canvas',json=graph(p['revision']-1)).status_code==409
    assert client.put(url+'/canvas',json=graph(p['revision']),headers={'Authorization':'Bearer two'}).status_code==404


def test_layout_change_keeps_approved_plan(client):
    p=ready(client);url='/creative/api/projects/'+p['id']
    p=client.put(url+'/canvas',json=graph(p['revision'])).json()
    p=client.post(url+'/message',json={'revision':p['revision'],'mode':'plan'}).json()
    r=client.put(url+'/canvas',json=graph(p['revision'],x=900))
    assert r.status_code==200 and r.json()['state']=='ready' and len(r.json()['shots'])==3


def test_upload_private_reference_and_director_consumes_only_connected(client):
    p=ready(client);url='/creative/api/projects/'+p['id']
    raw=io.BytesIO();Image.new('RGB',(240,180),'red').save(raw,format='PNG')
    r=client.post(url+'/canvas/assets',params={'kind':'image','revision':p['revision']},content=raw.getvalue())
    assert r.status_code==200
    p=r.json()['project'];asset=r.json()['asset']
    assert client.get(url+'/canvas/assets/'+asset['id']+'/preview').status_code==200
    assert client.get(url+'/canvas/assets/'+asset['id']+'/source',headers={'Authorization':'Bearer two'}).status_code==404
    g={'revision':p['revision'],'nodes':[{'id':'photo','kind':'image','asset':asset['id'],'text':'色调参考','label':'红色'}],'edges':[]}
    p=client.put(url+'/canvas',json=g).json()
    assert director_inputs(p)==([],[])
    g['revision']=p['revision'];g['edges']=[{'source':'photo','target':'director'}]
    p=client.put(url+'/canvas',json=g).json()
    notes,images=director_inputs(p)
    assert notes[0]['instruction']=='色调参考'
    assert images[1]['image_url']['url'].startswith('data:image/jpeg;base64,')
    assert all('红色' not in str(e) for e in p['events'])


def test_graph_rejects_foreign_assets_cycles_and_duplicate_edges():
    with pytest.raises(ValueError): validate_graph({'nodes':[{'id':'a','kind':'image','asset':'foreign'}]}, {})
    with pytest.raises(ValueError): validate_graph({'nodes':[{'id':'a','kind':'text'}],'edges':[{'source':'a','target':'a'}]}, {})
    with pytest.raises(ValueError): validate_graph({'nodes':[{'id':'a','kind':'text'}],'edges':[{'source':'a','target':'director'}]*2}, {})


def test_video_reference_is_decoded_to_real_frames(client,tmp_path,monkeypatch):
    import subprocess
    from pathlib import Path
    ffmpeg=Path('/opt/visualstation/creative-runtime/bin/ffmpeg')
    ffprobe=Path('/opt/visualstation/creative-runtime/bin/ffprobe')
    if not ffmpeg.exists():pytest.skip('media runtime unavailable')
    monkeypatch.setenv('CREATIVE_FFMPEG',str(ffmpeg));monkeypatch.setenv('CREATIVE_FFPROBE',str(ffprobe))
    clip=tmp_path/'fixture.mp4'
    subprocess.run([str(ffmpeg),'-v','error','-f','lavfi','-i','color=c=blue:s=320x180:r=12','-t','1','-c:v','libx264','-threads','1',str(clip)],check=True)
    p=ready(client);url='/creative/api/projects/'+p['id']
    response=client.post(url+'/canvas/assets',params={'kind':'video','revision':p['revision']},content=clip.read_bytes())
    assert response.status_code==200,response.text
    asset=response.json()['asset'];assert asset['frames']==3 and asset['duration']==1
    assert client.get(url+'/canvas/assets/'+asset['id']+'/metadata').json()=={'kind':'video','width':320,'height':180,'duration':1.0,'has_audio':False,'can_extract_frame':True,'frame_positions':['current','first','last']}
    preview=client.get(url+'/canvas/assets/'+asset['id']+'/preview')
    assert preview.status_code==200 and Image.open(io.BytesIO(preview.content)).width>0
    assert client.post(url+'/canvas/assets',params={'kind':'video','revision':response.json()['project']['revision']},content=b'not a video').status_code==422


def test_lineage_comes_from_owned_production_and_recovers_deleted_parent():
    from harness.tools.canvas_lineage import lineage, derivation_edges
    p={'canvas_assets':{'a':{'kind':'image'},'b':{'kind':'image'},'c':{'kind':'image','provenance':{'kind':'image_edit','sources':['b','foreign']}}},
       'image_attempts':[{'state':'completed','asset':'b','source_asset':'a'}, {'state':'failed','asset':'a','source_asset':'c'}]}
    records=lineage(p)
    assert records['b']=={'kind':'image_edit','sources':['a']}
    assert records['c']['sources']==['b'] and records['a']['sources']==[]
    g={'nodes':[{'id':'one','asset':'a'},{'id':'two','asset':'b'},{'id':'three','asset':'c'}]}
    assert derivation_edges(g,records)==[{'source':'one','target':'two','kind':'derived'},{'source':'two','target':'three','kind':'derived'}]
    g['nodes'].pop(0)
    assert len(derivation_edges(g,records))==1 and records['b']['sources']==['a']


def test_layout_orders_roles_and_ancestry_without_overlap_or_mutating_graph():
    from harness.tools.canvas_lineage import arrange
    g={'nodes':[{'id':'scene','kind':'image','asset':'s','role':'scene','x':4,'y':5},
                {'id':'variant','kind':'image','asset':'v','role':'product','x':4,'y':5},
                {'id':'product','kind':'image','asset':'p','role':'product','x':4,'y':5}], 'edges':[]}
    records={'v':{'sources':['p']}}
    laid=arrange(g,records,{'product':710,'scene':500,'variant':900})
    pos={n['id']:n for n in laid['nodes']}
    assert pos['product']['x']<pos['variant']['x']
    assert pos['product']['y']+710<pos['scene']['y']
    assert g['nodes'][0]['x']==4 and g['nodes'][0]['y']==5
    assert arrange(g,records,{'product':710,'scene':500,'variant':900})==laid
    crowded={'nodes':[dict(id=str(i),asset=str(i),role='reference',kind='image') for i in range(16)],'edges':[]}
    crowded=arrange(crowded,{}, {str(i):1800 for i in range(16)})
    for i,a in enumerate(crowded['nodes']):
        assert -10000<a['x']<10000 and 0<=a['y']<10000
        for b in crowded['nodes'][i+1:]:assert abs(a['x']-b['x'])>=300 or abs(a['y']-b['y'])>=1800
    with pytest.raises(ValueError):arrange(g,records,{'product':float('nan')})
    with pytest.raises(ValueError):arrange(g,{'p':{'sources':['v']},'v':{'sources':['p']}})


def test_generated_result_auto_layout_preserves_hand_placed_nodes():
    from harness.tools.canvas_lineage import auto_place_generated_node
    g={'nodes':[{'id':'product','kind':'image','asset':'p','role':'product','x':40,'y':30},
                {'id':'note','kind':'text','role':'story','x':40,'y':950},
                {'id':'generated','kind':'image','asset':'g','role':'product','x':40,'y':30}], 'edges':[]}
    records={'g':{'sources':['p']}}
    laid=auto_place_generated_node(g,records,'generated',{'product':780,'note':450,'generated':780})
    positions={n['id']:(n.get('x'),n.get('y')) for n in laid['nodes']}
    assert positions['product']==(40,30)
    assert positions['note']==(40,950)
    assert positions['generated']!=(40,30)
    assert auto_place_generated_node(g,records,'generated',{'product':780,'note':450,'generated':780})==laid


def test_layout_api_is_preview_only_private_and_preserves_plan(client):
    p=ready(client);url='/creative/api/projects/'+p['id']
    p=client.put(url+'/canvas',json=graph(p['revision'])).json()
    p=client.post(url+'/message',json={'revision':p['revision'],'mode':'plan'}).json()
    body={**p['canvas'],'revision':p['revision'],'sizes':{'note':320}}
    r=client.post(url+'/canvas/layout',json=body)
    assert r.status_code==200 and r.json()['canvas']['nodes'][0]['x']==40
    after=client.get(url).json();assert after['revision']==p['revision'] and after['state']=='ready' and after['canvas']==p['canvas']
    saved=client.put(url+'/canvas',json={'revision':p['revision'],**r.json()['canvas']}).json()
    assert saved['state']=='ready' and saved['shots']==p['shots']
    assert client.post(url+'/canvas/layout',json=body).status_code==409
    assert client.post(url+'/canvas/layout',json=body,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.post(url+'/canvas/layout',json={**body,'revision':saved['revision'],'sizes':{'note':9000}}).status_code==422


def test_roles_are_director_inputs_but_provenance_cannot_be_forged(client):
    p=ready(client);url='/creative/api/projects/'+p['id'];g=graph(p['revision'])
    g['nodes'][0]['role']='product';g['nodes'][0]['provenance']={'sources':['fake']}
    p=client.put(url+'/canvas',json=g).json()
    assert p['canvas']['nodes'][0]['role']=='product' and 'provenance' not in p['canvas']['nodes'][0]
    notes,_=director_inputs(p);assert notes[0]['role']=='product'
    p=client.post(url+'/message',json={'revision':p['revision'],'mode':'plan'}).json()
    g['revision']=p['revision'];g['nodes'][0]['role']='scene'
    p=client.put(url+'/canvas',json=g).json();assert p['state']=='intake'
    g['revision']=p['revision'];g['nodes'][0]['role']='admin'
    assert client.put(url+'/canvas',json=g).status_code==422


def test_owned_product_handoff_records_source_and_normal_upload_clears_it(client):
    p=client.post('/creative/api/projects',json={'message':'测试商品','aspect':'1:1'}).json();url='/creative/api/projects/'+p['id']
    raw=io.BytesIO();Image.new('RGB',(256,256),'blue').save(raw,'PNG')
    data=client.post(url+'/canvas/assets',params={'revision':p['revision'],'kind':'image'},content=raw.getvalue()).json()
    aid=data['asset']['id'];p=data['project']
    r=client.post(url+'/reference',params={'revision':p['revision'],'source_asset':aid});assert r.status_code==200
    p=r.json();assert p['reference']['source_asset']==aid
    assert client.post(url+'/reference',params={'revision':p['revision'],'source_asset':'f'*32}).status_code==422
    assert client.post(url+'/reference',params={'revision':p['revision'],'source_asset':aid},headers={'Authorization':'Bearer two'}).status_code==404
    p=client.post(url+'/reference',params={'revision':p['revision']},content=raw.getvalue()).json()
    assert 'source_asset' not in p['reference']


def test_saved_groups_preserve_plan_inputs_and_layout(client):
    from harness.tools.creative_canvas import input_signature
    p=ready(client);url='/creative/api/projects/'+p['id']
    g=graph(p['revision']);g['nodes'].append({'id':'second','kind':'text','label':'另一素材','text':'构图','x':400,'y':40})
    p=client.put(url+'/canvas',json=g).json()
    p=client.post(url+'/message',json={'revision':p['revision'],'mode':'plan'}).json()
    before=p['canvas'];shots=p['shots'];g={**before,'revision':p['revision'],'groups':[{'id':'group1','name':' 商品与场景 ','members':['note','second']}]}
    r=client.put(url+'/canvas',json=g);assert r.status_code==200,r.text
    saved=r.json();assert saved['canvas_capabilities']['groups'] is True
    assert saved['state']=='ready' and saved['shots']==shots
    assert input_signature(saved['canvas'])==input_signature(before)
    assert director_inputs(saved)==director_inputs(p)
    assert saved['canvas']['groups']==[{'id':'group1','name':'商品与场景','members':['note','second']}]
    assert client.get(url).json()['canvas']['groups']==saved['canvas']['groups']
    layout=client.post(url+'/canvas/layout',json={'revision':saved['revision'],**saved['canvas']})
    assert layout.status_code==200 and layout.json()['canvas']['groups']==saved['canvas']['groups']
    assert store.load(p['id'],1)['canvas']==saved['canvas']
    assert client.put(url+'/canvas',json=g).status_code==409
    assert client.put(url+'/canvas',json={**g,'revision':saved['revision']},headers={'Authorization':'Bearer two'}).status_code==404
    r=client.put(url+'/canvas',json={'revision':saved['revision'],**saved['canvas'],'groups':[]})
    assert r.status_code==200 and 'groups' not in r.json()['canvas']
    assert r.json()['shots']==shots and r.json()['training_eligible'] is False


@pytest.mark.parametrize('groups', [
    None, {}, [{'id':'bad id','name':'组','members':['a','b']}],
    [{'id':'g','name':' ','members':['a','b']}],
    [{'id':'g','name':'x'*61,'members':['a','b']}],
    [{'id':'g','name':'组','members':['a']}],
    [{'id':'g','name':'组','members':['a','a']}],
    [{'id':'g','name':'组','members':['a','director']}],
    [{'id':'g','name':'组','members':['a',{}]}],
    [{'id':'g','name':'组','members':['a','b']},{'id':'other','name':'组','members':['b','c']}],
    [{'id':'g','name':'组','members':['a','b']},{'id':'g','name':'组','members':['c','d']}],
])
def test_groups_reject_invalid_or_overlapping_members(groups):
    with pytest.raises(ValueError):
        validate_graph({'nodes':[{'id':v,'kind':'text'} for v in 'abcd'],'groups':groups},{})


def test_source_metadata_uses_preserved_pixels_and_is_owned_read_only(client):
    p=ready(client);url='/creative/api/projects/'+p['id']
    raw=io.BytesIO();Image.new('RGB',(1200,1800),'navy').save(raw,format='PNG')
    uploaded=client.post(url+'/canvas/assets',params={'kind':'image','revision':p['revision']},content=raw.getvalue()).json()
    aid=uploaded['asset']['id'];endpoint=url+'/canvas/assets/'+aid
    before=store.load(p['id'],1)
    assert Image.open(io.BytesIO(client.get(endpoint+'/preview').content)).size==(640,960)
    assert client.get(endpoint+'/metadata').json()=={'kind':'image','width':1200,'height':1800,'can_extract_frame':False,'frame_positions':[]}
    assert client.get(endpoint+'/metadata',headers={'Authorization':'Bearer two'}).status_code==404
    assert client.get(url+'/canvas/assets/'+'a'*32+'/metadata').status_code==404
    assert store.load(p['id'],1)==before
    # The cache must follow actual source replacement, including pixel normalization.
    from harness.tools.creative_canvas import asset_directory
    source=asset_directory(before,aid)/uploaded['asset']['filename']
    Image.new('RGB',(1800,1200),'red').save(source)
    assert client.get(endpoint+'/metadata').json()['width']==1800
    source.write_bytes(b'broken image')
    response=client.get(endpoint+'/metadata')
    assert response.status_code==422 and str(source) not in response.text


def test_generated_variants_pack_beside_moved_source_without_reflow():
    from harness.tools.canvas_lineage import auto_place_generated_node
    g={'nodes':[{'id':'source','kind':'image','asset':'s','x':1100,'y':500},
                {'id':'first','kind':'image','asset':'v1','x':1410,'y':500},
                {'id':'second','kind':'image','asset':'v2','x':0,'y':0}], 'edges':[]}
    records={'v1':{'sources':['s']},'v2':{'sources':['s']}}
    laid=auto_place_generated_node(g,records,'second')
    assert laid['nodes'][:2]==g['nodes'][:2]
    assert laid['nodes'][2]['x']==1410
    assert laid['nodes'][2]['y']==954  # 400px media footprint + 54px gap
    assert g['nodes'][2]['x']==0 and g['nodes'][2]['y']==0
    measured=auto_place_generated_node(g,records,'second',{'source':180,'first':180,'second':180})
    assert measured['nodes'][2]['x']==1410 and measured['nodes'][2]['y']==734
    tall=auto_place_generated_node(g,records,'second',{'source':180,'first':1200,'second':180})
    assert tall['nodes'][2]['y']>=1754
