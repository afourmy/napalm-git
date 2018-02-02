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
    ('192.168.1.88', 'ios'),
    )

napalm_getters = (
    ('ARP table', 'get_arp_table'),
    ('Interfaces counters', 'get_interfaces_counters'),
    ('Facts', 'get_facts'),
    ('Environment', 'get_environment'),
    ('Configuration', 'get_config'),
    ('Interfaces', 'get_interfaces'),
    ('Interface IP', 'get_interfaces_ip'),
    ('LLDP neighbors', 'get_lldp_neighbors'),
    ('LLDP neighbors detail', 'get_lldp_neighbors_detail'),
    ('MAC address', 'get_mac_address_table'),
    ('NTP servers', 'get_ntp_servers'),
    ('NTP statistics', 'get_ntp_stats'),
    ('Transceivers', 'get_optics'),
    ('SNMP', 'get_snmp_information'),
    ('Users', 'get_users'),
    ('Network instances (VRF)', 'get_network_instances'),
    ('NTP peers', 'get_ntp_peers'),
    ('BGP configuration', 'get_bgp_config'),
    ('BGP neighbors', 'get_bgp_neighbors'),
    ('IPv6', 'get_ipv6_neighbors_table'),
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

def napalm_git_job(local_git, username, password, ssh_key):
    configure_logging()
    store_getters(local_git, username, password)
    git_authenticate_and_commit(local_git, ssh_key)

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
        ssh_key = input('Path to SSH key: ')
        username = input('Username: ')
        password = getpass()
        seconds = input('Commit every (number of seconds): ')
        scheduler = BlockingScheduler()
        scheduler.add_job(
            napalm_git_job, 
            'interval',
            [local_git, username, password, ssh_key],
            seconds = int(seconds)
            )
        scheduler.start()
