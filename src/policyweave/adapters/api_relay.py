"""Container-local protocol relay; contains no model credentials."""

import select
import socket
import socketserver
import ssl
import argparse


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.connect("/run/policy-api.sock")
            while True:
                ready, _, _ = select.select([self.request, upstream], [], [], 650)
                if not ready:
                    return
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    (upstream if source is self.request else self.request).sendall(data)


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cert")
    parser.add_argument("--key")
    args = parser.parse_args()
    server = Server(("127.0.0.1", 8765), Handler)
    if args.cert or args.key:
        if not (args.cert and args.key):
            parser.error("TLS requires both certificate and key.")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.cert, args.key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()
