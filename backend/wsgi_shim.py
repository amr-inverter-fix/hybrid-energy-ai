"""Minimal ASGI-to-WSGI adapter for hosts without ASGI (e.g. PythonAnywhere free). HTTP only: no WebSocket, no streaming. One event loop per request."""
import asyncio, io
def make_wsgi(asgi_app):
    def application(environ, start_response):
        body = environ['wsgi.input'].read(int(environ.get('CONTENT_LENGTH') or 0))
        headers = []
        for k, v in environ.items():
            if k.startswith('HTTP_'):
                headers.append((k[5:].replace('_', '-').lower().encode('latin1'), v.encode('latin1')))
        if environ.get('CONTENT_TYPE'):
            headers.append((b'content-type', environ['CONTENT_TYPE'].encode('latin1')))
        if environ.get('CONTENT_LENGTH'):
            headers.append((b'content-length', environ['CONTENT_LENGTH'].encode('latin1')))
        path = environ.get('PATH_INFO', '/').encode('latin1').decode('utf8', 'replace')
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': environ['REQUEST_METHOD'],
                 'scheme': environ.get('wsgi.url_scheme', 'https'), 'path': path, 'raw_path': path.encode(),
                 'query_string': environ.get('QUERY_STRING', '').encode('latin1'), 'root_path': '',
                 'headers': headers, 'client': (environ.get('REMOTE_ADDR', '0.0.0.0'), 0), 'server': ('localhost', 443)}
        out = {'status': 500, 'headers': [], 'body': []}
        async def run():
            sent = False
            async def receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {'type': 'http.request', 'body': body, 'more_body': False}
                return {'type': 'http.disconnect'}
            async def send(m):
                if m['type'] == 'http.response.start':
                    out['status'] = m['status']; out['headers'] = m.get('headers', [])
                elif m['type'] == 'http.response.body':
                    out['body'].append(m.get('body', b''))
            await asgi_app(scope, receive, send)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens()); loop.close()
        start_response('%d OK' % out['status'], [(k.decode('latin1'), v.decode('latin1')) for k, v in out['headers']])
        return [b''.join(out['body'])]
    return application
