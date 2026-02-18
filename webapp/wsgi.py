"""PythonAnywhere WSGI entrypoint for FastAPI.

PythonAnywhere expects a WSGI callable named `application`.
FastAPI is ASGI, so we adapt ASGI -> WSGI using a2wsgi.
"""
from a2wsgi import ASGIMiddleware
from app.main import app

application = ASGIMiddleware(app)
