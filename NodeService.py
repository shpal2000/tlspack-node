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

    data_s = await request.read()
    data_j = json.loads(data_s)

    neighborhood_j = data_j.pop('neighborhood')
    neighborhood_j.pop('testbed', None)
    neighborhood_j.pop('ready', None)
    neighborhood_j.pop('runing', None)
    neighborhood_j.pop('modified', None)
    neighborhood_name = runid
    neighborhood_file_name = '/rundir/arenas/'+neighborhood_name

    if not os.path.isfile(neighborhood_file_name):
        with open (neighborhood_file_name, 'w') as f:
            neighborhood_j['modified'] = 1
            f.write(json.dumps(neighborhood_j))
            neighborhood_j.pop('modified', None)
            TlsApp.insert_testbed(neighborhood_name, neighborhood_j)
    else:
        with open (neighborhood_file_name) as f:
            neighborhood_j_org = json.loads(f.read())
            neighborhood_j_org.pop('testbed', None)
            neighborhood_j_org.pop('ready', None)
            neighborhood_j_org.pop('runing', None)
            neighborhood_j_org.pop('modified', None)
            if neighborhood_j == neighborhood_j_org:
                neighborhood_j['modified'] = 0
            else:
                neighborhood_j['modified'] = 1
        with open (neighborhood_file_name, 'w') as f:
            f.write(json.dumps(neighborhood_j))


    cfg_j = TlsApp.create_config ('rundir.apps'
                            , app_name
                            , neighborhood_name
                            , **data_j)

    TlsApp.start_run ('rundir.apps'
                        , runid
                        , cfg_j)

    return web.json_response ({'status' : 0})

async def stop_run(request):
    runid = request.match_info['runid']
    TlsApp.stop_run (runid)
    return web.json_response ({'status' : 0})

app.add_routes([web.get('/run_list', run_list),
                web.get('/run_stats/{runid:.*}', run_stats),
                web.post('/start_run/{runid:.*}', start_run),
                web.get('/stop_run/{runid:.*}', stop_run)])

if __name__ == '__main__':
    TlsApp.restart(sys.argv[1])
    web.run_app(app, port=8889)
