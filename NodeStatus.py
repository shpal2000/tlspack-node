from aiohttp import web
import json
import os
import sys

from .apps.TlsApp import TlsApp

app = web.Application()

async def run_state(request):
    runid = request.match_info['runid']
    return web.json_response ({"state" : TlsApp.run_state(runid)})

app.add_routes([web.get('/run_state/{runid:.*}', run_state)])

if __name__ == '__main__':
    web.run_app(app, port=8887)
