__author__ = 'Shirish Pal'

def get_config (app_name, testbed, **app_params):
    from .TlsApp import TlsApp
    return TlsApp.get_config (__name__
                            , app_name
                            , testbed
                            , **app_params)

def start_run (runid, app_config):
    from .TlsApp import TlsApp
    return TlsApp.start_run (runid, app_config)

def purge_testbed (testbed):
    from .TlsApp import TlsApp
    TlsApp.purge_testbed (testbed)

def stop_run (runid):
    from .TlsApp import TlsApp
    TlsApp.stop_run (runid)

def get_stats (runid):
    from .TlsApp import TlsApp
    return TlsApp.get_stats (runid)

def run_list ():
    from .TlsApp import TlsApp
    return TlsApp.run_list ()

