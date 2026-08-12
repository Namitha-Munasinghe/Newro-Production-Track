"""
Desktop entry point — wraps the existing Flask app (app.py) in a native
window via pywebview, instead of requiring a browser + localhost URL.

Run directly for local testing:  python desktop_app.py
Build into a Windows .exe with:  see build_windows.md
"""
import socket
import sys
import threading
import time
import urllib.request

import webview

from app import app as flask_app

WEBVIEW2_DOWNLOAD_URL = 'https://developer.microsoft.com/microsoft-edge/webview2/'


def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_flask(port):
    # debug/reloader off: the reloader spawns a second process, which breaks
    # both PyInstaller-frozen builds and the background-thread model here.
    flask_app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False, threaded=True)


def wait_for_server(port, timeout=10):
    deadline = time.time() + timeout
    url = f'http://127.0.0.1:{port}/login'
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main():
    port = find_free_port()
    threading.Thread(target=start_flask, args=(port,), daemon=True).start()

    if not wait_for_server(port):
        raise RuntimeError('Local server did not start in time.')

    webview.create_window(
        'Newro Operations',
        f'http://127.0.0.1:{port}/',
        width=1440,
        height=900,
        min_size=(1024, 700)
    )

    try:
        # Force the modern Chromium-based Edge engine. Left to auto-detect,
        # pywebview silently falls back to the ancient IE/Trident engine on
        # any Windows PC without the WebView2 Runtime installed — which can't
        # run this app's JS/CSS at all, but LOOKS like a half-working app
        # (faded styling, dead buttons) rather than an obvious failure.
        webview.start(gui='edgechromium' if sys.platform == 'win32' else None)
    except Exception as exc:
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                'Newro Operations needs the Microsoft Edge WebView2 Runtime, which '
                "isn't installed on this PC.\n\n"
                f'Install it from:\n{WEBVIEW2_DOWNLOAD_URL}\n\n'
                'Then reopen this app.\n\n'
                f'(Technical detail: {exc})',
                'Newro Operations - Missing Component',
                0x10  # MB_ICONERROR
            )
        raise


if __name__ == '__main__':
    main()
