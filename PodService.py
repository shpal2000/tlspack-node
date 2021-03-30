#!/usr/bin/python3

from fastapi import FastAPI, BackgroundTasks
from typing import Optional, List
from pydantic import BaseModel

import asyncio
import uvicorn
import json
import sys
import os
import time

app = FastAPI()

appStats = {}

class StartParam(BaseModel):
    cfg_file: str
    z_index: int
    net_ifaces: List [str]
    rpc_ip_veth1: str
    rpc_ip_veth2: str
    rpc_port: int
    timeout: Optional [int] = 15


class StopParam(BaseModel):
    net_ifaces: List [str]
    rpc_ip_veth1: str
    rpc_ip_veth2: str
    rpc_port: int
    timeout: Optional [int] = 15


async def collect_stats(ip: str, port: int):
    global appStats
    while True:

        awk_exp = "'{print $2}'"
        cmd_str = "kill -0 $(ps aux | grep '[t]lspack.exe' | awk {})".format(awk_exp)
        status = os.system (cmd_str)
        if status: #not running
            break

        try:
            reader, writer = await asyncio.open_connection (ip, port, ssl=False)

            writer.write("get_ev_sockstats".encode())
            await writer.drain()
            writer.write_eof()

            response = await reader.read (-1)

            writer.close()
            await writer.wait_closed()

            appStats = json.loads (response)
        except:
            pass

        await asyncio.sleep(0.1)


@app.post('/start')
async def start(params : StartParam, background_tasks: BackgroundTasks):
    awk_exp = "'{print $2}'"
    cmd_str = "kill -0 $(ps aux | grep '[t]lspack.exe' | awk {})".format(awk_exp)
    status = os.system (cmd_str)
    if not status: #already running
        return {'status' : -2, 'error' : 'already running'}

    cmd_str = "ip netns add ns-tool"
    os.system (cmd_str)

    for netdev in params.net_ifaces:
        cmd_str = "ip link set dev {} netns ns-tool".format(netdev)
        os.system (cmd_str)

    cmd_str = "ip link add veth1 type veth peer name veth2"
    os.system (cmd_str)

    cmd_str = "ip addr add {}/24 dev veth1".format(params.rpc_ip_veth1)
    os.system (cmd_str)

    cmd_str = "ip link set dev veth1 up"
    os.system (cmd_str)

    cmd_str = "ip link set veth2 netns ns-tool"
    os.system (cmd_str)

    cmd_str = "ip netns exec ns-tool ip addr add {}/24 dev veth2". \
                                                format(params.rpc_ip_veth2)
    os.system (cmd_str)

    cmd_str = "ip netns exec ns-tool ip link set dev veth2 up"
    os.system (cmd_str)
    
    with open(params.cfg_file) as f:
        zone_cmds = json.load(f)["zones"][params.z_index]["zone_cmds"]
        for cmd in zone_cmds:
            cmd_str = "ip netns exec ns-tool {}".format(cmd)
            os.system (cmd_str)
    
    cmd_str = "ip netns exec {} /rundir/lib/tlspack.exe {} {} {} {} &".format('ns-tool'
            , params.rpc_ip_veth2
            , params.rpc_port
            , params.cfg_file
            , params.z_index)
    os.system (cmd_str)

    time_tick = 0
    init_done = False
    while time_tick < params.timeout:
        await asyncio.sleep(1)
        time_tick += 1
        try:
            reader, writer = await asyncio.open_connection (params.rpc_ip_veth2
                                                            , params.rpc_port
                                                            , ssl=False)

            writer.write("is_init".encode())
            await writer.drain()
            writer.write_eof()

            response = await reader.read (-1)
            
            writer.close()
            await writer.wait_closed()

            j_resp = json.loads(response)
            if j_resp.get('cmd_resp') == 'init_done':
                init_done = True
                break
        except:
            pass

    if init_done:
        background_tasks.add_task(collect_stats
                                    , params.rpc_ip_veth2
                                    , params.rpc_port)
        return {"status" : 0}

    return {"status" : -1, 'error' : 'timeout'}


@app.post('/stop')
async def stop(params : StopParam):
    
    awk_exp = "'{print $2}'"
    cmd_str = "kill -0 $(ps aux | grep '[t]lspack.exe' | awk {})".format(awk_exp)
    status = os.system (cmd_str)

    if status: # not running
        stop_done = True
    else:
        time_tick = 0
        stop_done = False
        while time_tick < params.timeout:
            await asyncio.sleep(1)
            time_tick += 1
            try:
                reader, writer = await asyncio.open_connection (params.rpc_ip_veth2
                                                                , params.rpc_port
                                                                , ssl=False)

                writer.write("stop".encode())
                await writer.drain()
                writer.write_eof()

                response = await reader.read (-1)

                writer.close()
                await writer.wait_closed()

                j_resp = json.loads(response)
                if j_resp.get('cmd_resp') == 'STOP_FINISH':
                    stop_done = True
                    break
            except:
                pass

    awk_exp = "'{print $2}'"
    cmd_str = "kill $(ps aux | grep '[t]lspack.exe' | awk {})".format(awk_exp)    
    os.system (cmd_str)

    cmd_str = "ip netns exec ns-tool ip link set veth2 netns 1"
    os.system (cmd_str)

    cmd_str = "ip link delete veth1"
    os.system (cmd_str)

    for netdev in params.net_ifaces:
        cmd_str = "ip netns exec ns-tool ip link set {} netns 1".format(netdev)
        os.system (cmd_str)

    cmd_str = "ip netns del ns-tool"
    os.system (cmd_str)

    if stop_done:
        return {"status" : 0}
    return {"status" : -1, 'error' : 'timeout'}

@app.get('/ev_sockstats')
async def ev_sockstats():
    return appStats


if __name__ == '__main__':
    rpc_proxy_ip = sys.argv[1]
    rpc_proxy_port = int(sys.argv[2])
    asyncio.run (uvicorn.run(app
                                , host=rpc_proxy_ip
                                , port=rpc_proxy_port
                                , loop='asyncio'
                                , debug=False))
