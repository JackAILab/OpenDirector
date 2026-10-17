from types import SimpleNamespace
from harness.tools import creative_render as render


def test_blank_caption_has_no_overlay_but_preserves_footage_and_sound(tmp_path,monkeypatch):
    gsap=tmp_path/'gsap.js';gsap.write_text('')
    monkeypatch.setenv('CREATIVE_GSAP',str(gsap));monkeypatch.setenv('CREATIVE_HYPERFRAMES','test-cli');monkeypatch.setenv('CREATIVE_FFMPEG','test-ffmpeg')
    monkeypatch.setattr(render,'verify_native_audio',lambda *args:None)
    monkeypatch.setattr(render,'probe',lambda *args:{'format':{'duration':'15'},'streams':[{'codec_type':'video','width':1280,'height':720},{'codec_type':'audio'}]})
    monkeypatch.setattr(render.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0))
    for captions in (['',' \n ',''],['','真实字幕','']):
        directory=tmp_path/('blank' if not captions[1].strip() else 'mixed');directory.mkdir()
        project={'aspect':'16:9','duration':15,'generation_mode':'single_native','shots':[{'start':i*5,'duration':5,'caption':c} for i,c in enumerate(captions)]}
        result=render.render(project,directory);html=(directory/'index.html').read_text()
        assert html.count('class="clip copy"')==(1 if captions[1].strip() else 0)
        assert 'data-has-audio="true"' in html and 'src="film.mp4"' in html
        assert result['audio'] is True
        if captions[1].strip():assert 'id="copy-1"' in html and '真实字幕' in html
