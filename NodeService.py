from aiohttp import web
import json
import os
import sys

from .apps.TlsApp import TlsApp

app = web.Application()

async def create_config(request):
    data_s = await request.read()
    data_j = json.loads(data_s)
    return web.json_response (TlsApp.create_config ('rundir.apps'
                                , data_j['app_name']
                                , data_j['testbed']
                                , **data_j['app_params']))

async def start_run(request):
    data_s = await request.read()
    data_j = json.loads(data_s)
    TlsApp.start_run ('rundir.apps'
                        , data_j['runid']
                        , data_j['app_config'])
    return web.json_response ({'status' : 0})


async def purge_testbed(request):
    data_s = await request.read()
    data_j = json.loads(data_s)
    TlsApp.purge_testbed (data_j['testbed'])
    return web.json_response ({'status' : 0})


async def stop_run(request):
    data_s = await request.read()
    data_j = json.loads(data_s)
    TlsApp.stop_run (data_j['runid'])
    return web.json_response ({'status' : 0})


async def run_stats(request):
    return web.json_response (TlsApp.run_stats (request.query['runid']))


async def run_list(request):
    return web.json_response ({"run_list" : TlsApp.run_list()})


app.add_routes([web.get('/run_list', run_list),
                web.get('/run_stats', run_stats),
                web.post('/stop_run', stop_run),
                web.post('/purge_testbed', purge_testbed),
                web.post('/start_run', start_run),
                web.post('/create_config', create_config)])

if __name__ == '__main__':
    TlsApp.restart(sys.argv[1])
    web.run_app(app, port=8889)
