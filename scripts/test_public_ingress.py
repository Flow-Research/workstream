"""Exercise canonical Caddy routes over real sockets with bounded upstream fixtures.

The test frontend is HTTP on loopback; real public certificate issuance is a
separate deployment proof. The identity upstream uses verified TLS here.
"""
from __future__ import annotations

import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublicIngressTest(unittest.TestCase):
    def test_exact_hosts_paths_headers_upload_and_identity_tls(self):
        binary = os.environ['WORKSTREAM_TEST_CADDY']
        with tempfile.TemporaryDirectory(prefix='ws-ingress-') as directory:
            root = Path(directory)
            cert, key = root / 'cert.pem', root / 'key.pem'
            subprocess.run([
                'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                '-days', '1', '-subj', '/CN=identity.example.test', '-addext',
                'subjectAltName=DNS:identity.example.test', '-keyout', str(key),
                '-out', str(cert),
            ], check=True, capture_output=True)
            calls = []

            class Upstream(http.server.BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    pass

                def do_GET(self):
                    self.do_POST()

                def do_POST(self):
                    length = int(self.headers.get('Content-Length', '0'))
                    body = self.rfile.read(length)
                    calls.append((self.path, dict(self.headers), len(body)))
                    # Simulate the unchanged MCP Origin boundary. Live SDK proof
                    # independently exercises the real MCP server's implementation.
                    if self.path == '/mcp' and self.headers.get('Origin'):
                        self.send_response(403)
                        self.end_headers()
                        return
                    response = json.dumps({'path': self.path, 'bytes': len(body),
                                           'sha256': hashlib.sha256(body).hexdigest()}).encode()
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)

            plain = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
            secure = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            secure.socket = context.wrap_socket(secure.socket, server_side=True)
            threads = [threading.Thread(target=s.serve_forever, daemon=True)
                       for s in (plain, secure)]
            for thread in threads:
                thread.start()
            process = None
            try:
                env = dict(os.environ, DEMO_IDENTITY_HOSTNAME='identity.example.test',
                           DEMO_IDENTITY_UPSTREAM_CERT=str(cert),
                           WORKSTREAM_PUBLIC_HOSTNAME='workstream.example.test',
                           WORKSTREAM_API_HOST_PORT='18027')
                adapted = subprocess.run([binary, 'adapt', '--config',
                    str(ROOT / 'deploy/hosted/public.Caddyfile'), '--adapter', 'caddyfile'],
                    env=env, check=True, capture_output=True, text=True)
                config = json.loads(adapted.stdout)
                server = next(iter(config['apps']['http']['servers'].values()))
                self.assertEqual(server['listen'], [':443'])
                self.assertEqual(config['admin'], {'disabled': True})
                # Only transport addresses/frontend TLS are changed for this fixture.
                # Routing, host/header rules, body limits and upstream TLS stay intact.
                seen, limits = [], []

                def relocate(value):
                    if isinstance(value, dict):
                        if value.get('handler') == 'request_body':
                            limits.append(value['max_size'])
                        if value.get('handler') == 'reverse_proxy':
                            address = value['upstreams'][0]['dial']
                            self.assertIn(address, ['127.0.0.1:8080', '127.0.0.1:8443',
                                                    '127.0.0.1:18027'])
                            seen.append(address)
                            port = secure.server_port if address.endswith(':8443') else plain.server_port
                            value['upstreams'][0]['dial'] = f'127.0.0.1:{port}'
                        for child in value.values():
                            relocate(child)
                    elif isinstance(value, list):
                        for child in value:
                            relocate(child)

                relocate(config)
                self.assertCountEqual(seen, ['127.0.0.1:8443'] * 2 +
                                      ['127.0.0.1:8080', '127.0.0.1:18027'])
                self.assertCountEqual(limits, [4096, 96 * 1024**2, 500 * 1024**2])
                with socket.socket() as probe:
                    probe.bind(('127.0.0.1', 0))
                    port = probe.getsockname()[1]
                server['listen'] = [f'127.0.0.1:{port}']
                server['automatic_https'] = {'disable': True}
                server.pop('tls_connection_policies', None)
                config['apps'].pop('tls', None)
                path = root / 'config.json'
                path.write_text(json.dumps(config))
                log = open(root / 'caddy.log', 'wb')
                self.addCleanup(log.close)
                process = subprocess.Popen([binary, 'run', '--config', str(path)],
                                           stdout=log, stderr=log)
                for _ in range(100):
                    if process.poll() is not None:
                        self.fail('Caddy exited before readiness: ' + (root / 'caddy.log').read_text())
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.1):
                            break
                    except OSError:
                        time.sleep(.05)
                else:
                    self.fail('Caddy did not listen')

                def request(host, target, body=None, extra=None):
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
                    try:
                        connection.request('POST' if body is not None else 'GET', target,
                                           body=body, headers={'Host': host, **(extra or {})})
                        response = connection.getresponse()
                        return response.status, response.read()
                    finally:
                        connection.close()

                self.assertEqual(request('identity.example.test', '/jwks.json')[0], 200)
                self.assertEqual(request('identity.example.test', '/login', b'x' * 4097)[0], 413)
                before = len(calls)
                self.assertEqual(request('identity.example.test', '/not-a-route')[0], 404)
                self.assertEqual(request('foreign.example.test', '/api/v1/health')[0], 404)
                self.assertEqual(request('workstream.example.test', '/admin/accounts', b'{}')[0], 404)
                self.assertEqual(len(calls), before)
                # Larger than identity's limit, still a valid API body; prove streaming
                # preserves exact bytes rather than merely accepting a status code.
                body = b'zip-fixture-' * 100000
                status, result = request('workstream.example.test', '/api/v1/upload', body)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(result)['sha256'], hashlib.sha256(body).hexdigest())
                self.assertEqual(json.loads(result)['bytes'], len(body))
                spoofed = {'X-Forwarded-For': '192.0.2.66', 'X-Real-IP': '192.0.2.66',
                           'Forwarded': 'for=192.0.2.66;host=evil.invalid',
                           'X-Forwarded-Host': 'evil.invalid', 'X-Forwarded-Proto': 'http',
                           'Authorization': 'Bearer synthetic-test-only'}
                self.assertEqual(request('workstream.example.test', '/mcp', b'{}', spoofed)[0], 200)
                headers = {k.lower(): v for k, v in calls[-1][1].items()}
                self.assertEqual(headers['host'], '127.0.0.1:8080')
                self.assertEqual(headers['authorization'], 'Bearer synthetic-test-only')
                self.assertNotIn('192.0.2.66', json.dumps(headers))
                self.assertNotIn('evil.invalid', json.dumps(headers))
                self.assertEqual(request('workstream.example.test', '/mcp', b'{}',
                                         {'Origin': 'https://evil.invalid'})[0], 403)
                self.assertEqual(calls[-1][1]['Origin'], 'https://evil.invalid')
            finally:
                if process is not None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                plain.shutdown()
                secure.shutdown()
                plain.server_close()
                secure.server_close()
                for thread in threads:
                    thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
