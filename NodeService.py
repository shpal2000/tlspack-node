from aiohttp import web
import json
import os
import sys
import asyncio

from .apps.TlsApp import TlsApp
from .apps.TlsApp import TlsAppError

class ServiceUitl(object):
    @staticmethod
    def get_info(infoid):
        return TlsApp.get_info(infoid)

async def store_info(request):
    infoid = request.match_info['infoid']
    data_s = await request.read()
    data_j = json.loads(data_s)
    TlsApp.store_info(infoid, data_j)
    info_file = '/rundir/store/'+infoid
    with open (info_file, 'w') as f:
        f.write(data_s)
    return web.json_response ({"status" : 0})

async def remove_info(request):
    infoid = request.match_info['infoid']
    info_file = '/rundir/store/'+infoid
    if os.path.isfile(info_file):
        os.remove(info_file)
    TlsApp.remove_info(infoid)
    return web.json_response ({"status" : 0})

async def run_list(request):
    return web.json_response ({"run_list" : TlsApp.run_list()})

async def run_stats(request):
    try:
        runid = request.match_info['runid']
        return web.json_response (TlsApp.run_stats (runid))
    except TlsAppError as err:
        return web.Response (status=500, text=str(err))

async def start_run(request):
    try:
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


        TlsApp.start_run ('rundir.apps'
                            , app_name
                            , neighborhood_name
                            , runid
                            , **data_j)
    except TlsAppError as err:
        return web.Response (status=500, text=str(err))

    return web.json_response ({'status' : 0})

async def stop_run(request):
    try:
        runid = request.match_info['runid']
        TlsApp.stop_run (runid)
    except TlsAppError as err:
        return web.Response (status=500, text=str(err))

    return web.json_response ({'status' : 0})

async def fallback_path_handler(request):
    fallback_path = request.match_info['fallback_path']

    if os.path.isfile ( os.path.join ('/uidir/', fallback_path) ):
        return web.FileResponse (path=os.path.join ('/uidir/', fallback_path))

    with open('/uidir/index.html') as f:
        index_str = f.read()
    return web.Response (status=200, text=str(index_str), content_type='text/html')

if __name__ == '__main__':
    sys.path.append('/plugindir')
    import RoutesExt 

    TlsApp.restart(sys.argv[1])

    app = web.Application()

    app.add_routes( RoutesExt.get_routes(ServiceUitl) + [ web.get('/store_info/{infoid:.*}', store_info),
        web.get('/remove_info/{infoid:.*}', remove_info),
        web.get('/run_list', run_list),
        web.get('/run_stats/{runid:.*}', run_stats),
        web.post('/start_run/{runid:.*}', start_run),
        web.get('/stop_run/{runid:.*}', stop_run),
        web.static('/static', '/uidir/static'),
        web.get('/{fallback_path:.*}', fallback_path_handler),
    ])


    web.run_app(app, port=8889)
