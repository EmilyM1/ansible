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

module: k8s_events

short_description: Create Kubernetes Events

version_added: "2.8"

author: Emily Moss for Red Hat

description:
  - Create Kubernetes Events for Metering

extends_documentation_fragment:
  - k8s_auth_options

options:
  resource_definition:
    description:
    - A partial YAML definition of the Event object being created/updated. Here you can define Kubernetes
      Event Resource parameters not covered by this module's parameters.
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
      - Use to specify a Event object name.
    required: true
    type: str
  namespace:
    description:
      - Use to specify a Event object namespace.
    required: true
    type: str
  message:
    description:
      - Status for Operation
    required: true
    type: str
  reason:
    description:
      - Reason for the transition into the objects current status
    required: true
    type: str
  reportingComponent:
    description:
      - Component responsible for event
    required: true
    type: str
  type:
    description:
      - Specifies the type of Event to create.
    choices:
      - NodePort
      - ClusterIP
      - LoadBalancer
      - ExternalName
  source:
    description:
      - Component for reporting this Event
    required: true
    type: string
  involvedObject:
    description: ObjectReference
      - Object event is reporting on. ApiVersion, kind, name and namespace are of the involvedObject.
    - apiVersion
      required: true
      type: string
    - kind
      required: true
      type: string
    - name
      required: true
      type: string
    - namespace
      required: true
      type: string

requirements:
  - python >= 2.7
  - openshift >= 0.6.2
'''

EXAMPLES = '''

- name: Create Kubernetes Event
  k8s_events
  state: present
  name: test-https-emily109
  namespace: default
  message: message here
  reason: reason is now different againnnnnnnnnnnn
  reportingComponent: reportingComponents here
  type: Normal
  source:
    component: Metering components
  involvedObject:
    apiVersion: v1
    kind: Event
    name: involvedObject event names
    namespace: default
'''

RETURN = '''
result:
  description:
  - The created, patched, or otherwise present Event object. Will be empty in the case of a deletion.
  returned: success
  type: complex
  contains:
     api_version:
       description: The versioned schema of this representation of an object.
       returned: success
       type: str
     kind:
       description: Always 'Event'.
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
import openshift
#from openshift.dynamic.exceptions import ResourceNotFoundError, ResourceNotUniqueError

from collections import defaultdict

from ansible.module_utils.k8s.common import AUTH_ARG_SPEC, COMMON_ARG_SPEC
from ansible.module_utils.k8s.raw import KubernetesRawModule
# now = datetime.datetime.utcnow()
# trying = now.isoformat()
# now = datetime.datetime.now()
# rfc = kubernetes.config.dateutil.format_rfc3339(now)

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

        definition = defaultdict(defaultdict)

        def_meta = definition['metadata']
        def_meta['name'] = self.params.get('name')
        def_meta['namespace'] = self.params.get('namespace')

        def_involvedObject = definition['involvedObject']
        def_involvedObject['namespace'] = self.params.get('namespace')
        def_involvedObject['apiVersion'] = self.params.get('apiVersion')
        def_involvedObject['kind'] = self.params.get('kind')
        def_involvedObject['name'] = self.params.get('name')
        def_involvedObject['uid'] = self.params.get('uid')
        def_involvedObject['resourceVersion'] = self.params.get('resourceVersion')
        resource = self.find_resource('Event', 'v1', fail=True)#finds resource or gets it from the client api, looks for resrouce
    # second call to find resource for involved object, set kind to arg of involved OBject kind
    #rnewesource = self.find_resource('involvedObjectKind', 'v1', fail=True)

    #this just establishes tha vars and seperates out the reason and count from returned cli object
        priorCount = 1
        try:
            priorEvent=resource.get(name=def_meta['name'],
                 namespace=def_meta['namespace'])
            priorReason=priorEvent['reason']
            print(priorReason)
            print("current reason is %s" % reason)
            priorCount = priorEvent['count']
            print("the count from the prior event is %i" % priorCount)

            if priorEvent is not None and priorReason != reason:
                print("If reason changed %i" % priorCount)
                now = datetime.datetime.now()
                rfc = kubernetes.config.dateutil.format_rfc3339(now)
                firstTimestamp=rfc
                priorCount = 1
                firstTimestamp=rfc
                print("the value of the firstTimestamp new event is", firstTimestamp)
            else:
                #priorCount = 1
                priorCount = priorCount + 1
                print("the reason has changed", priorCount)
        except openshift.dynamic.exceptions.NotFoundError:
            pass

        involvedObject_resourceVersion = "1"
        involvedObject_uid = "1"
        try:
            totalEvent=resource.get(name=def_meta['name'], namespace=def_meta['namespace'])

            if totalEvent is not None:
                involvedObject_output=totalEvent['involvedObject']
                print("im the involvedObject key", involvedObject_output)
                involvedObject_resourceVersion=involvedObject_output['resourceVersion']
                print("I'm the involvedObject resource version key", involvedObject_resourceVersion)

                involvedObject_uid=involvedObject_output['uid']
                print("Im the involvedObject uid", involvedObject_uid)
        except openshift.dynamic.exceptions.NotFoundError:
            pass



        now = datetime.datetime.now()
        rfc = kubernetes.config.dateutil.format_rfc3339(now)
        firstTimestamp=rfc
        print("the value of the firstTimestamp new event is", firstTimestamp)
        try:
            totalEvent=resource.get(name=def_meta['name'], namespace=def_meta['namespace'])
            if totalEvent is not None: #if the event exists
                firstTimestamp=totalEvent['firstTimestamp']
                print("the value of the firstTimestamp old event is", firstTimestamp)
                lastTimestamp=firstTimestamp
            else:
                rfc = kubernetes.config.dateutil.format_rfc3339(now)
                lastTimestamp=rfc
        except openshift.dynamic.exceptions.NotFoundError:
            pass


        event = {
       "apiVersion": "v1",#nr
       "count": priorCount, # not increment up
       "eventTime": None,#nr
       "firstTimestamp":firstTimestamp , # dont modifiy it after first time,
       "involvedObject": { #ref to
          "apiVersion": def_involvedObject['apiVersion'],
          "kind": def_involvedObject['kind'],
          "namespace": def_involvedObject['namespace'],
          "name": def_involvedObject['name'],
           "resourceVersion": involvedObject_resourceVersion,
           "uid": involvedObject_uid
       },
       "kind": "Event", #not returned
       "lastTimestamp": lastTimestamp,# creating
       "message": message,
       "metadata": {
          "name": def_meta['name'],
          "namespace": "default",
       },
       "reason": reason, #not hardcoded
       "reportingComponent": reportingComponent,#not returned not ahrdcoded
       "reportingInstance": "", #not returned , not hardcoded
       "source":{"component": source}, #not returned source,
         # "component": "Metering Operator", #nh
       "type": event_type
    }

        print("count from CURRENT is %i" % event['count'])

        definition = self.set_defaults(resource, definition)# passes ns,apiversion.kind and name in metadata
        result = self.perform_action(resource, event)# updates if info has changed
        self.exit_json(**result)
        # except openshift.dynamic.exceptions.NotFoundError:
        #     print(" no event")


def main():
    module = KubernetesEvent()
    try:
        module.execute_module()
    except Exception as e:
        module.fail_json(msg=str(e), exception=traceback.format_exc())

if __name__ == '__main__':
    main()
