from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_required_files():
    for name in ['app.py','requirements.txt','run_frost.bat','.env.example','README.md']:
        assert (ROOT/name).exists(), name


def test_voice_removed():
    app=(ROOT/'app.py').read_text(encoding='utf-8'); req=(ROOT/'requirements.txt').read_text(encoding='utf-8')
    assert 'st.audio_input' not in app and 'SpeechRecognition' not in req and not (ROOT/'src'/'voice.py').exists()


def test_no_demo_order_button():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    assert 'PLACE DEMO ORDER' not in app
    assert '"Place order"' in app


def test_no_duplicate_taste_features():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    assert 'Taste DNA' not in app
    assert 'Flavor Lab' not in app


def test_no_command_like_fallback():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    assert 'Try “something chocolatey under ₹500”' not in app


def test_navigation_views_exist():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    for token in ['"chat"', '"shop"', '"cart"', '"account"', 'elif st.session_state.view == "checkout"']:
        assert token in app


def test_no_command_like_home_copy():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    assert 'No commands needed' not in app
