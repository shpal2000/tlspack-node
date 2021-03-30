__author__ = 'Shirish Pal'

from .TlsApp import TlsCsApp

import os
import jinja2
import json


class TlsCps(TlsCsApp):

    def __init__(self, is_dev=False):
        super().__init__()

        self.client_module = 'libtls_client_perf.so'
        self.server_module = 'libtls_server_perf.so'

        self.max_active = 100
        self.max_pipeline = 100
        self.tcp_snd_buff = 0
        self.tcp_rcv_buff = 0
        self.app_snd_buff = 0
        self.app_rcv_buff = 0
        self.app_next_write = 0
        self.app_cs_starttls_len = 0
        self.app_sc_starttls_len = 0
        self.app_cs_data_len = 128
        self.app_sc_data_len = 128
        self.total_conn_count = 0
        self.close_type = 'fin'
        self.close_notify = 'no_send'
        self.client_port_begin = 5000
        self.client_port_end = 65000
        self.resumption_count = 10
        self.session_cache = "server"

    def create_config (self
                , testbed
                , cps
                , cipher
                , version
                , srv_cert
                , srv_key
                , resumption_count
                , session_cache
                , total_conn_count):
        
        self.set_testbed(testbed)

        self.cps = cps / self.testbedI.traffic_path_count
        if  self.cps == 0:
            self.cps = 1

        self.cipher = cipher
        self.version = version
        self.srv_cert = os.path.join(self.pod_certs_dir, srv_cert)
        self.srv_key = os.path.join(self.pod_certs_dir, srv_key)

        self.total_conn_count = total_conn_count / self.testbedI.traffic_path_count
        if self.total_conn_count == 0 and total_conn_count > 0:
            self.total_conn_count = 1
    
        self.resumption_count = resumption_count
        self.session_cache = session_cache

        config_t = jinja2.Template('''{
            "app" : "TlsCps",
            "testbed" : "{{PARAMS.testbedI.testbed}}",
            "zones" : [
                {% set ns = namespace(cs_grp_count=0, srv_count=0) %}
                {%- for traffic_path_index in range(0, PARAMS.testbedI.traffic_path_count) %}
                    {
                        "zone_type" : "client",
                        "zone_label" : "traffic_path_{{traffic_path_index+1}}_client",
                        "enable" : 1,
                        "app_list" : [
                            {
                                "app_type" : "tls_client_perf",
                                "app_lib" : "{{PARAMS.pod_lib_dir.rstrip('/')}}/{{PARAMS.client_module}}",
                                "app_label" : "tls_client_{{traffic_path_index+1}}",
                                "enable" : 1,
                                "conn_per_sec" : {{PARAMS.cps}},
                                "max_pending_conn_count" : {{PARAMS.max_pipeline}},
                                "max_active_conn_count" : {{PARAMS.max_active}},
                                "total_conn_count" : {{PARAMS.total_conn_count}},
                                "cs_grp_list" : [
                                    {% set ns.cs_grp_count = 0 %}
                                    {%- for next_client_list in PARAMS.testbedI.traffic_paths[traffic_path_index]['client']['client_list'] %}
                                        {{ "," if ns.cs_grp_count }}
                                        {% set ns.cs_grp_count = ns.cs_grp_count+1 %}
                                        {
                                            "cs_grp_label" : "{{PARAMS.testbedI.traffic_paths[traffic_path_index]['client']['client_list'][loop.index0]['label']}}",
                                            "enable" : 1,
                                            "srv_ip"   : "{{PARAMS.testbedI.traffic_paths[traffic_path_index]['client']['client_list'][loop.index0]['server_ip']}}",
                                            "srv_port" : {{PARAMS.testbedI.traffic_paths[traffic_path_index]['client']['client_list'][loop.index0]['server_port']}},
                                            "clnt_ip_begin" : "{{PARAMS.testbedI.traffic_paths[traffic_path_index]['client']['client_list'][loop.index0]['client_ip_begin']}}",
                                            "clnt_ip_end" : "{{PARAMS.next_ipaddr(PARAMS.testbedI.traffic_paths[traffic_path_index]['client']['client_list'][loop.index0]['client_ip_begin'], PARAMS.testbedI.traffic_paths[traffic_path_index]['client']['client_list'][loop.index0]['client_ip_count']-1)}}",
                                            "clnt_port_begin" : {{PARAMS.client_port_begin}},
                                            "clnt_port_end" : {{PARAMS.client_port_end}},
                                            "cipher" : "{{PARAMS.cipher}}",
                                            "tls_version" : "{{PARAMS.version}}",
                                            "close_type" : "{{PARAMS.close_type}}",
                                            "close_notify" : "{{PARAMS.close_notify}}",
                                            "app_rcv_buff" : {{PARAMS.app_rcv_buff}},
                                            "app_snd_buff" : {{PARAMS.app_snd_buff}},
                                            "write_chunk" : {{PARAMS.app_next_write}},
                                            "tcp_rcv_buff" : {{PARAMS.tcp_rcv_buff}},
                                            "tcp_snd_buff" : {{PARAMS.tcp_snd_buff}},
                                            "cs_data_len" : {{PARAMS.app_cs_data_len}},
                                            "sc_data_len" : {{PARAMS.app_sc_data_len}},
                                            "cs_start_tls_len" : {{PARAMS.app_cs_starttls_len}},
                                            "sc_start_tls_len" : {{PARAMS.app_sc_starttls_len}},
                                            "resumption_count" : {{PARAMS.resumption_count}},
                                            "session_cache" : "{{PARAMS.session_cache}}"
                                       }
                                    {%- endfor %}                         
                                ]
                            }
                        ],

                        "zone_cmds" : [
                            "ip link set dev {{PARAMS.testbedI.pod_iface}} up",
                            "ifconfig {{PARAMS.testbedI.pod_iface}} hw ether {{PARAMS.testbedI.traffic_paths[traffic_path_index]['client']['gw_mac']}}",
                            "ip route add default dev {{PARAMS.testbedI.pod_iface}} table 200",
                            "ip -4 route add local {{PARAMS.testbedI.traffic_paths[traffic_path_index]['client']['subnets'][0]}} dev lo",
                            "ip rule add from {{PARAMS.testbedI.traffic_paths[traffic_path_index]['client']['subnets'][0]}} table 200"
                        ]
                    }
                    ,
                    {
                        "zone_type" : "server",
                        "zone_label" : "traffic_path_{{traffic_path_index+1}}_server",
                        "enable" : 1,
                        "app_list" : [
                            {
                                "app_type" : "tls_server_perf",
                                "app_lib" : "{{PARAMS.pod_lib_dir.rstrip('/')}}/{{PARAMS.server_module}}",
                                "app_label" : "tls_server_{{traffic_path_index+1}}",
                                "enable" : 1,
                                "srv_list" : [
                                    {% set ns.srv_count = 0 %}
                                    {%- for next_server in PARAMS.testbedI.traffic_paths[traffic_path_index]['server']['server_list'] %}
                                        {{ "," if ns.srv_count }}
                                        {% set ns.srv_count = ns.srv_count+1 %}
                                        {
                                            "srv_label" : "{{PARAMS.testbedI.traffic_paths[traffic_path_index]['server']['server_list'][loop.index0]['label']}}",
                                            "enable" : 1,
                                            "srv_ip" : "{{PARAMS.testbedI.traffic_paths[traffic_path_index]['server']['server_list'][loop.index0]['server_ip']}}",
                                            "srv_port" : {{PARAMS.testbedI.traffic_paths[traffic_path_index]['server']['server_list'][loop.index0]['server_port']}},
                                            "srv_cert" : "{{PARAMS.srv_cert}}",
                                            "srv_key" : "{{PARAMS.srv_key}}",
                                            "cipher" : "{{PARAMS.cipher}}",
                                            "tls_version" : "{{PARAMS.version}}",
                                            "close_type" : "{{PARAMS.close_type}}",
                                            "close_notify" : "{{PARAMS.close_notify}}",
                                            "app_rcv_buff" : {{PARAMS.app_rcv_buff}},
                                            "app_snd_buff" : {{PARAMS.app_snd_buff}},
                                            "write_chunk" : {{PARAMS.app_next_write}},
                                            "tcp_rcv_buff" : {{PARAMS.tcp_rcv_buff}},
                                            "tcp_snd_buff" : {{PARAMS.tcp_snd_buff}},
                                            "cs_data_len" : {{PARAMS.app_cs_data_len}},
                                            "sc_data_len" : {{PARAMS.app_sc_data_len}},
                                            "cs_start_tls_len" : {{PARAMS.app_cs_starttls_len}},
                                            "sc_start_tls_len" : {{PARAMS.app_sc_starttls_len}},
                                            "resumption_count" : {{PARAMS.resumption_count}},
                                            "session_cache" : "{{PARAMS.session_cache}}"
                                       }
                                    {%- endfor %}
                                ]
                            }
                        ],

                        "zone_cmds" : [
                            "ip link set dev {{PARAMS.testbedI.pod_iface}} up",
                            "ifconfig {{PARAMS.testbedI.pod_iface}} hw ether {{PARAMS.testbedI.traffic_paths[traffic_path_index]['server']['gw_mac']}}",
                            "ip route add default dev {{PARAMS.testbedI.pod_iface}} table 200",
                            "ip -4 route add local {{PARAMS.testbedI.traffic_paths[traffic_path_index]['server']['subnets'][0]}} dev lo",
                            "ip rule add from {{PARAMS.testbedI.traffic_paths[traffic_path_index]['server']['subnets'][0]}} table 200"
                        ]
                    }
                    {{ "," if not loop.last }}
                {%- endfor %}
            ]
        }
        ''')        

        config_s = config_t.render(PARAMS = vars(self))

        config_j = json.loads(config_s)

        return config_j
