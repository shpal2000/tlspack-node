__author__ = 'Shirish Pal'

import os
import sys
import uuid
import json
import time
import signal
import argparse
import requests
import ipaddress
import importlib
import subprocess
from threading import Thread
from functools import reduce
from pymongo import MongoClient

from .config import POD_RUNDIR, NODE_SRCDIR, POD_SRCDIR, TCPDUMP_FLAG
from .config import REGISTRY_DB_NAME, RESULT_DB_NAME
from .config import STATS_TABLE, CSTATE_TABLE, LIVE_STATS_TABLE, POD_RUNDIR
from .config import RPC_IP_VETH1, RPC_IP_VETH2, RPC_PORT, NODE_SRCDIR, POD_SRCDIR
from .config import TESTBED_TABLE, RUN_TABLE, STATE_TABLE, INFO_TABLE

class TlsCfg:
    DB_CSTRING = 'localhost:27017'
    NODE_RUNDIR = '/root/rundir'


def nodecmd(_cmd_str, check_ouput=False):
    print (_cmd_str)
    ssh_cmd = "ssh -i /rundir/ssh/ssh_rsa_id -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null localhost"
    cmd_str = ssh_cmd + ' ' + '"{}"'.format (_cmd_str)
    if check_ouput:
        return subprocess.check_output(cmd_str, shell=True, close_fds=True).decode("utf-8").strip()
    else:
        os.system(cmd_str)
        return None

def localcmd(cmd_str, check_ouput=False):
    if check_ouput:
        return subprocess.check_output(cmd_str, shell=True, close_fds=True).decode("utf-8").strip()
    else:
        os.system(cmd_str)
        return None

def get_pod_name (testbed, pod_index):
    return "tlspack_{}_pod_{}".format (testbed, pod_index+1)

def get_pod_ip (testbed, pod_index):
    pod_name = get_pod_name (testbed, pod_index)
    cmd_str = "sudo docker inspect --format='{{.NetworkSettings.IPAddress}}' " + pod_name
    return nodecmd(cmd_str, check_ouput=True)

def start_run_thread(testbed
                        , pod_index
                        , pod_cfg_file
                        , pod_iface_list
                        , pod_ip):

    url = 'http://{}:{}/start'.format(pod_ip, RPC_PORT)

    data = {'cfg_file': pod_cfg_file
                , 'z_index' : pod_index
                , 'net_ifaces' : pod_iface_list
                , 'rpc_ip_veth1' : RPC_IP_VETH1
                , 'rpc_ip_veth2' : RPC_IP_VETH2
                , 'rpc_port' : RPC_PORT}

    resp = requests.post(url, json=data)


def stop_run_thread(testbed
                        , pod_index
                        , pod_iface_list
                        , pod_ip):

    url = 'http://{}:{}/stop'.format(pod_ip, RPC_PORT)

    data = {'net_ifaces' : pod_iface_list
                , 'rpc_ip_veth1' : RPC_IP_VETH1
                , 'rpc_ip_veth2' : RPC_IP_VETH2
                , 'rpc_port' : RPC_PORT}

    resp = requests.post(url, data=json.dumps(data))

    # todo


def start_run_stats (runid
                        , server_pod_ips=[]
                        , proxy_pod_ips=[]
                        , client_pod_ips=[]):

    stats_pid_file = os.path.join(POD_RUNDIR, 'traffic', runid, 'stats_pid.txt')

    pod_ips = ''
    if server_pod_ips:
        pod_ips += ' --server_pod_ips ' + ':'.join(server_pod_ips)
    if proxy_pod_ips:
        pod_ips += ' --proxy_pod_ips ' + ':'.join(proxy_pod_ips)
    if client_pod_ips:
        pod_ips += ' --client_pod_ips ' + ':'.join(client_pod_ips)

    localcmd('python3 -m rundir.apps.TlsApp --runid {} {} & echo $! > {}'. \
                                format (runid, pod_ips, stats_pid_file))

    stats_pid = 0
    with open (stats_pid_file) as f:
        stats_pid = int(f.read().strip())

    return stats_pid


def stop_run_stats(stats_pid):
    if stats_pid:
        try:
            os.kill (stats_pid, signal.SIGKILL)
        except:
            print (sys.exc_info())

def run_stats_iter(runid):
    mongoClient = MongoClient (TlsCfg.DB_CSTRING)
    db = mongoClient[RESULT_DB_NAME]
    stats_col = db[LIVE_STATS_TABLE]
    run_table = db[RUN_TABLE]

    while run_table.find_one ({'runid' : runid}):
        try:
            stats = stats_col.find({'runid' : runid})[0]
        except:
            stats = {}
        yield stats

def next_ipaddr (ip_addr, count):
    return ipaddress.ip_address(ip_addr) + count


class TlsAppError (Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message

        
class TlsAppRun:
    def __init__(self, runid, new_run=True):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        run_table = db[RUN_TABLE]
        if new_run:
            if run_table.find_one ({'runid' : runid}):
                raise TlsAppError(-1,  'error: {} already runing'.format (runid))
        else:
            if not run_table.find_one ({'runid' : runid}):
                raise TlsAppError(-1,  'error: invlaid runid'.format (runid))

        self.runid = runid

    @property
    def testbed (self):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        run_table = db[RUN_TABLE]
        return run_table.find_one ({'runid' : self.runid}).get('testbed', '')

    @testbed.setter
    def testbed (self, value):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        run_table = db[RUN_TABLE]
        run_table.insert ({'runid' : self.runid, 'testbed' : value})

    @property
    def stats_pid(self):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        run_table = db[RUN_TABLE]
        return run_table.find_one ({'runid' : self.runid}).get('stats_pid', '')

    @stats_pid.setter
    def stats_pid(self, value):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        run_table = db[RUN_TABLE]
        run_table.update ({'runid' : self.runid}
                            , {"$set": { "stats_pid": value }})


    @property
    def state (self):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        state_table = db[STATE_TABLE]
        return state_table.find_one ({'state_id' : self.runid}).get('state', '')

    @state.setter
    def state (self, value):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        state_table = db[STATE_TABLE]
        state_table.update ({'state_id' : self.runid}
                            , {"$set": { "state": value }})

    def init_state (self, value):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        state_table = db[STATE_TABLE]
        try:
            state_table.remove ({'state_id' : self.runid})
        except:
            pass 
        state_table.insert ({'state_id' : self.runid
                            , 'start' : str(time.time())
                            , 'state' : value })

    def dispose(self):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        run_table = db[RUN_TABLE]
        run_table.remove ({'runid' : self.runid})
        self.runid = ''


class TlsAppTestbed:
    def __init__(self, testbed):
        self.testbed = testbed
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        testbed_table = db[TESTBED_TABLE]
        if not testbed_table.find_one({'testbed' : self.testbed}):
            raise TlsAppError(-1, 'testbed {} does not exist'.format (self.testbed))

    @property
    def type(self):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        testbed_table = db[TESTBED_TABLE]
        return testbed_table.find_one({'testbed' : self.testbed}).get('type', '')       

    @property
    def ready(self):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        testbed_table = db[TESTBED_TABLE]
        return testbed_table.find_one({'testbed' : self.testbed}).get('ready', 0)

    @ready.setter
    def ready(self, value):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        testbed_table = db[TESTBED_TABLE]
        testbed_table.update({'testbed' : self.testbed}, {"$set": { 'ready': value}})
    
    @property
    def runid(self):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        testbed_table = db[TESTBED_TABLE]
        return testbed_table.find_one({'testbed' : self.testbed}).get('runing', '')

    @runid.setter
    def runid(self, value):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        testbed_table = db[TESTBED_TABLE]
        testbed_table.update({'testbed' : self.testbed}, {"$set": { 'runing': value }})

    @property
    def busy(self):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        testbed_table = db[TESTBED_TABLE]
        if testbed_table.find_one({'testbed' : self.testbed}).get('runing'):
            return True
        return False

    def get_info(self):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        testbed_table = db[TESTBED_TABLE]
        return testbed_table.find_one({'testbed' : self.testbed})


class TlsCsAppTestbed (TlsAppTestbed):
    def __init__(self, testbed):

        super().__init__(testbed)

        testbed_info = self.get_info()

        self.pod_iface = 'eth1'
        self.traffic_paths = testbed_info['traffic_paths']
        self.traffic_path_count = len(self.traffic_paths)
        
    def start_pod(self, pod_index, testbed_info, traffic_path, client):
        rundir_map = "--volume={}:{}".format (TlsCfg.NODE_RUNDIR, POD_RUNDIR)
        srcdir_map = "--volume={}:{}".format (NODE_SRCDIR, POD_SRCDIR)

        pod_name = get_pod_name (self.testbed, pod_index)
        if client:
            node_iface = traffic_path['client']['iface']
        else:
            node_iface = traffic_path['server']['iface']

        cmd_str = "sudo docker run --cap-add=SYS_PTRACE --security-opt seccomp=unconfined --network=bridge --privileged --name {} -it -d {} {} tlspack/node:latest /bin/bash".format (pod_name, rundir_map, srcdir_map)
        nodecmd (cmd_str)

        pod_ip = get_pod_ip (self.testbed, pod_index)

        cmd_str = "sudo ip link set dev {} up".format(node_iface)
        nodecmd (cmd_str)

        node_macvlan = testbed_info[node_iface]['macvlan']
        cmd_str = "sudo docker network connect {} {}".format(node_macvlan, pod_name)
        nodecmd (cmd_str)

        cmd_str = "sudo docker exec -d {} echo '/rundir/cores/core.%t.%e.%p' | tee /proc/sys/kernel/core_pattern".format(pod_name)
        nodecmd (cmd_str)
        
        cmd_str = "sudo docker exec -d {} /rundir/PodService.py {} {}".format(pod_name, pod_ip, RPC_PORT)
        nodecmd (cmd_str)


    def start(self, _runI):

        testbed_info = self.get_info()

        for uplink in testbed_info['uplink_ifaces']:
            cmd_str = "sudo docker network rm {}".format (testbed_info[uplink]['macvlan'])
            nodecmd (cmd_str)

            cmd_str = "ip link set dev {} up".format (uplink)
            nodecmd (cmd_str)

            cmd_str = "sudo docker network create -d macvlan -o parent={} {} -o macvlan_mode=bridge".format (uplink, testbed_info[uplink]['macvlan'])
            nodecmd (cmd_str)

        # time.sleep(5)
        pod_index = -1
        zone_id = 0
        for traffic_path in testbed_info['traffic_paths']:
            zone_id += 1
            _runI.state = 'Setup Subnets-Zone{}'.format(zone_id)

            #client
            pod_index += 1
            self.start_pod(pod_index, testbed_info, traffic_path, client=True)

            #server
            pod_index += 1
            self.start_pod(pod_index, testbed_info, traffic_path, client=False)

        self.ready = 1


    def stop_pod(self, pod_index):
        pod_name = get_pod_name (self.testbed, pod_index)
        cmd_str = "sudo docker rm -f {}".format (pod_name)
        nodecmd (cmd_str)


    def stop(self):

        testbed_info = self.get_info()

        pod_index = -1
        for traffic_path in testbed_info['traffic_paths']:
            #servers
            pod_index += 1
            self.stop_pod(pod_index)

            #clients
            pod_index += 1
            self.stop_pod(pod_index)

        self.ready = 0


class TlsApp(object):
    def __init__(self):

        self.pod_certs_dir = os.path.join(POD_RUNDIR, 'certs')
        self.pod_lib_dir = os.path.join(POD_RUNDIR, 'lib')

        self.tcpdump = TCPDUMP_FLAG
        self.next_ipaddr = next_ipaddr
        self.stats_iter = None
        
        self.run_uid = str(uuid.uuid4())
        self.next_log_index = 0

        self.runI = None
        self.testbedI = None
        self.app_testbed_type = None


    @staticmethod
    def store_info(infoid, infoj):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        info_table = db[INFO_TABLE]
        try:
            info_table.remove ({'infoid' : infoid})
        except:
            pass
        infoj['infoid'] = infoid
        info_table.insert (infoj)
        infoj.pop('_id', None)
        infoj.pop('infoid', None)

    @staticmethod
    def remove_info(infoid):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        info_table = db[INFO_TABLE]
        info_table.remove ({'infoid' : infoid})

    @staticmethod
    def get_info(infoid):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        info_table = db[INFO_TABLE]
        return info_table.find_one({'infoid' : infoid})

    @staticmethod
    def insert_testbed(testbed, testbed_j):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        testbed_table = db[TESTBED_TABLE]
        testbed_j['testbed'] = testbed
        testbed_table.insert (testbed_j)
        testbed_j.pop('_id', None)
        testbed_j.pop('testbed', None)

    @staticmethod
    def remove_testbed(testbed):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        testbed_table = db[TESTBED_TABLE]
        testbed_table.remove ({'testbed' : testbed})

    @staticmethod
    def restart(node_rundir):
        TlsCfg.NODE_RUNDIR = node_rundir

        nodecmd ("sudo docker ps --filter name=tlspack_* -aq | xargs sudo docker rm -f")

        # nodecmd ("ps aux | grep '[T]lsApp' | awk '{print $2}' | xargs kill -9")
        localcmd("mongod --shutdown --dbpath /rundir/db")
        
        localcmd("rm -rf /rundir/db/*")
        localcmd("mongod --noauth --dbpath /rundir/db &")

        time.sleep(5)

        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]

        testbed_table = db[TESTBED_TABLE]
        for areana in os.listdir('/rundir/arenas'):
            next_arena_file = '/rundir/arenas/'+areana
            with open (next_arena_file) as f:
                try:
                    next_arena = json.load(f)
                except:
                    continue
                next_arena.pop('modified', None)
                TlsApp.insert_testbed (areana, next_arena)

            with open (next_arena_file, 'w') as f:
                next_arena['modified'] = 0
                f.write(json.dumps(next_arena))

        info_table = db[INFO_TABLE]
        for infoid in os.listdir('/rundir/store'):
            next_info_file = '/rundir/store/'+infoid
            with open (next_info_file) as f:
                try:
                    next_info = json.load(f)
                except:
                    continue
                TlsApp.store_info (infoid, next_info)

    @staticmethod
    def create_config(package, app_name, testbed, **app_kwargs):
        app_module = importlib.import_module ('.'+app_name, package=package)
        app_class = getattr(app_module, app_name)
        app = app_class ()
        config_j = app.create_config (testbed, **app_kwargs)
        return config_j

    @staticmethod
    def start_run (package, app_name, testbed, runid, **app_kwargs):
        app_module = importlib.import_module ('.'+app_name, package=package)
        app_class = getattr(app_module, app_name)
        app = app_class ()
        app.start_run (testbed, runid, **app_kwargs)
        return app

    @staticmethod
    def stop_run(runid):
        _runI = TlsAppRun (runid, new_run=False)

        if not _runI or not _runI.testbed:
            raise TlsAppError(-1, 'error: not running')

        testbed_class_name = TlsAppTestbed(_runI.testbed).type + 'Testbed'
        testbed_class = getattr(sys.modules[__name__], testbed_class_name)
        _testbedI = testbed_class (_runI.testbed)

        app_class_name = TlsAppTestbed(_runI.testbed).type
        app_class = getattr(sys.modules[__name__], app_class_name)

        app_class.stop_run(runid)

    @staticmethod
    def stats_iter(runid):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)

        db = mongoClient[RESULT_DB_NAME]
        stats_col = db[LIVE_STATS_TABLE]

        db = mongoClient[REGISTRY_DB_NAME]
        run_table = db[RUN_TABLE]

        while run_table.find_one ({'runid' : runid}):
            try:
                stats = stats_col.find({'runid' : runid})[0]
            except:
                stats = {}
            yield stats

    @staticmethod
    def run_stats(runid):
        _runI = TlsAppRun (runid, new_run=False)

        mongoClient = MongoClient (TlsCfg.DB_CSTRING)

        db = mongoClient[RESULT_DB_NAME]
        stats_col = db[LIVE_STATS_TABLE]

        try:
            stats = stats_col.find({'runid' : runid}, {'_id': 0})[0]
        except:
            raise TlsAppError(-1, 'stats not found')

        return stats
        
    @staticmethod
    def purge_testbed (testbed):

        testbed_class_name = TlsAppTestbed(testbed).type + 'Testbed'
        testbed_class = getattr(sys.modules[__name__], testbed_class_name)
        _testbedI = testbed_class (testbed)

        if _testbedI.runid:
            TlsApp.stop_run (_testbedI.runid)

        _testbedI.stop()

        TlsApp.remove_testbed (testbed)

    @staticmethod
    def run_list ():
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        run_table = db[RUN_TABLE]
        running_app_list = run_table.find ({}, {'_id': 0})
        if not running_app_list:
            return []
        return list (running_app_list)

    @staticmethod
    def run_state (runid):
        mongoClient = MongoClient (TlsCfg.DB_CSTRING)
        db = mongoClient[REGISTRY_DB_NAME]
        state_table = db[STATE_TABLE]
        return state_table.find_one ({'state_id' : runid}).get('state', '')


    def set_testbed(self, testbed):

        # testbed info
        testbed_class_name = self.app_testbed_type + 'Testbed'
        testbed_class = getattr(sys.modules[__name__], testbed_class_name)
        _testbedI = testbed_class (testbed)

        # testbed compatibility
        if not _testbedI.type == self.app_testbed_type:
            raise TlsAppError(-1
            , 'error: incompatible testbed type {}'.format (_testbedI.type))

        self.testbedI = _testbedI

    def set_traffic_config (self, config_j):

        node_cfg_dir = os.path.join(POD_RUNDIR, 'traffic', self.runI.runid)

        localcmd( 'rm -rf {}'.format(node_cfg_dir) )
        localcmd( 'mkdir -p {}'.format(node_cfg_dir) )
        localcmd( 'mkdir -p {}'.format(os.path.join(node_cfg_dir, 'pcaps')) )
        localcmd( 'mkdir -p {}'.format(os.path.join(node_cfg_dir, 'logs')) )

        node_cfg_file = os.path.join(node_cfg_dir, 'config.json')
        config_s = json.dumps(config_j, indent=2)
        with open(node_cfg_file, 'w') as f:
            f.write(config_s)

        pod_cfg_file = os.path.join(POD_RUNDIR
                                    , 'traffic'
                                    , self.runI.runid
                                    , 'config.json')
        return pod_cfg_file
        
    def stats (self):
        if not self.stats_iter:
            self.stats_iter = TlsApp.stats_iter (self.runI.runid)
        return next (self.stats_iter, None)

    def stop(self):
        if not self.runI or not self.runI.testbed:
            raise TlsAppError(-1, 'error: not started')
        
        TlsApp.stop_run (self.runI.runid)

        self.runI = None
        self.testbedI = None

class TlsCsApp(TlsApp):
    def __init__ (self):
        super().__init__()
        self.app_testbed_type = 'TlsCsApp'

    def start_run (self, testbed, runid, **app_kwargs):

        # runid info
        self.runI = TlsAppRun(runid)

        #testbed
        self.set_testbed (testbed)

        # testbed availability
        if self.testbedI.busy:
            raise TlsAppError(-1
            , 'error: testbed {} in use; running {}'.format \
            (self.testbedI.testbed, self.testbedI.runid))

        self.runI.init_state ('Init')

        # testbed readiness
        if self.testbedI.ready:
            with open('/rundir/arenas/'+self.testbedI.testbed) as f:
                testbed_j = json.load(f)
            if testbed_j.get('modified', 0):
                testbed_j['modified'] = 0
                with open('/rundir/arenas/'+self.testbedI.testbed, 'w') as f:
                    f.write(json.dumps(testbed_j))
                self.runI.state = 'Purging Subnet-Zones'
                TlsApp.purge_testbed (self.testbedI.testbed)
                testbed_j.pop('modified', None)
                TlsApp.insert_testbed(self.testbedI.testbed, testbed_j)

        if not self.testbedI.ready:
            self.testbedI.start(self.runI)

        # time.sleep(5)

        config_j = self.create_config(self.testbedI.testbed, **app_kwargs)

        pod_cfg_file = self.set_traffic_config (config_j)

        testbed_info = self.testbedI.get_info()
        
        # start the server
        self.runI.state = 'Start Servers'
        server_pod_ips = []
        pod_start_threads = []
        pod_index = 1
        for traffic_path in testbed_info['traffic_paths']:

            pod_ip = get_pod_ip (self.testbedI.testbed, pod_index)
            server_pod_ips.append (pod_ip)

            thd = Thread(target=start_run_thread
                        , args=[self.testbedI.testbed
                                , pod_index
                                , pod_cfg_file
                                , [self.testbedI.pod_iface]
                                , pod_ip])
            thd.daemon = True
            thd.start()
            pod_start_threads.append(thd)

            pod_index += 2

        if pod_start_threads:
            for thd in pod_start_threads:
                thd.join()
            # time.sleep(5)


        # start the clients
        self.runI.state = 'Start Clients'
        client_pod_ips = []
        pod_start_threads = []
        pod_index = 0
        for traffic_path in testbed_info['traffic_paths']:

            pod_ip = get_pod_ip (self.testbedI.testbed, pod_index)
            client_pod_ips.append (pod_ip)

            thd = Thread(target=start_run_thread
                        , args=[self.testbedI.testbed
                                , pod_index
                                , pod_cfg_file
                                , [self.testbedI.pod_iface]
                                , pod_ip])
            thd.daemon = True
            thd.start()
            pod_start_threads.append(thd)

            pod_index += 2

        if pod_start_threads:
            for thd in pod_start_threads:
                thd.join()
            # time.sleep(5)

        self.testbedI.runid = self.runI.runid
        self.runI.testbed = self.testbedI.testbed
        self.runI.state = 'running'

        self.runI.stats_pid = start_run_stats (self.runI.runid
                                , server_pod_ips = server_pod_ips
                                , client_pod_ips = client_pod_ips)

    @staticmethod
    def stop_run (runid):
        _runI = TlsAppRun (runid, new_run=False)
        _testbedI = TlsCsAppTestbed (_runI.testbed)

        testbed_info = _testbedI.get_info()

    
        # stop the clients
        _runI.state = 'Stop Clients'
        pod_stop_threads = []
        pod_index = 0
        for traffic_path in testbed_info['traffic_paths']:

            pod_ip = get_pod_ip (_testbedI.testbed, pod_index)

            thd = Thread(target=stop_run_thread
                        , args=[_testbedI.testbed
                                , pod_index
                                , [_testbedI.pod_iface]
                                , pod_ip])
            thd.daemon = True
            thd.start()
            pod_stop_threads.append(thd)
            pod_index += 2

        if pod_stop_threads:
            for thd in pod_stop_threads:
                thd.join()
            # time.sleep(5)


        # stop the servers
        _runI.state = 'Stop Servers'
        pod_stop_threads = []
        pod_index = 1
        for traffic_path in testbed_info['traffic_paths']:

            pod_ip = get_pod_ip (_testbedI.testbed, pod_index)

            thd = Thread(target=stop_run_thread
                        , args=[_testbedI.testbed
                                , pod_index
                                , [_testbedI.pod_iface]
                                , pod_ip])
            thd.daemon = True
            thd.start()
            pod_stop_threads.append(thd)

            pod_index += 2

        if pod_stop_threads:
            for thd in pod_stop_threads:
                thd.join()
            # time.sleep(5)

        stop_run_stats (_runI.stats_pid)

        _runI.state = 'stopped'
        _testbedI.runid = ''
        _runI.dispose ()

def get_pod_stats (pod_ips):
    stats_list = []
    stats_keys = []
    for pod_ip in pod_ips:
        try:
            resp = requests.get('http://{}:{}/ev_sockstats'.format(pod_ip, RPC_PORT))
            stats_j = resp.json()
            stats_list.append (stats_j)
            if stats_j:
                stats_keys = stats_j.keys()
        except:
            stats_list.append ({})

    stats_sum = {}
    for stats_key in stats_keys:
        stats_values = map(lambda s : s.get(stats_key, 0), stats_list) 
        stats_sum[stats_key] = reduce(lambda x, y : x + y, stats_values)

    return (stats_sum, stats_list)

def collect_stats (runid
                    , server_pod_ips
                    , proxy_pod_ips
                    , client_pod_ips):
    max_tick = 1

    mongoClient = MongoClient (TlsCfg.DB_CSTRING)
    db = mongoClient[RESULT_DB_NAME]
    stats_col = db[LIVE_STATS_TABLE]

    stats_col.remove({'runid' : runid})

    tick = 0
    while True:
        tick += 1

        server_stats, server_stats_list  = get_pod_stats (server_pod_ips)
        proxy_stats, proxy_stats_list = get_pod_stats (proxy_pod_ips)
        client_stats, client_stats_list = get_pod_stats (client_pod_ips)
        
        stats_col.insert({'tick' : tick
                                , 'runid' : runid

                                , 'server_stats' : server_stats
                                , 'proxy_stats' : proxy_stats
                                , 'client_stats' : client_stats
                                , 'server_stats_list' : server_stats_list
                                , 'proxy_stats_list' : proxy_stats_list
                                , 'client_stats_list' : client_stats_list
                                
                                })
        if tick > max_tick:
            stats_col.remove({'tick' : tick-max_tick})

        time.sleep(0.1)


def get_arguments ():

    arg_parser = argparse.ArgumentParser(description = 'stats')

    arg_parser.add_argument('--runid'
                                , action="store"
                                , required=True
                                , help = 'run id')
                                
    arg_parser.add_argument('--server_pod_ips'
                                , action="store"
                                , default=''
                                , help = 'run id')

    arg_parser.add_argument('--proxy_pod_ips'
                                , action="store"
                                , default=''
                                , help = 'run id')

    arg_parser.add_argument('--client_pod_ips'
                                , action="store"
                                , default=''
                                , help = 'run id')

    return arg_parser.parse_args()


if __name__ == '__main__':
    c_args = get_arguments ()

    server_pod_ips = c_args.server_pod_ips.split(':')
    proxy_pod_ips = c_args.proxy_pod_ips.split(':')
    client_pod_ips = c_args.client_pod_ips.split(':')

    collect_stats (c_args.runid
                    , server_pod_ips
                    , proxy_pod_ips
                    , client_pod_ips)



        
        
      
