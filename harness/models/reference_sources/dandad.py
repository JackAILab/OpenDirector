"""Public D&AD annual/archive pages; keep only bounded reference metadata."""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser
import httpx

ORIGIN='https://www.dandad.org'

class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        value=dict(attrs).get('href','')
        if tag=='a' and re.fullmatch(r'/work/d-ad-awards-archive/[a-z0-9-]+',value):
            if value not in self.links:self.links.append(value)


def discover(client):
    response=client.get(ORIGIN+'/work/annual');response.raise_for_status()
    parser=Links();parser.feed(response.text)
    if not parser.links:raise ValueError('source_layout_changed')
    return [urljoin(ORIGIN,p) for p in parser.links]


def parse(html,url):
    match=re.search(r'<script id="props" type="application/json">(.*?)</script>',html,re.S)
    if not match:raise ValueError('source_layout_changed')
    page=json.loads(match[1])['data']['page']
    if page.get('loginRequired'):return None
    video=None
    for asset in page.get('assets',[]):
        media=asset.get('media') or {}
        v=media.get('externalVideo') or media.get('video')
        if v and v.get('url'):video=v;break
    if not video:return None
    awards=[e['node'] for e in page.get('awards',{}).get('edges',[])]
    if not awards:return None
    brand=next((e['node']['name'] for e in page.get('credits',{}).get('edges',[]) if e['node'].get('role')=='Brand'),'')
    categories=[a.get('entryCategory',{}).get('name','') for a in awards]
    ad_type=classify(categories)
    poster=video.get('posterImage') or {}
    evidence=[{'kind':'award_archive','text':str(page.get('year',''))+' D&AD · '+a.get('awardType','')+' · '+a.get('entryCategory',{}).get('name',''),'source_url':url} for a in awards[:8]]
    industries={'disney':'娱乐文旅','spotify':'科技互联网','nike':'运动服饰','lego':'玩具与家庭','stella artois':'食品饮料','squarespace':'科技互联网','apple':'科技互联网','new balance':'运动服饰','adidas':'运动服饰','uber':'出行服务','burberry':'奢侈时尚','telstra':'通信服务','frontline19':'公益健康','ikea':'家居生活'}
    return {'source_url':url,'title':page['title'][:300],'brand':brand,'source_name':'D&AD 官方奖项档案',
            'industry':industries.get(brand.lower(),'待分类'),'ad_type':ad_type,'published':str(page.get('year','')),
            'summary':'具有可核查的官方奖项记录。当前分类依据奖项类别；具体广告策略、镜头节奏与声音表现等待观看和人工标注。',
            'quality_evidence':evidence,'thumbnail_url':poster.get('psrc') or poster.get('url') or '',
            'media_url':video['url'],'media_status':'source_link','media_role':'work_or_case_film_unverified','rights':'reference_only; redistribution_and_training_not_verified',
            'tags':sorted(categories,key=lambda c:not c.lower().startswith('film /'))[:8]}


def fetch(client,url):
    if urlsplit(url).hostname!='www.dandad.org':raise ValueError('unsupported_source')
    response=client.get(url);response.raise_for_status()
    return parse(response.text,url)


def discover_films(client,year,page_number):
    url=ORIGIN+f'/work/d-ad-awards-archive?years={int(year)}&categories=film&page={int(page_number)}'
    response=client.get(url);response.raise_for_status()
    match=re.search(r'<script id="props" type="application/json">(.*?)</script>',response.text,re.S)
    if not match:raise ValueError('source_layout_changed')
    items=json.loads(match[1])['data']['page']['items']
    if (items.get('filters',{}).get('categories',{}).get('value')!=['film'] or
        items.get('filters',{}).get('years',{}).get('value')!=[int(year)]):
        raise ValueError('source_layout_changed')
    # Deep HTML pages may render page 1. Use the same public listing endpoint
    # as the site's Load More control, while checking each item's year/category.
    if int(page_number)>1 and items.get('pageInfo',{}).get('page')==1:
        return discover_film_listing(client,year,page_number,items)
    # This archive returns cumulative edges (12, 24, 36...), not isolated pages.
    # Fail visibly if that contract changes; never pin the crawler on a >limit page.
    if items.get('pageInfo',{}).get('page')!=int(page_number):raise ValueError('source_layout_changed')
    if len(items['edges'])!=min(items['total'],int(page_number)*12):raise ValueError('source_layout_changed')
    edges=items['edges'][(int(page_number)-1)*12:]
    links=[urljoin(ORIGIN,e['node']['url']) for e in edges]
    return links,max(1,items['totalPages'])


def discover_film_listing(client,year,page_number,first_page):
    if (len(first_page['edges'])!=min(12,first_page['total']) or
        not 1<int(page_number)<=first_page['totalPages']):
        raise ValueError('source_layout_changed')
    api=ORIGIN+'/api/v1/listings/work%2Fd-ad-awards-archive'
    robots=client.get(ORIGIN+'/robots.txt')
    if robots.status_code not in (200,404):raise ValueError('robots_unavailable')
    policy=RobotFileParser();policy.parse(robots.text.splitlines() if robots.status_code==200 else [])
    if robots.status_code==200 and not policy.can_fetch('VisualAgent-ReferenceCollector',api):
        raise ValueError('robots_disallowed')
    response=client.get(api,params={'years':int(year),'categories':'film','page':int(page_number)})
    response.raise_for_status();result=response.json();edges=result.get('items',[])
    expected=min(12,first_page['total']-(int(page_number)-1)*12)
    if (result.get('totalItems')!=first_page['total'] or
        result.get('totalPages')!=first_page['totalPages'] or len(edges)!=expected):
        raise ValueError('source_layout_changed')
    links=[];first={e['node']['url'] for e in first_page['edges']}
    for edge in edges:
        node=edge['node'];path=node.get('url','')
        if (node.get('year')!=int(year) or
            not any(c.get('name')=='Film' for c in node.get('associatedWorkCategories',[])) or
            not re.fullmatch(r'/work/d-ad-awards-archive/[a-z0-9-]+',path) or path in first):
            raise ValueError('source_layout_changed')
        links.append(urljoin(ORIGIN,path))
    if len(set(links))!=len(links):raise ValueError('source_layout_changed')
    return links,max(1,result['totalPages'])


def classify(categories):
    film=next((c.lower() for c in categories if c.lower().startswith('film /')),'')
    if film:
        for key,label in (('social','社交媒体广告'),('tv/vod','电视/点播广告'),('television','电视广告'),('cinema','影院广告'),('online','网络广告'),('tactical','即时营销广告')):
            if key in film:return label
        return '品牌广告影片'
    # Older award archives use a distinct category family; do not infer from titles.
    if any(c.lower().startswith('tv & cinema advertising /') for c in categories):
        return '电视/影院广告'
    text=' '.join(categories).lower()
    if 'music video' in text:return '音乐影像参考'
    if 'animation' in text:return '动画影像参考'
    return '品牌视觉参考'
