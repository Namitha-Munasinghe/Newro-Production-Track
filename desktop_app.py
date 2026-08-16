"""
Desktop entry point — wraps the existing Flask app (app.py) in a native
window via pywebview, instead of requiring a browser + localhost URL.

Run directly for local testing:  python desktop_app.py
Build into a Windows .exe with:  see build_windows.md
"""
import base64
import socket
import sys
import threading
import time
import urllib.request

import webview

from app import app as flask_app

WEBVIEW2_DOWNLOAD_URL = 'https://developer.microsoft.com/microsoft-edge/webview2/'


class Api:
    """
    JS-callable bridge (window.pywebview.api.*) for things a browser tab can
    do natively but an embedded webview can't be relied on for — PDF
    downloads via a synthetic <a download> click on a blob: URL routinely do
    nothing in an embedded WebView2 control, with no error and no dialog.
    Routing the save through a real native "Save As" dialog here sidesteps
    that entirely, since it's Python doing the file write, not the webview.
    """

    def save_pdf_file(self, data_uri, suggested_name):
        try:
            # jsPDF's output('datauristring') looks like:
            # "data:application/pdf;filename=generated.pdf;base64,JVBERi0x..."
            b64_data = data_uri.split(',', 1)[1] if ',' in data_uri else data_uri
            pdf_bytes = base64.b64decode(b64_data)

            result = webview.windows[0].create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=suggested_name,
                file_types=('PDF Files (*.pdf)', 'All files (*.*)')
            )
            if not result:
                return {'status': 'cancelled'}

            path = result[0] if isinstance(result, (list, tuple)) else result
            with open(path, 'wb') as f:
                f.write(pdf_bytes)
            return {'status': 'success', 'path': path}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}


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
        min_size=(1024, 700),
        js_api=Api()
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
