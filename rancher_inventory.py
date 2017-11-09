#!/usr/bin/env python

from __future__ import print_function
import sys
import json
import re
import logging
import requests
import copy
import os
from time import time
from argparse import ArgumentParser
from os import environ
from pprint import pprint
from collections import defaultdict

try:
    import json
except:
    import simplejson as json


logging.basicConfig(format='%(asctime)-15s %(message)s')
LOG = logging.getLogger('RancherInventory')
LOG.setLevel(logging.INFO)
RANCHER_API_PATH='/v2-beta'
RANCHER_URL='http://localhost:8080'


def to_json(in_dict):
    return json.dumps(in_dict, sort_keys=True, indent=2)


class RancherInventory(object):

    def __init__(self, server_url, access_key, secret_key, apipath='/v2-beta'):
        self._server = server_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._apiurl = '{}{}'.format(self._server, apipath)
        self.parse_cli_args()
        self._containers = dict()
        self._projects = dict()
        self._stacks = dict()
        self._services = dict()
        self._hosts = dict()
        self._networks = dict()
        self._subnets = dict()
        self._inventory = {
            '_meta': {'hostvars': {}},
        }
        self._default_vars = {'ansible_connection': 'docker'}

    def parse_cli_args(self):
        parser = ArgumentParser(
            description='Ansible dynamic inventory for OpenStack Ironic')

        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--list', action='store_true',
                           help='List active servers')
        group.add_argument('--host',
                           help='List details about the specific host')

        self.args = parser.parse_args()

    def run(self):
        inventory = self._get_inventory()
        if not inventory:
            return False

        if self.args.host:
            print(json.dumps(self._inventory['_meta']['hostvars'].get(
                self.args.host, dict()), indent=4, sort_keys=True)
            )
        elif self.args.list:
            print(json.dumps(self._inventory, indent=4, sort_keys=True))
        return True

    def _get_key_from_dict(self, haystack, key, value):
        for k, v in haystack.iteritems():
            if v[key] == value:
                return k

        return False

    def _get_inventory(self):
        r = self._get_info()
        if r is None:
            return False


        for cont_id, cont in self._containers.iteritems():
            if 'all' not in self._inventory:
                self._inventory['all'] = {'hosts': [], 'vars': self._default_vars}
            self._inventory['all']['hosts'].append(cont.get('docker_id'))

            if cont.get('host') is not None:
                self._inventory['host_{}'.format(
                    self._hosts[cont['host']]['name']
                )]['hosts'].append(cont.get('docker_id'))
                self._inventory['host_{}'.format(
                    self._hosts[cont['host']]['name']
                )]['vars'] = self._default_vars

            if cont.get('network') is not None:
                self._inventory['network_{}'.format(
                    self._networks[cont['network']]['name']
                )]['hosts'].append(cont.get('docker_id'))
                self._inventory['network_{}'.format(
                    self._networks[cont['network']]['name']
                )]['vars'] = self._default_vars
                subnet_name = self._get_key_from_dict(
                    self._subnets, 'network', cont['network']
                )
                if subnet_name:
                    self._inventory['subnet_{}'.format(
                        subnet_name
                    )]['hosts'].append(cont.get('docker_id'))
                    self._inventory['subnet_{}'.format(
                        subnet_name
                    )]['vars'] = self._default_vars

            if cont.get('image') is not None:
                if 'image_{}'.format(cont['image'])  not in self._inventory:
                    self._inventory['image_{}'.format(cont['image'])] = {'hosts': [], 'vars': self._default_vars}
                self._inventory['image_{}'.format(cont['image'])]['hosts'].append(cont.get('docker_id'))

            if cont.get('projects') is not None:
                for prj in cont['projects']:
                    self._inventory['project_{}'.format(
                        self._projects[prj]['name']
                    )]['hosts'].append(cont.get('docker_id'))
                    self._inventory['project_{}'.format(
                        self._projects[prj]['name']
                    )]['vars'] = self._default_vars

            if cont.get('services') is not None:
                for srv in cont['services']:
                    self._inventory['service_{}'.format(
                        self._services[srv]['name']
                    )]['hosts'].append(cont.get('docker_id'))
                    if cont.get('hostvars') is not None:
                        hostvars = copy.deepcopy(self._default_vars)
                        hostvars.update(cont['hostvars'])
                        self._inventory['service_{}'.format(
                            self._services[srv]['name']
                        )]['vars'] = hostvars
                    else:
                        self._inventory['service_{}'.format(
                            self._services[srv]['name']
                        )]['vars'] = self._default_vars

            if cont.get('stacks') is not None:
                for stack in cont['stacks']:
                    self._inventory['stack_{}'.format(
                        self._stacks[stack]['name']
                    )]['hosts'].append(cont.get('docker_id'))
                    self._inventory['stack_{}'.format(
                        self._stacks[stack]['name']
                    )]['vars'] = self._default_vars

            if cont.get('state') is not None:
                if 'state_{}'.format(cont['state']) not in self._inventory:
                    self._inventory['state_{}'.format(cont['state'])] = {'hosts': [], 'vars': self._default_vars}
                self._inventory['state_{}'.format(cont['state'])]['hosts'].append(cont.get('docker_id'))

            if cont.get('system') is not None:
                if cont['system']:
                    if 'system' not in self._inventory:
                        self._inventory['system'] = {'hosts': [], 'vars': self._default_vars}
                    self._inventory['system']['hosts'].append(cont.get('docker_id'))
                else:
                    if 'user' not in self._inventory:
                        self._inventory['user'] = {'hosts': [], 'vars': self._default_vars}
                    self._inventory['user']['hosts'].append(cont.get('docker_id'))

            if cont.get('labels') is not None:
                for label in cont['labels']:
                    if 'label_{}'.format(label) not in self._inventory:
                        self._inventory['label_{}'.format(label)] = {'hosts': [], 'vars': self._default_vars}
                    self._inventory['label_{}'.format(label)]['hosts'].append(cont.get('docker_id'))

            if cont.get('hostvars') is not None:
                hostvars = copy.deepcopy(self._default_vars)
                hostvars.update(cont['hostvars'])
                self._inventory['_meta']['hostvars'][cont.get('docker_id')] = hostvars
            else:
                self._inventory['_meta']['hostvars'][cont.get('docker_id')] = self._default_vars

        return True

    def _get_info(self):
        prj_list = self._get_projects()
        if prj_list is None:
            return None

        r = self._get_containers(projects=prj_list)
        if r is None:
            return None
        self._containers = copy.deepcopy(r)

        r = self._get_services(projects=prj_list)
        if r is None:
            return None
        self._containers = copy.deepcopy(r)

        r = self._get_stacks(projects=prj_list)
        if r is None:
            return None
        self._containers = copy.deepcopy(r)

        r = self._get_hosts(projects=prj_list)
        if r is None:
            return None
        self._containers = copy.deepcopy(r)

        r = self._get_networks(projects=prj_list)

        return True

    def _get_projects(self):
        """Retrieve all projects (environments) from rancher
        Returns:
            List with all projects. None if call to api fails
        """
        data = self._call_api('/projects')
        projects = []
        if data is None:
            return None

        for prj in data.get('data', []):
            self._projects[prj.get('id')] = {
                'id': prj.get('id'),
                'name': prj.get('name'),
                'state': prj.get('state'),
                'stacks': [],
                'services': [],
                'hosts': {},
                'networks': {}
            }
            projects.append(prj.get('id'))
            self._inventory['project_{}'.format(prj.get('name'))] = {
                'hosts': [], 'vars': self._default_vars
            }

        return projects

    def _get_containers(self, projects):
        """Retrieve containers
        Args
            projects (list): list of projects id
        Returns:
            Dictionary projects updated with all stacks. None if call to api fails
        """
        containers = {}
        for prj in projects:
            data = self._call_api('/projects/{}/containers'.format(prj))
            for cont in data.get('data', []):
                containers[cont.get('id')] = {
                    'id': cont.get('id'),
                    'name': cont.get('name'),
                    'description': cont.get('description'),
                    'type': cont.get('baseType'),
                    'system': cont.get('system', False),
                    'host': cont.get('hostId'),
                    'image': cont.get('imageUuid'),
                    'network': cont.get('primaryNetworkId'),
                    'state': cont.get('state'),
                    'docker_id': cont.get('externalId'),
                    'projects': [prj],
                    'services': [],
                    'service_type': '',
                    'stacks': [],
                    'hosts': [],
                    'networks': [],
                    'labels': [],
                    'hostvars': {
                        'system': cont.get('system', False),
                        'state': cont.get('state')
                    }
                }

        return containers

    def _get_services(self, projects):
        """Retrieve services
        Args
            projects (list): all the projects with id and name ({u'1a7': {'id': u'1a7', 'name': u'TEST'}})
        Returns:
            Dictionary all services. None if call to api fails
        """
        containers = copy.deepcopy(self._containers)
        for prj in projects:
            data = self._call_api('/projects/{}/services'.format(prj))
            for srv in data.get('data', []):
                srv_data = {
                    'id': srv.get('id'),
                    'name': srv.get('name'),
                    'description': srv.get('description'),
                    'type': srv.get('baseType'),
                    'system': srv.get('system', False),
                    'state': srv.get('state'),
                    'containers': [],
                    'service_type': srv.get('type')
                }

                if srv['launchConfig'].get('labels') is not None:
                    srv_data['labels'] = {k: v for k, v in srv['launchConfig']['labels'].iteritems()}
                else:
                    srv_data['labels'] = {}

                if srv.get('instanceIds') is not None:
                    for c in srv['instanceIds']:
                        if c in containers:
                            containers[c]['services'].append(srv_data['id'])
                            containers[c]['labels'].extend(
                                ['{}_{}'.format(k, v) for k, v in srv_data['labels'].iteritems()]
                            )
                            containers[c]['labels'].extend(srv_data['labels'].keys())
                            containers[c]['labels'].extend(srv_data['labels'].values())
                            containers[c]['hostvars'].update(srv_data['labels'])
                            containers[c]['hostvars']['service_type'] = srv_data['service_type']
                    srv_data['containers'] = [v for v in srv['instanceIds']]

                self._services[srv_data['id']] = srv_data
                self._inventory['service_{}'.format(srv_data['name'])] = {
                    'hosts': [], 'vars': self._default_vars
                }

                if srv.get('accountId') is not None:
                    self._projects[srv['accountId']]['services'].append(srv_data['id'])

        return containers

    def _get_stacks(self, projects):
        """Retrieve stacks for every project
        Args:
            projects (dict): all the projects with id and name ({u'1a7': {'id': u'1a7', 'name': u'TEST'}})
        Returns:
            Dictionary with all stacks. None if call to api fails
        """
        containers = copy.deepcopy(self._containers)
        for prj in projects:
            data = self._call_api('/projects/{}/stacks'.format(prj))
            for stack in data.get('data', []):
                stack_data = {
                    'id': stack.get('id'),
                    'name': stack.get('name'),
                    'description': stack.get('description'),
                    'system': stack.get('system', False),
                    'state': stack.get('state'),
                    'services': []
                }
                if stack.get('serviceIds') is not None:
                    stack_data['services'] = [v for v in stack['serviceIds']]
                    for s in stack_data['services']:
                        for c in self._services[s]['containers']:
                            containers[c]['stacks'].append(stack_data['id'])

                self._stacks[stack_data['id']] = stack_data
                self._inventory['stack_{}'.format(stack_data['name'])] = {
                    'hosts': [], 'vars': self._default_vars
                }

                if stack.get('accountId') is not None:
                    self._projects[stack['accountId']]['stacks'].append(stack_data['id'])

        return containers

    def _get_hosts(self, projects):
        """Retrieve hosts for every project
        Args:
            projects (dict): all the projects with id and name ({u'1a7': {'id': u'1a7', 'name': u'TEST'}})
        Returns:
            Dictionary with all stacks. None if call to api fails
        """
        containers = copy.deepcopy(self._containers)
        for prj in projects:
            data = self._call_api('/projects/{}/hosts'.format(prj))
            for host in data.get('data', []):
                host_data = {
                    'id': host.get('id'),
                    'name': host.get('hostname'),
                    'description': host.get('description'),
                    'state': host.get('state'),
                    'ip_address': host.get('agentIpAddress'),
                    'containers': []
                }
                self._hosts[host_data['id']] = host_data

                if host.get('instanceIds') is not None:
                    host_data['containers'] = [v for v in host['instanceIds']]

                self._hosts[host_data['id']] = host_data
                self._inventory['host_{}'.format(host_data['name'])] = {
                    'hosts': [], 'vars': self._default_vars
                }

        return containers

    def _get_networks(self, projects):
        """Retrieve networks for every project
        Args:
            projects (dict): all the projects with id and name ({u'1a7': {'id': u'1a7', 'name': u'TEST'}})
        Returns:
            Dictionary with all stacks. None if call to api fails
        """
        for prj in projects:
            data = self._call_api('/projects/{}/networks'.format(prj))
            for net in data.get('data', []):
                net_data = {
                    'id': net.get('id'),
                    'name': net.get('name'),
                    'description': net.get('description'),
                    'state': net.get('state'),
                    'subnets': []
                }
                if net.get('subnets') is not None:
                    net_data['subnets'] = [v['networkAddress'] for v in net['subnets']]

                self._networks[net_data['id']] = net_data
                self._inventory['network_{}'.format(net_data['name'])] = {
                    'hosts': [], 'vars': self._default_vars
                }
                if net_data['subnets']:
                    for s in net_data['subnets']:
                        self._inventory['subnet_{}'.format(s)] = {
                            'hosts': [], 'vars': self._default_vars
                        }
                        self._subnets[s] = {'name': s, 'network': net_data['id']}

        return True


    def _call_api(self, path):
        headers = {'content-Type': 'application/json'}
        try:
            rest_reply = requests.get(
                '{}{}'.format(self._apiurl, path),
                headers=headers,
                auth=(self._access_key, self._secret_key)
            )
        except Exception as e:
            LOG.error('Error calling REST API: {}'.format(e))
            sys.exit(1)

        if rest_reply.status_code > 299:
            return None

        return rest_reply.json()


def main():
    if os.environ.get('RANCHER_URL') is not None:
        rancher_url = os.environ['RANCHER_URL']
    else:
        rancher_url = RANCHER_URL

    if os.environ.get('RANCHER_ACCESS_KEY') is not None:
        rancher_access_key = os.environ['RANCHER_ACCESS_KEY']
    else:
        LOG.error('Please set RANCHER_ACCESS_KEY env variable')
        sys.exit(1)

    if os.environ.get('RANCHER_SECRET_KEY') is not None:
        rancher_secret_key = os.environ['RANCHER_SECRET_KEY']
    else:
        LOG.error('Please set RANCHER_SECRET_KEY env variable')
        sys.exit(1)

    if os.environ.get('RANCHER_API_PATH') is not None:
        rancher_api_path = os.environ['RANCHER_API_PATH']
    else:
        rancher_api_path = RANCHER_API_PATH

    rancher_inventory = RancherInventory(
        server_url=rancher_url,
        access_key=rancher_access_key,
        secret_key=rancher_secret_key,
        apipath=rancher_api_path
    )
    if rancher_inventory.run():
        sys.exit(0)
    else:
        sys.exit(-1)

if __name__ == "__main__":
    main()

