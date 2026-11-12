"""Credential-holding host relay; isolated applications only reach Responses."""

from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import socketserver
import threading
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class ModelProxy:
    def __init__(self, directory, connection):
        base = connection['baseUrl'].rstrip('/')
        address = urlsplit(base)
        if address.scheme not in ('http', 'https') or not address.netloc or address.username or address.query or address.fragment:
            raise ValueError('Use a standard model base URL without credentials or query.')
        endpoint, key, model = base + '/responses', connection.get('apiKey', ''), connection['modelId']

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                if self.path != '/v1/responses':
                    self.send_error(404)
                    return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 8_000_000:
                        raise ValueError()
                    body = self.rfile.read(length)
                    if json.loads(body).get('model') != model:
                        raise ValueError()
                except (ValueError, TypeError, AttributeError):
                    self.send_error(400)
                    return
                headers = {'Content-Type': 'application/json'}
                if key:
                    headers['Authorization'] = 'Bearer ' + key
                try:
                    try:
                        response = urlopen(Request(endpoint, data=body, headers=headers), timeout=600)
                    except HTTPError as error:
                        response = error
                except OSError:
                    self.send_error(502)
                    return
                self.send_response(response.status)
                self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                self.send_header('Connection', 'close')
                self.end_headers()
                try:
                    while chunk := response.read1(8192):
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    response.close()

        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

        self.path = Path(directory) / 'api.sock'
        self.server = Server(str(self.path), Handler)
        # Parent directory is private; the unprivileged container needs the socket.
        os.chmod(self.path, 0o666)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.path.unlink(missing_ok=True)
