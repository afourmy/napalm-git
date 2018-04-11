from __future__ import print_function
from apscheduler.schedulers.blocking import BlockingScheduler
from getpass import getpass
from git import Git, Repo
from logging import basicConfig, exception, getLogger, INFO, StreamHandler
from multiprocessing.pool import ThreadPool
from napalm import get_network_driver
from os import environ, makedirs
from os.path import abspath, dirname, exists, join
from sys import argv

source_path = dirname(abspath(__file__))

napalm_dispatcher = (
    ('192.168.243.135', 'ios'),
    ('192.168.243.135', 'ios'),
    ('192.168.243.135', 'ios'),
    ('192.168.243.135', 'ios'),
    ('192.168.243.135', 'ios'),
    )

napalm_getters = (
    # ('ARP table', 'get_arp_table'),
    ('Interfaces counters', 'get_interfaces_counters'),
    # ('Facts', 'get_facts'),
    # ('Environment', 'get_environment'),
    # ('Configuration', 'get_config'),
    # ('Interfaces', 'get_interfaces'),
    # ('Interface IP', 'get_interfaces_ip'),
    # ('LLDP neighbors', 'get_lldp_neighbors'),
    # ('LLDP neighbors detail', 'get_lldp_neighbors_detail'),
    # ('MAC address', 'get_mac_address_table'),
    # ('NTP servers', 'get_ntp_servers'),
    # ('NTP statistics', 'get_ntp_stats'),
    # ('Transceivers', 'get_optics'),
    # ('SNMP', 'get_snmp_information'),
    # ('Users', 'get_users'),
    # ('Network instances (VRF)', 'get_network_instances'),
    # ('NTP peers', 'get_ntp_peers'),
    # ('BGP configuration', 'get_bgp_config'),
    # ('BGP neighbors', 'get_bgp_neighbors'),
    # ('IPv6', 'get_ipv6_neighbors_table'),
    )

# pretty-print a dictionnary recursively
def str_dict(input, depth=0):
    tab = '\t'*depth
    if isinstance(input, list):
        result = '\n'
        for element in input:
            result += '{}- {}\n'.format(tab, str_dict(element, depth + 1))
        return result
    elif isinstance(input, dict):
        result = ''
        for key, value in input.items():
            result += '\n{}{}: {}'.format(tab, key, str_dict(value, depth + 1))
        return result
    else:
        return str(input)

def git_commit(local_git):
    repo = Repo(local_git)
    repo.git.add(A=True)
    repo.git.commit(m='commit all')
    repo.remotes.origin.push()

def git_authenticate_and_commit(local_git, ssh_key):
    if ssh_key:
        git_ssh_cmd = 'ssh -i ' + ssh_key
        with Git().custom_environment(GIT_SSH_COMMAND=git_ssh_cmd):
            git_commit(local_git)
    else:
        git_commit(local_git)

def open_device(**kwargs):
    driver = get_network_driver(kwargs['os_type'])
    device = driver(
        hostname = kwargs['hostname'], 
        username = kwargs['username'],
        password = kwargs['password'], 
        optional_args = {'transport': 'telnet'}
        )
    device.open()
    return device

# used for:
# - storing AP Scheduler and netmiko logs 
# - catching exceptions upon storing the getters
def configure_logging():
    log = getLogger('apscheduler.executors.default')
    log.setLevel(INFO)
    h = StreamHandler()
    log.addHandler(h)
    basicConfig(filename='logs.log', level=INFO)

def store_getters_process(kwargs):
    try:
        getters_result = {}
        device = open_device(**kwargs)
        path_folder = join(local_git, kwargs['hostname'])
        # check if the directory associated to the hostname exists
        # if it does not, create it
        if not exists(path_folder):
            makedirs(path_folder)
        for getter_name, getter in napalm_getters:
            try:
                getter_result = getattr(device, getter)()
                # we store the running and startup configurations 
                # in separate unlike other getters
                if getter_name == 'Configuration':
                    for conf in getter_result:
                        # the candidate config is useful only for NAPALM
                        # merge / replace / commit process: there is no
                        # need for storing it
                        if conf == 'candidate':
                            continue
                        filename = conf + '_config'
                        with open(join(path_folder, filename), 'w') as f:
                            f.write(getter_result[conf].encode("utf8"))
                else:
                    getters_result[getter_name] = getter_result
            except Exception as e:
                getters_result[getter_name] = str(e)
        device.close()
        with open(join(path_folder, 'getters'), 'w') as f:
            f.write(str_dict(getters_result))
    except Exception as e:
        exception('error with {}: '.format(kwargs['hostname']) + str(e))

def store_getters(username, password):
    pool = ThreadPool(processes=100)
    kwargs = [({
        'hostname': hostname,
        'os_type': os_type,
        'username': username,
        'password': password
        }) for hostname, os_type in napalm_dispatcher]
    pool.map(store_getters_process, kwargs)
    pool.close()
    pool.join()

def napalm_git_job(username, password):
    configure_logging()
    store_getters(username, password)
    git_authenticate_and_commit(local_git, ssh_key)

if __name__ == '__main__':
    # for py2/3 compatibility of input
    try:
        input = raw_input
    except NameError:
        pass
    if argv[1] == 'init':
        remote_git = input('Enter URL of remote git repository: ')
        local_git = input('Enter URL of local folder (that does not exist yet): ')
        Repo.clone_from(remote_git, local_git)
    if argv[1] == 'schedule':
        local_git = input('Enter URL of local folder: ')
        ssh_key = input('Path to SSH key: ')
        username = input('Username: ')
        password = getpass()
        seconds = input('Commit every (number of seconds): ')
        scheduler = BlockingScheduler()
        scheduler.add_job(
            napalm_git_job, 
            'interval',
            [username, password],
            seconds = int(seconds),
            )
        scheduler.start()
