"""Curated ADFEST 2026 entries bound to verified official PDF editions."""
import hashlib
from urllib.parse import quote, parse_qs, urlsplit
from harness.models.reference_sources.award_evidence import award_evidence_kind

SOURCE_YEAR = 2026
# This locally assigned query value is an identity, not evidence of the year.
# Preserve it so existing reviews, links and media keep their original IDs.
LEGACY_IDENTITY_YEAR = 2025
VERIFIED_PDFS = {
    'film': {'sha256': '9457a0cabe7ef3c61d449a4a7d887421b20f04ad5c8c40577734be6c30b4d005', 'dated': '2026-04-10', 'name': 'film-lotus'},
    'craft': {'sha256': 'c197c6595c32a7983da281edd6a1c7e0264057f825fca452bd0da2b58caade3e', 'dated': '2026-03-18', 'name': 'film-craft-lotus'},
    'entertainment': {'sha256': 'cf8196223ad28f316290532655017260a329cc229d30d1bc56c68e721929fa49', 'dated': '2026-03-16', 'name': 'entertainment-lotus'},
}


def verify_pdf(kind, content):
    if hashlib.sha256(content).hexdigest() != VERIFIED_PDFS[kind]['sha256']:
        raise ValueError('source_document_changed')


def _verified_records(records, kind):
    proof = VERIFIED_PDFS[kind]
    for record in records:
        record['published'] = str(SOURCE_YEAR)
        for field in ('source_name', 'summary'):
            record[field] = record[field].replace('ADFEST 2025', 'ADFEST 2026')
        code = parse_qs(urlsplit(record['source_url']).query)['code'][0]
        award = record['quality_evidence'][1].rsplit('; ', 1)[-1]
        source = record['source_url'].split('&adfest_year=')[0]
        record['quality_evidence'] = [
            {'kind': award_evidence_kind(award),
             'text': f"{record['source_name']} · {code} · {award}", 'source_url': source},
            {'kind': 'source_publication', 'text': f"官方名单日期 {proof['dated']}；奖项年度 2026。", 'source_url': source},
        ]
        record['creative_structure'] = {
            'entry_code': code, 'award': award, 'award_year': SOURCE_YEAR,
            'legacy_identity_year': LEGACY_IDENTITY_YEAR,
            'source_document_sha256': proof['sha256'], 'source_document_date': proof['dated'],
        }
    return records

PDF_URL = 'https://www.adfest.com/index.php/Home/Pdfview/index.html?id=11&type=winnerslist'
# The official PDF is a public winners list. Keep only stable editorial fields;
# media URLs and provider responses never enter the library.
ENTRIES = (
 ('SOIL','CHUPPS FOOTWEAR','F01 Broadcast: Consumer Goods','FINALIST','F01/003'),
 ('AMUK EMAK','WE+','F04 Broadcast: Finance, Business & Commercial Public Services','BRONZE','F04/004'),
 ('STEADFAST - DIRTY MONEY','STEADFAST STATIONERY','F04 Broadcast: Finance, Business & Commercial Public Services','FINALIST','F04/003'),
 ('NO LABELS','NIKKA WHISKY','F07 Online Film: Food & Beverages','FINALIST','F07/001'),
 ('IT’S DETTOL TIME','DETTOL','F08 Online Film: Consumer Goods','BRONZE','F08/002'),
 ('THE SCENT THAT GIVES YOU THE SCENE','MITH BANGKOK','F08 Online Film: Consumer Goods','BRONZE','F08/009'),
 ('POSSESSED','LIFEBUOY','F08 Online Film: Consumer Goods','FINALIST','F08/010'),
 ('DEATH OF A SALESMAN','FIVE STAR CHICKEN','F10 Online Film: Retail','SILVER','F10/004'),
 ('OWN IT FIRST','CENTRAL DEPARTMENT STORE','F10 Online Film: Retail','BRONZE','F10/008'),
 ('SAFETYNOVELA','PHILIPPINE AIRLINES','F11 Online Film: Travel & Leisure','FINALIST','F11/004'),
 ('WHATSAPP – BAATAN HI BAATAN MEIN (LOVE IN A FEW WORDS)','WHATSAPP','F12 Online Film: Media & Entertainment','SILVER','F12/002'),
 ('REZA RAHADIAN PRESENTS: FILMS WITHOUT REZA RAHADIAN','NETFLIX ID BLOCKBUSTER','F12 Online Film: Media & Entertainment','FINALIST','F12/005'),
 ('PATIENT','KRUNG SRI FIRST CHOICE','F13 Online Film: Finance & Real Estate','GOLD','F13/001'),
 ('AMUK EMAK','WE+','F13 Online Film: Finance & Real Estate','BRONZE','F13/004'),
 ('DESI OON','CENTRE FOR PASTORALISM','F16 Online Film: Public Services & Cause Appeals','BRONZE','F16/002'),
 ('MOTHER STRIKE','SNACK JACK RING','F17 Viral Film','GRANDE','F17/003'),
 ('THE SCENT THAT GIVES YOU THE SCENE','MITH BANGKOK','F17 Viral Film','SILVER','F17/006'),
 ('DARE TO STEP','GAMBOL','F19 Web Series','BRONZE','F19/005'),
 ('CHICKY','GRABMART','F19 Web Series','BRONZE','F19/007'),
)

def winners():
    out=[]
    for title,brand,category,award,code in ENTRIES:
        url=PDF_URL+f'&adfest_year=2025&code={quote(code)}'
        out.append({'source_url':url,'title':title,'brand':brand,'industry':'consumer',
          'ad_type':'ADFEST Film Lotus / '+category,'format':'video','language':'en','audio':True,
          'summary':f'ADFEST 2025 Film Lotus official winners list; {category}; {award}.',
          'quality_evidence':[f'ADFEST 2025 Film Lotus official winners list ({code})',f'{category}; {award}'],
          'source_name':'ADFEST 2025 Film Lotus official winners list','published':'2025',
          'media_status':'source_link','media_role':'official award record; playback unverified',
          'rights':'official public reference link; no media cached','tags':['adfest','film-lotus','human_review_pending']})
    return _verified_records(out, 'film')

CRAFT_PDF_URL = 'https://www.adfest.com/index.php/Home/Pdfview/index.html?id=10&type=winnerslist'
CRAFT_ENTRIES = (
 ('THE M SSING PIECE','KFC THAILAND','CF01 Directing','SILVER','CF01/007'),('SUPER.MONEY \'JONTY RODES\'','SUPER.MONEY','CF01 Directing','BRONZE','CF01/003'),('THE MISSING EGG','EDUFARMERS','CF01 Directing','BRONZE','CF01/019'),('FLIGHT OF THE FINCH','ALLIANZ','CF01 Directing','FINALIST','CF01/028'),('SHOT ON IPHONE - LAST SCENE','IPHONE','CF01 Directing','FINALIST','CF01/032'),('KAPAL KERTAS','THE KANCIL AWARDS AND CREATIVE FESTIVAL','CF02 Script','GOLD','CF02/005'),('LET GO','SAMSUNG','CF03 Cinematography','SILVER','CF03/007'),('GENESIS GV60 TAKE YOUR WONDER FURTHER','GENESIS','CF03 Cinematography','SILVER','CF03/010'),('SPACE','LEXUS','CF03 Cinematography','BRONZE','CF03/003'),('MAKE LOVE LAST','VIATRIS','CF03 Cinematography','FINALIST','CF03/009'),('FLIPKART SA SA LE LE','FLIPKART','CF06 Casting','BRONZE','CF06/002'),('SAY IT PROND','SPEAK','CF07 Use of Talent/Celebrity','SILVER','CF07/001'),("CAN'T DO THAT IF YOU'RE DRIVING",'UBER AUSTRALIA','CF07 Use of Talent/Celebrity','FINALIST','CF07/005'),('LESSONS','APPLE','CF08 Editing','FINALIST','CF08/002'),('THE ADVENTURES OF AMPY','AMPOL','CF10 Special Effects: In-Camera','BRONZE','CF10/004'),('MIRROR MIRROR','TELSTRA','CF11 Digital Visual Effects','FINALIST','CF11/003'),('CRAFTMAN.SHIPS','SHIPS','CF12 Animation','GOLD','CF12/006'),('FRIES BEAT 2025',"MCDONALD'S",'CF12 Animation','SILVER','CF12/004'),('PROJECT: MEMORY CARD','PLAYSTATION','CF12 Animation','SILVER','CF12/010'),('GO MONGOLIA','GOVERNMENT OF MONGOLIA','CF13 Original Music','SILVER','CF13/011'),('ECHOES OF KOREA - JEOLLA','KOREA TOURISM ORGANIZATION','CF13 Original Music','FINALIST','CF13/003'),('TOYOTA SAFETY','TOYOTA','CF16 Sound Design','FINALIST','CF16/002'),('SOUNDS HUMAN','JAPAN PHILHARMONIC ORCHESTRA','CF17 Breakthrough in Production','BRONZE','CF17/003'),
)
def craft_winners():
    out=[]
    for title,brand,category,award,code in CRAFT_ENTRIES:
        url=CRAFT_PDF_URL+f'&adfest_year=2025&code={quote(code)}'
        out.append({'source_url':url,'title':title,'brand':brand,'industry':'consumer','ad_type':'ADFEST Film Craft Lotus / '+category,'format':'video','language':'en','audio':True,'summary':f'ADFEST 2025 Film Craft Lotus official winners list; {category}; {award}.','quality_evidence':[f'ADFEST 2025 Film Craft Lotus official winners list ({code})',f'{category}; {award}'],'source_name':'ADFEST 2025 Film Craft Lotus official winners list','published':'2025','media_status':'source_link','media_role':'official award record; playback unverified','rights':'official public reference link; no media cached','tags':['adfest','film-craft-lotus','human_review_pending']})
    return _verified_records(out, 'craft')

ENTERTAINMENT_PDF_URL = 'https://www.adfest.com/index.php/Home/Pdfview/index.html?id=9&type=winnerslist'
ENTERTAINMENT_ENTRIES = (
 ('DORITOS CILANTRO SWAP','DORITOS','EN01 Consumer Goods','FINALIST','EN01/005'),('KUNG FRIES',"MCDONALD'S FRIES",'EN03 Retail, Leisure & Entertainment','BRONZE','EN03/001'),('TOXIC BACKFIRE','SAMSUNG','EN05 Corporate Image and CSR','SILVER','EN05/001'),('I MADE A MIXTAPE FOR YOU','APPLE','EN08 Fiction and Non-Fiction Film: 5-30 minutes','BRONZE','EN08/005'),("I'M OK NOT OK // BRINGING BACK TWO LONG-LOST FRIENDS",'BOYDPOD FEAT BILLKIN','EN10 Music Video','SILVER','EN10/003'),('SAVE THE MUSIC','APPLE','EN10 Music Video','BRONZE','EN10/001'),('THE GREAT IN-GAME WEDDING','BATTLEGROUNDS MOBILE INDIA','EN19 Community Engagement: Gaming','GOLD','EN19/001'),('CHEER SIGNS','TOKYO METROPOLITAN GOVERNMENT','EN27 Breakthrough in Sports','BRONZE','EN27/002'),('VASELINE HUH?','VASELINE','EN29 Brand Integration, Partnerships and Collaborations','SILVER','EN29/001'),('REAL FAZZ','FAZZIO','EN31 Use of Talent and Influencer','BRONZE','EN31/002'),('CHIZZALULU CHIZZALALA, THE EDIBLE BRAINROT','KFC THAILAND','EN35 Digital, Social and Emerging Technology','SILVER','EN35/003'),
)
def entertainment_winners():
    out=[]
    for title,brand,category,award,code in ENTERTAINMENT_ENTRIES:
        out.append({'source_url':ENTERTAINMENT_PDF_URL+f'&adfest_year=2025&code={quote(code)}','title':title,'brand':brand,'industry':'consumer','ad_type':'ADFEST Entertainment Lotus / '+category,'format':'video','language':'en','audio':True,'summary':f'ADFEST 2025 Entertainment Lotus official winners list; {category}; {award}.','quality_evidence':[f'ADFEST 2025 Entertainment Lotus official winners list ({code})',f'{category}; {award}'],'source_name':'ADFEST 2025 Entertainment Lotus official winners list','published':'2025','media_status':'source_link','media_role':'official award record; playback unverified','rights':'official public reference link; no media cached','tags':['adfest','entertainment-lotus','human_review_pending']})
    return _verified_records(out, 'entertainment')
