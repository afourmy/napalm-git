from __future__ import print_function
from apscheduler.schedulers.blocking import BlockingScheduler
from getpass import getpass
from git import Git, Repo
from logging import basicConfig, DEBUG, exception
from napalm import get_network_driver
from os import environ, makedirs
from os.path import abspath, dirname, exists, join
from sys import argv

source_path = dirname(abspath(__file__))

napalm_dispatcher = (
    # Ax: ASR1000, IOS XE
    ('BNET-A1', 'ios'),
    # ('BNET-A4', 'ios'),
    # C10K, IOS
    # ('BNET-E1', 'ios'),
    # # C7600, IOS
    # ('BNET-I1', 'ios'),
    # # Gx: GSR12K, IOS XR
    # ('BNET-G1', 'ios-xr'),
    # ('BNET-G2', 'ios-xr'),
    # # ASR9K, IOS XR 
    # ('BNET-P1', 'ios-xr'),
    # # Juniper devices, Junos
    # ('BNET-J1', 'junos'),
    # ('BNET-J2', 'junos'),
    )

napalm_getters = (
    ('ARP table', 'get_arp_table'),
    # ('Interfaces counters', 'get_interfaces_counters'),
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
    # ('ISIS neighbors', 'get_isis_neighbors'),
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

def commit_changes(path):
    git_ssh_cmd = 'ssh -i ' + '/home/afourmy/.ssh/id_rsa'
    print(git_ssh_cmd)
    with Git().custom_environment(GIT_SSH_COMMAND=git_ssh_cmd):
        repo = Repo(path)
        repo.git.add(A=True)
        repo.git.commit(m='commit all')
        repo.remotes.origin.push()

def open_device(hostname, os_type, username, password):
    driver = get_network_driver(os_type)
    device = driver(
        hostname = hostname, 
        username = username,
        password = password, 
        optional_args = {'transport': 'telnet'}
        )
    device.open()
    return device

# used for:
# - storing AP Scheduler and netmiko logs 
# - catching exceptions upon storing the getters
def configure_logging():
    basicConfig(filename='logs.log', level=DEBUG)

def store_getters(local_git, username, password):
    for hostname, os_type in napalm_dispatcher:
        try:
            getters_result = {}
            device = open_device(hostname, os_type, username, password)
            path_folder = join(local_git, hostname)
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
                                print(getter_result[conf].encode("utf8"), file=f)
                    else:
                        getters_result[getter_name] = getter_result
                except Exception as e:
                    getters_result[getter_name] = str(e)
            with open(join(path_folder, 'getters'), 'w') as f:
                print(str_dict(getters_result), file=f)
        except Exception as e:
            exception('error with {}: '.format(hostname) + str(e))

def napalm_git_job(local_git, username, password):
    configure_logging()
    store_getters(local_git, username, password)
    commit_changes(local_git)

if __name__ == '__main__':
    # for py2/3 compatibility of input
    try:
        input = raw_input
    except NameError:
        pass
    if argv[1] == 'init':
        remote_git = input('Enter URL of remote git repository: ')
        local_git = input('Enter URL of local folder: ')
        Repo.clone_from(remote_git, local_git)
    if argv[1] == 'schedule':
        local_git = input('Enter URL of local folder: ')
        username = input('Username: ')
        password = getpass()
        seconds = input('Commit every (number of seconds): ')
        scheduler = BlockingScheduler()
        scheduler.add_job(
            napalm_git_job, 
            'interval',
            [local_git, username, password],
            seconds = int(seconds)
            )
        scheduler.start()
