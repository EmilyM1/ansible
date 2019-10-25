#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (c) 2018, KubeVirt Team <@kubevirt>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''

module: k8s_service

short_description: Manage Services on Kubernetes

version_added: "2.8"

author: KubeVirt Team (@kubevirt)

description:
  - Use Openshift Python SDK to manage Services on Kubernetes

extends_documentation_fragment:
  - k8s_auth_options

options:
  resource_definition:
    description:
    - A partial YAML definition of the Service object being created/updated. Here you can define Kubernetes
      Service Resource parameters not covered by this module's parameters.
    - "NOTE: I(resource_definition) has lower priority than module parameters. If you try to define e.g.
      I(metadata.namespace) here, that value will be ignored and I(metadata) used instead."
    aliases:
    - definition
    - inline
    type: dict
  state:
    description:
    - Determines if an object should be created, patched, or deleted. When set to C(present), an object will be
      created, if it does not already exist. If set to C(absent), an existing object will be deleted. If set to
      C(present), an existing object will be patched, if its attributes differ from those specified using
      module options and I(resource_definition).
    default: present
    choices:
    - present
    - absent
  force:
    description:
    - If set to C(True), and I(state) is C(present), an existing object will be replaced.
    default: false
    type: bool
  merge_type:
    description:
    - Whether to override the default patch merge approach with a specific type. By default, the strategic
      merge will typically be used.
    - For example, Custom Resource Definitions typically aren't updatable by the usual strategic merge. You may
      want to use C(merge) if you see "strategic merge patch format is not supported"
    - See U(https://kubernetes.io/docs/tasks/run-application/update-api-object-kubectl-patch/#use-a-json-merge-patch-to-update-a-deployment)
    - Requires openshift >= 0.6.2
    - If more than one merge_type is given, the merge_types will be tried in order
    - If openshift >= 0.6.2, this defaults to C(['strategic-merge', 'merge']), which is ideal for using the same parameters
      on resource kinds that combine Custom Resources and built-in resources. For openshift < 0.6.2, the default
      is simply C(strategic-merge).
    choices:
    - json
    - merge
    - strategic-merge
    type: list
  name:
    description:
      - Use to specify a Service object name.
    required: true
    type: str
  namespace:
    description:
      - Use to specify a Service object namespace.
    required: true
    type: str
  type:
    description:
      - Specifies the type of Service to create.
      - See U(https://kubernetes.io/docs/concepts/services-networking/service/#publishing-services-service-types)
    choices:
      - NodePort
      - ClusterIP
      - LoadBalancer
      - ExternalName
  ports:
    description:
      - A list of ports to expose.
      - U(https://kubernetes.io/docs/concepts/services-networking/service/#multi-port-services)
    type: list
  selector:
    description:
      - Label selectors identify objects this Service should apply to.
      - U(https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/)
    type: dict

requirements:
  - python >= 2.7
  - openshift >= 0.6.2
'''

EXAMPLES = '''
- name: Expose https port with ClusterIP
  k8s_service:
    state: present
    name: test-https
    namespace: default
    ports:
    - port: 443
      protocol: TCP
    selector:
      key: special

- name: Expose https port with ClusterIP using spec
  k8s_service:
    state: present
    name: test-https
    namespace: default
    inline:
      spec:
        ports:
        - port: 443
          protocol: TCP
        selector:
          key: special
'''

RETURN = '''
result:
  description:
  - The created, patched, or otherwise present Service object. Will be empty in the case of a deletion.
  returned: success
  type: complex
  contains:
     api_version:
       description: The versioned schema of this representation of an object.
       returned: success
       type: str
     kind:
       description: Always 'Service'.
       returned: success
       type: str
     metadata:
       description: Standard object metadata. Includes name, namespace, annotations, labels, etc.
       returned: success
       type: complex
     spec:
       description: Specific attributes of the object. Will vary based on the I(api_version) and I(kind).
       returned: success
       type: complex
     status:
       description: Current status details for the object.
       returned: success
       type: complex
'''

import copy
import traceback
import datetime
import kubernetes.config.dateutil

from collections import defaultdict

from ansible.module_utils.k8s.common import AUTH_ARG_SPEC, COMMON_ARG_SPEC
from ansible.module_utils.k8s.raw import KubernetesRawModule
# now = datetime.datetime.utcnow()
# trying = now.isoformat()
now = datetime.datetime.now()
rfc = kubernetes.config.dateutil.format_rfc3339(now)

EVENT_ARG_SPEC = {
    'state': {
        'default': 'present',
        'choices': ['present', 'absent'],
    },
    'name': {'required': True},
    'namespace': {'required': True},
    'merge_type': {'type': 'list', 'choices': ['json', 'merge', 'strategic-merge']},
    'message': {'type':'str', 'required':True},
    'reason': {'type':'str', 'required':True},
    'reportingComponent': {'type': 'str', 'required':True},
    'type': {
        'choices': ['Normal', 'Warning'],
        },
    'source': {'type':'str',
    'component': {'type':'str', 'required':True}},
    'involvedObject': {'type': 'str',
    'apiVersion':{'type': 'str', 'required': True},
    'kind': {'type': 'str', 'required': True},
    'name':{'type': 'str', 'required':True},
    'namespace':{'type': 'str', 'required': True}},

}


class KubernetesEvent(KubernetesRawModule):
    def __init__(self, *args, **kwargs):
        super(KubernetesEvent, self).__init__(*args, k8s_kind='Event', **kwargs)

    # @staticmethod
    # def merge_dicts(x, y):
    #     for k in set(x.keys()).union(y.keys()):
    #         if k in x and k in y:
    #             if isinstance(x[k], dict) and isinstance(y[k], dict):
    #                 yield (k, dict(KubernetesEvent.merge_dicts(x[k], y[k])))
    #             else:
    #                 yield (k, y[k])
    #         elif k in x:
    #             yield (k, x[k])
    #         else:
    #             yield (k, y[k])

    @property
    def argspec(self):
        """ argspec property builder """
        argument_spec = copy.deepcopy(AUTH_ARG_SPEC)
        argument_spec.update(EVENT_ARG_SPEC)
        return argument_spec

    def execute_module(self):
        """ Module execution """
        self.client = self.get_api_client()#mostly auth

        api_version = 'v1'
        name_args = self.params.get('name')
        namespace_args = self.params.get('namespace')
        message = self.params.get('message')
        reason = self.params.get('reason')
        reportingComponent = self.params.get('reportingComponent')
        event_type = self.params.get('type')
        source = self.params.get('source')
#        involvedObject = self.params.get('involvedObject')

        definition = defaultdict(defaultdict)

        def_meta = definition['metadata']
        def_meta['name'] = self.params.get('name')
        def_meta['namespace'] = self.params.get('namespace')

        def_involvedObject = definition['involvedObject']
        def_involvedObject['namespace'] = self.params.get('namespace')
        def_involvedObject['apiVersion'] = self.params.get('apiVersion')
        def_involvedObject['kind'] = self.params.get('kind')
        def_involvedObject['name'] = self.params.get('name')

#        def_involvedObject = definition['involvedObject']
#        def_involvedObject['uuid'] = self.params.get('uid')
#        def_involvedObject['resourceVersion'] = self.params.get('resourceVersion')
        resource = self.find_resource('Event', 'v1', fail=True)#finds resource or gets it from the client api, looks for resrouce
    # second call to find resource for involved object, set kind to arg of involved OBject kind
    #rnewesource = self.find_resource('involvedObjectKind', 'v1', fail=True)

    #this just establishes tha vars and seperates out the reason and count from returned cli object
        priorEvent=resource.get(name=def_meta['name'],
                 namespace=def_meta['namespace'])
        priorReason=priorEvent['reason']
        print(priorReason)
        print("current reason is %s" % reason)
        priorCount = priorEvent['count']
        print("the count from the prior event is %i" % priorCount)

        if priorEvent is not None:
            print(" I giess I can use a bool")
        if priorReason != reason:
            priorCount = priorCount + 1
            print(priorCount)
        else:
            priorCount = 1
            print("If not reason changed %i" % priorCount)

        event = {
       "apiVersion": "v1",#nr
       "count": 18, # not increment up
       "eventTime": None,#nr
       "firstTimestamp":rfc, # dont modifiy it after first time,
       "involvedObject": { #ref to
          "apiVersion": def_involvedObject['apiVersion'],
          "kind": def_involvedObject['kind'],
          "namespace": def_involvedObject['namespace'],
          "name": def_involvedObject['name'],
#          "resourceVersion": "6989176211",
#          "uid": "0f4d7718-b314-11e9-9718-0a580a80006d"
       },
       "kind": "Event", #not returned
       "lastTimestamp": rfc,# creating
       "message": message, # will be can't br hardcoded, user supllied arg
       "metadata": {
          "name": def_meta['name'],
          "namespace": "default",
       },
       "reason": reason, #not hardcoded
       "reportingComponent": reportingComponent,#not returned not ahrdcoded
       "reportingInstance": "1234", #not returned , not hardcoded
       "source":{"component": source}, #not returned source,
         # "component": "Metering Operator", #nh
       "type": event_type #enum service, maybe maybe k8 service
    }

        # selector = self.params.get('selector')
        # service_type = self.params.get('type')
        # ports = self.params.get('ports')
        #
        #
        # definition['kind'] = 'Service'
        # definition['apiVersion'] = api_version
        #
        # def_spec = definition['spec']
        # def_spec['type'] = service_type
        # def_spec['ports'] = ports
        # def_spec['selector'] = selector
        #
        # def_meta = definition['metadata']
        # def_meta['name'] = self.params.get('name')
        # def_meta['namespace'] = self.params.get('namespace')
        #
        # # 'resource_definition:' has lower priority than module parameters
    #    definition = dict(self.merge_dicts(self.resource_definitions[0], definition))
        print("count from CURRENT is %i" % event['count'])

        if priorReason != reason:
            priorCount = priorCount + 1
        #pastexistingEvent = resource.get(name=def_meta['name'],
        #                                  namespace=def_meta['namespace'])
        definition = self.set_defaults(resource, definition)# passes ns,apiversion.kind and name in metadata
        result = self.perform_action(resource, event)# updates if info has changed
        #result = {}
        #print("within execute_module the reason is %s" % reason)
        #the_reason = result.reason
        #print(type(result['reason']))
        # print(priorCount)
        self.exit_json(**result)

    def count_unique_event(reason):
        if event['reason'] != event['reason']: #unsure if specificying old and new enough here
            event['count'] = 1
        else:
            event['count'] +=1
        count = event['count']
        return count

def main():
    module = KubernetesEvent()
    try:
        module.execute_module()
    except Exception as e:
        module.fail_json(msg=str(e), exception=traceback.format_exc())

if __name__ == '__main__':
    main()
