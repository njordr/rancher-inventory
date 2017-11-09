rancher\_inventory
=========================


This script can be used as an Ansible dynamic inventory for Rancher.
The connection parameters are set up via environment variables:

  * RANCHER\_URL: rancher server url (default to http://localhost:8080)
  * RANCHER\_ACCESS\_KEY: access\_key from Rancher API
  * RANCHER\_SECRET\_KEY: secret\_key from Rancher API
  * RANCHER\_API\_PATH: path to Rancher API (default to /v2-beta)

## Variables and Parameters
A global parameter is used for every container: 'ansible\_connection': 'docker' to enable ansible to connect to containers using docker and not ssh.

For every labels found in the services a container hostvar is created.


## Automatic Ansible groups

The script creates  a group for each of these items:
 - project\_<project\_name>
 - stack\_<stack\_name>
 - service\_<service\_name>
 - host\_<host\_name>
 - network\_<network\_name>

It also creates the following groups:
 - subnet\_<subnet\_name>: for every network with a subnet defined a group is created
 - image\_<image\_name>: a group for every docker image used
 - state\_<state\_name>: a group for each state (running, active, stopped, etc.)
 - system: group with all the system containers
 - user: group with all the user containers
 - label\_<label\_name>: a group for each label found in the services

Playbook example
 ```
---
- name: test playbook
  hosts: service_rabbitmq
  remote_user: root
  gather_facts: False
  tasks:
    - raw: "touch /tmp/test"
      args:
        executable: /bin/bash
```

```
ansible-playbook -i rancher_inventory.py simple.yml
```
