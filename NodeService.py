from aiohttp import web
import json
import os
import sys

from .apps.TlsApp import TlsApp

app = web.Application()

async def run_list(request):
    return web.json_response ({"run_list" : TlsApp.run_list()})

async def run_stats(request):
    runid = request.match_info['runid']
    return web.json_response (TlsApp.run_stats (runid))

async def start_run(request):
    runid = request.match_info['runid']
    app_name = request.query['app']
    neighborhood = request.query['neighborhood']
    testbed_delay = int(request.query.get('testbed_delay', '10'))

    data_s = await request.read()
    data_j = json.loads(data_s)

    cfg_j = TlsApp.create_config ('rundir.apps'
                            , app_name
                            , neighborhood
                            , **data_j)

    TlsApp.start_run ('rundir.apps'
                        , runid
                        , cfg_j
                        , testbed_delay)

    return web.json_response ({'status' : 0})

async def stop_run(request):
    runid = request.match_info['runid']
    TlsApp.stop_run (runid)
    return web.json_response ({'status' : 0})

async def get_neighborhood(request):
    neighborhood_name = request.match_info['neighborhood_name']
    with open ('/rundir/arenas/'+neighborhood_name) as f:
        data_j = json.loads(f.read())
        data_j.pop('modified', None)
        return web.json_response(data_j)

async def set_neighborhood(request):
    neighborhood_name = request.match_info['neighborhood_name']
    data_s = await request.read()
    data_j = json.loads(data_s)
    data_j['testbed'] = neighborhood_name
    data_j.pop('ready', None)
    data_j.pop('runing', None)
    data_j['modified'] = 1
    with open ('/rundir/arenas/'+neighborhood_name, 'w') as f:
        f.write(json.dumps(data_j))
    return web.json_response ({'status' : 0})

async def remove_neighborhood(request):
    neighborhood_name = request.match_info['neighborhood_name']
    os.system('rm -f ' + '/rundir/arenas/'+neighborhood_name)
    return web.json_response ({'status' : 0})

app.add_routes([web.get('/run_list', run_list),
                web.get('/run_stats/{runid:.*}', run_stats),
                web.post('/start_run/{runid:.*}', start_run),
                web.get('/stop_run/{runid:.*}', stop_run),
                web.get('/neighborhood/{neighborhood_name:.*}', get_neighborhood),
                web.post('/neighborhood/{neighborhood_name:.*}', set_neighborhood),
                web.delete('/neighborhood/{neighborhood_name:.*}', remove_neighborhood)])

if __name__ == '__main__':
    TlsApp.restart(sys.argv[1])
    web.run_app(app, port=8889)
