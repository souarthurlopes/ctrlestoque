"""Entrada WSGI para Gunicorn; reutiliza as rotas e permissões do servidor."""
from email.message import Message
from http import HTTPStatus
from io import BytesIO
import os
from supabase_server import Handler, ROOT, Supabase

HOP_HEADERS = {'connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailers','transfer-encoding','upgrade'}

class Request(Handler):
    def __init__(self, environ, backend, secure_cookie):
        # O servidor WSGI já analisou o HTTP. Não criar um socket ou novo listener.
        self.backend = backend
        self.secure_cookie = secure_cookie
        self.directory = str(ROOT)
        self.command = environ['REQUEST_METHOD'].upper()
        self.path = environ.get('PATH_INFO','/')
        if environ.get('QUERY_STRING'):
            self.path += '?' + environ['QUERY_STRING']
        self.request_version = environ.get('SERVER_PROTOCOL','HTTP/1.1')
        self.requestline = self.command + ' ' + self.path + ' ' + self.request_version
        self.client_address = (environ.get('REMOTE_ADDR',''),0)
        self.headers = Message()
        for name,value in environ.items():
            if name.startswith('HTTP_'):
                self.headers[name[5:].replace('_','-')] = str(value)
        for name in ('CONTENT_TYPE','CONTENT_LENGTH'):
            if environ.get(name): self.headers[name.replace('_','-')] = str(environ[name])
        self.rfile = environ['wsgi.input']
        self.wfile = BytesIO()
        self.response_status = '200 OK'
        self.response_headers = []

    def send_response(self, code, message=None):
        self.response_status = f'{code} {message or HTTPStatus(code).phrase}'

    def send_header(self, keyword, value):
        if keyword.lower() not in HOP_HEADERS:
            self.response_headers.append((keyword,str(value)))

    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')

    def log_message(self, *args):
        # Gunicorn cuida dos logs, sem imprimir corpos ou cookies.
        pass

def create_app(backend=None, secure_cookie=None):
    remote = backend or Supabase()
    secure = os.environ.get('CONTROLAI_SECURE_COOKIE')=='1' if secure_cookie is None else secure_cookie
    def application(environ,start_response):
        request = Request(environ,remote,secure)
        if request.path == '/healthz' and request.command in ('GET','HEAD'):
            request.reply(200,dict(status='ok',backend='supabase'))
        elif request.command in ('GET','HEAD'):
            request.do_GET() # HEAD também passa pela lista de arquivos públicos.
        elif request.command in ('POST','PUT'):
            getattr(request,'do_'+request.command)()
        else:
            request.reply(405,dict(error='Método não permitido.'))
        body = request.wfile.getvalue()
        start_response(request.response_status,request.response_headers)
        return [b'' if request.command=='HEAD' else body]
    return application

app = create_app()
