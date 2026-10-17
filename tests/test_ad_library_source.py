import json
import httpx
import pytest
from harness.models.reference_sources.dandad import discover_films,classify


def test_cumulative_archive_pages_are_sliced_without_duplicates():
    def respond(req):
        page=int(req.url.params['page'])
        data={'filters':{'categories':{'value':['film']},'years':{'value':[2025]}},'pageInfo':{'page':page},'total':41,'totalPages':4,'edges':[{'node':{'url':'/work/d-ad-awards-archive/item-'+str(i)}} for i in range(min(41,page*12))]}
        return httpx.Response(200,text='<script id="props" type="application/json">'+json.dumps({'data':{'page':{'items':data}}})+'</script>')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        pages=[discover_films(client,2025,p)[0] for p in range(1,5)]
    assert list(map(len,pages))==[12,12,12,5]
    assert len(set(sum(pages,[])))==41
    assert classify(['Film / TV/VOD Commercials 16-180 Seconds'])=='电视/点播广告'


@pytest.mark.parametrize('failure',[None,'duplicate_page','wrong_year','wrong_category','robots'])
def test_deep_page_uses_public_listing_and_rejects_invalid_results(failure):
    calls=[]
    def respond(req):
        calls.append(req.url.path)
        if req.url.path=='/robots.txt':
            return httpx.Response(200,text='User-agent: *\nDisallow: /api/\n' if failure=='robots' else '')
        if '/api/v1/listings/' in req.url.path:
            assert req.url.params['page']=='6' and req.url.params['years']=='2018'
            first=0 if failure=='duplicate_page' else 60
            edges=[{'node':{'url':'/work/d-ad-awards-archive/item-'+str(i),'year':2017 if failure=='wrong_year' else 2018,'associatedWorkCategories':[{'name':'Design' if failure=='wrong_category' else 'Film'}]}} for i in range(first,first+12)]
            return httpx.Response(200,json={'items':edges,'totalItems':91,'totalPages':8})
        data={'filters':{'categories':{'value':['film']},'years':{'value':[2018]}},'pageInfo':{'page':1},'total':91,'totalPages':8,'edges':[{'node':{'url':'/work/d-ad-awards-archive/item-'+str(i)}} for i in range(12)]}
        return httpx.Response(200,text='<script id="props" type="application/json">'+json.dumps({'data':{'page':{'items':data}}})+'</script>')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        if failure:
            with pytest.raises(ValueError):discover_films(client,2018,6)
        else:
            links,pages=discover_films(client,2018,6)
            assert len(links)==12 and links[0].endswith('item-60') and pages==8
    if failure=='robots':assert len(calls)==2


def test_primary_film_category_survives_bounded_metadata_without_people():
    from harness.models.reference_sources.dandad import parse
    categories=['Art Direction / Digital']*8+['Film / TV/VOD Commercials 16-180 Seconds']
    page={'title':'Example','year':2025,'credits':{'edges':[{'node':{'role':'Brand','name':'Example brand'}},{'node':{'role':'Director','name':'Private person'}}]},'assets':[{'media':{'externalVideo':{'url':'https://media.dandad.org/example.m3u8'}}}], 'awards':{'edges':[{'node':{'awardType':'SHORTLIST','entryCategory':{'name':c}}} for c in categories]}}
    result=parse('<script id="props" type="application/json">'+json.dumps({'data':{'page':page}})+'</script>','https://www.dandad.org/work/d-ad-awards-archive/example')
    assert classify(result['tags'])==result['ad_type']=='电视/点播广告'
    assert 'Private person' not in json.dumps(result)
    page['loginRequired']=True
    assert parse('<script id="props" type="application/json">'+json.dumps({'data':{'page':page}})+'</script>','https://www.dandad.org/example') is None


def test_legacy_tv_cinema_categories_are_advertising_not_generic_references():
    assert classify(['TV & Cinema Advertising / TV Commercials 21-40 seconds']) == '电视/影院广告'
    assert classify(['TV & Cinema Advertising / TV Commercial Campaigns']) == '电视/影院广告'
    assert classify(['Film / TV/VOD Commercials 16-180 Seconds']) == '电视/点播广告'
    assert classify(['Music Videos / TV & Cinema Advertising inspired']) == '音乐影像参考'
