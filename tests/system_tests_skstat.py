#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License
#

import os
import re
import sys
import unittest
from subprocess import PIPE
from proton import Url, SSLDomain, SSLUnavailable, SASL
from proton.utils import BlockingConnection
from system_test import main_module, TIMEOUT, TestCase, Qdrouterd, Process, Logger
from system_test import CA_CERT, BAD_CA_CERT, SERVER_CERTIFICATE, SERVER_PRIVATE_KEY, CLIENT_CERTIFICATE, \
    CLIENT_PRIVATE_KEY, CLIENT_PASSWORD_FILE, SERVER_PRIVATE_KEY_PASSWORD, CLIENT_PRIVATE_KEY_PASSWORD


class SkstatTestBase(TestCase):
    """Define run_skstat for use with all tests"""

    def run_skstat(self, args, address=None, regex=None, expect=Process.EXIT_OK):
        if args is None:
            args = []
        args = ['skstat',
                '--bus', str(address or self.address()),
                '--timeout', str(TIMEOUT)] + args

        p = self.popen(args, name='skstat-' + self.id(), stdout=PIPE,
                       expect=expect, universal_newlines=True)
        out, err = p.communicate()

        if p.returncode != 0:
            raise RuntimeError("skstat failed: %s (%s, %s)" % (p.returncode,
                                                               out, err))
        if regex is not None:
            pattern = re.compile(regex, re.I)
            self.assertRegex(out, pattern)

        return out

    def address(self):
        """Can be overridden by tests"""
        return self.router.addresses[0]


class SkstatTest(SkstatTestBase):
    """Test skstat tool output"""
    @classmethod
    def setUpClass(cls):
        super(SkstatTest, cls).setUpClass()
        config = Qdrouterd.Config([
            ('router', {'id': 'QDR.A', 'workerThreads': 1}),
            ('listener', {'port': cls.tester.get_port()}),
        ])
        cls.router = cls.tester.qdrouterd('test-router', config)

    def test_help(self):
        self.run_skstat(['--help'], regex=r'Usage: skstat')

    def test_general(self):
        out = self.run_skstat(['--general'],
                              regex=r'(?s)Router Statistics.*Mode\s*Standalone')

        self.assertTrue(re.match(r"(.*)\bConnections\b[ \t]+\b1\b(.*)",
                                 out, flags=re.DOTALL) is not None, out)
        self.assertTrue(re.match(r"(.*)\bNodes\b[ \t]+\b0\b(.*)",
                                 out, flags=re.DOTALL) is not None, out)
        self.assertTrue(re.match(r"(.*)\bAuto Links\b[ \t]+\b0\b(.*)",
                                 out, flags=re.DOTALL) is not None, out)
        self.assertTrue(re.match(r"(.*)\bWorker Threads\b[ \t]+\b1\b(.*)",
                                 out, flags=re.DOTALL) is not None, out)
        self.assertTrue(re.match(r"(.*)\bRouter Id\b[ \t]+\bQDR.A\b(.*)",
                                 out, flags=re.DOTALL) is not None, out)
        self.assertTrue(re.match(r"(.*)\bMode\b[ \t]+\bstandalone\b(.*)",
                                 out, flags=re.DOTALL) is not None, out)
        if sys.platform.lower().startswith('linux'):
            # process memory metrics currently only supported on linux
            self.assertTrue(re.match(r"(.*)\bVmSize\b[ \t]+\b[0-9]+\b(.*)",
                                     out, flags=re.DOTALL) is not None, out)
            self.assertTrue(re.match(r"(.*)\bRSS\b[ \t]+\b[0-9]+\b(.*)",
                                     out, flags=re.DOTALL) is not None, out)

        self.assertEqual(out.count("QDR.A"), 2)

    def test_general_csv(self):
        out = self.run_skstat(['--general', '--csv'],
                              regex=r'(?s)Router Statistics.*Mode","Standalone')

        self.assertIn('"Total Connections","1"', out)
        self.assertIn('"Worker Threads","1"', out)
        self.assertIn('"Nodes","0"', out)
        self.assertIn('"Auto Links","0"', out)
        self.assertIn('"Router Id","QDR.A"', out)
        self.assertIn('"Mode","standalone"', out)
        self.assertIn('"AMQP Service Connections","1"', out)
        self.assertEqual(out.count("QDR.A"), 2)

    def test_connections(self):
        self.run_skstat(['--connections'], regex=r'host.*container.*role')
        outs = self.run_skstat(['--connections'], regex=r'no-auth')
        outs = self.run_skstat(['--connections'], regex=r'QDR.A')

    def test_connections_csv(self):
        self.run_skstat(['--connections', "--csv"], regex=r'host.*container.*role')
        outs = self.run_skstat(['--connections'], regex=r'no-auth')
        outs = self.run_skstat(['--connections'], regex=r'QDR.A')

    def test_links(self):
        self.run_skstat(['--links'], regex=r'QDR.A')
        out = self.run_skstat(['--links'], regex=r'endpoint.*out.*local.*temp.')
        parts = out.split("\n")
        self.assertEqual(len(parts), 9)

    def test_links_csv(self):
        self.run_skstat(['--links', "--csv"], regex=r'QDR.A')
        out = self.run_skstat(['--links'], regex=r'endpoint.*out.*local.*temp.')
        parts = out.split("\n")
        self.assertEqual(len(parts), 9)

    def test_links_with_limit(self):
        out = self.run_skstat(['--links', '--limit=1'])
        parts = out.split("\n")
        self.assertEqual(len(parts), 8)

    def test_links_with_limit_csv(self):
        out = self.run_skstat(['--links', '--limit=1', "--csv"])
        parts = out.split("\n")
        self.assertEqual(len(parts), 7)

    def test_nodes(self):
        self.run_skstat(['--nodes'], regex=r'No Router List')

    def test_nodes_csv(self):
        self.run_skstat(['--nodes', "--csv"], regex=r'No Router List')

    def test_address(self):
        # there are two calls to skstat in order ot verify regex is present
        self.run_skstat(['--address'], regex=r'QDR.A')
        out = self.run_skstat(['--address'], regex=r'\$management')
        parts = out.split("\n")
        self.assertEqual(len(parts), 17,
                         f"Expected 17 lines, got: {parts}")

    def test_address_csv(self):
        # there are two calls to skstat in order ot verify regex is present
        self.run_skstat(['--address'], regex=r'QDR.A')
        out = self.run_skstat(['--address'], regex=r'\$management')
        parts = out.split("\n")
        self.assertEqual(len(parts), 17,
                         f"Expected 17 lines, got: {parts}")

    def test_skstat_no_args(self):
        outs = self.run_skstat(args=None)
        self.assertIn("Presettled Count", outs)
        self.assertIn("Dropped Presettled Count", outs)
        self.assertIn("Accepted Count", outs)
        self.assertIn("Rejected Count", outs)
        self.assertIn("Deliveries from Route Container", outs)
        self.assertIn("Deliveries to Route Container", outs)
        self.assertIn("Egress Count", outs)
        self.assertIn("Ingress Count", outs)
        self.assertIn("Uptime", outs)

    def test_skstat_no_other_args_csv(self):
        outs = self.run_skstat(["--csv"])
        self.assertIn("Presettled Count", outs)
        self.assertIn("Dropped Presettled Count", outs)
        self.assertIn("Accepted Count", outs)
        self.assertIn("Rejected Count", outs)
        self.assertIn("Deliveries from Route Container", outs)
        self.assertIn("Deliveries to Route Container", outs)
        self.assertIn("Egress Count", outs)
        self.assertIn("Ingress Count", outs)
        self.assertIn("Uptime", outs)

    def test_address_priority(self):
        out = self.run_skstat(['--address'])
        lines = out.split("\n")

        # make sure the output contains a header line
        self.assertTrue(len(lines) >= 2)

        # see if the header line has the word priority in it
        priorityregexp = r'pri'
        priority_column = re.search(priorityregexp, lines[4]).start()
        self.assertTrue(priority_column > -1)

        # extract the number in the priority column of every address
        for i in range(6, len(lines) - 1):
            pri = re.findall(r'[-\d]+', lines[i][priority_column:])

            # make sure the priority found is a hyphen or a legal number
            if pri[0] == '-':
                pass  # naked hypnen is allowed
            else:
                self.assertTrue(len(pri) > 0, "Can not find numeric priority in '%s'" % lines[i])
                priority = int(pri[0])
                # make sure the priority is from -1 to 9
                self.assertTrue(priority >= -1, "Priority was less than -1")
                self.assertTrue(priority <= 9, "Priority was greater than 9")

    def test_address_priority_csv(self):
        HEADER_ROW = 4
        PRI_COL = 3
        out = self.run_skstat(['--address', "--csv"])
        lines = out.split("\n")

        # make sure the output contains a header line
        self.assertTrue(len(lines) >= 2)

        # see if the header line has the word priority in it
        header_line = lines[HEADER_ROW].split(',')
        self.assertTrue(header_line[PRI_COL] == '"pri"')

        # extract the number in the priority column of every address
        for i in range(HEADER_ROW + 1, len(lines) - 1):
            line = lines[i].split(',')
            pri = line[PRI_COL][1:-1]  # unquoted value

            # make sure the priority found is a hyphen or a legal number
            if pri == '-':
                pass  # naked hypnen is allowed
            else:
                priority = int(pri)
                # make sure the priority is from -1 to 9
                self.assertTrue(priority >= -1, "Priority was less than -1")
                self.assertTrue(priority <= 9, "Priority was greater than 9")

    def test_address_with_limit(self):
        out = self.run_skstat(['--address', '--limit=1'])
        parts = out.split("\n")
        self.assertEqual(len(parts), 8)

    def test_address_with_limit_csv(self):
        out = self.run_skstat(['--address', '--limit=1', '--csv'])
        parts = out.split("\n")
        self.assertEqual(len(parts), 7)

    def test_memory(self):
        out = self.run_skstat(['--memory'])
        self.assertIn("QDR.A", out)
        self.assertIn("UTC", out)
        regexp = r'qdr_address_t\s+[0-9]+'
        self.assertIsNotNone(re.search(regexp, out, re.I),
                             "Can't find '%s' in '%s'" % (regexp, out))
        if sys.platform.lower().startswith('linux'):
            # process memory metrics currently only supported on linux
            m_regexp = r"(.*)\bVmSize\b[ \t]+\bRSS\b[ \t]+\bPooled\b(.*)"
            self.assertIsNotNone(re.match(m_regexp, out, flags=re.DOTALL), out)

    def test_memory_csv(self):
        out = self.run_skstat(['--memory', '--csv'])
        self.assertIn("QDR.A", out)
        self.assertIn("UTC", out)
        regexp = r'qdr_address_t","[0-9]+'
        assert re.search(regexp, out, re.I), "Can't find '%s' in '%s'" % (regexp, out)

    def test_policy(self):
        out = self.run_skstat(['--policy'])
        self.assertIn("Maximum Concurrent Connections", out)
        self.assertIn("Total Denials", out)

    def test_policy_csv(self):
        out = self.run_skstat(['-p', "--csv"])
        self.assertIn("Maximum Concurrent Connections", out)
        self.assertIn("Total Denials", out)

    def test_log(self):
        self.run_skstat(['--log', '--limit=5'], regex=r'AGENT \(debug\).*GET-LOG')

    def test_yy_query_many_links(self):
        # This test intermittently times out and we are adding log statements to see where the
        # flow actually stops.
        logger = Logger(title="test_yy_query_many_links", print_to_console=True)

        logger.log("Starting test_yy_query_many_links")

        # This test will fail without the fix for DISPATCH-974
        c = BlockingConnection(self.router.addresses[0])
        count = 0
        links = []
        COUNT = 2000

        ADDRESS_SENDER = "examples-sender"
        ADDRESS_RECEIVER = "examples-receiver"

        logger.log("Starting to create senders and receivers")

        while True:
            count += 1
            r = c.create_receiver(ADDRESS_RECEIVER + str(count))
            links.append(r)
            s = c.create_sender(ADDRESS_SENDER + str(count))
            links.append(c)
            if count == COUNT:
                break

        logger.log(f"{count} senders and receivers created")

        # Now we run skstat command and check if we got back details
        # about all the links
        # We do not specify the limit which means unlimited
        # which means get everything that is there.
        outs = self.run_skstat(['--links'])
        out_list = outs.split("\n")

        logger.log("Ran skstat to retrieve all link information from the router")

        out_links = 0
        in_links = 0
        for out in out_list:
            if "endpoint  in" in out and ADDRESS_SENDER in out:
                in_links += 1
            if "endpoint  out" in out and ADDRESS_RECEIVER in out:
                out_links += 1

        self.assertEqual(in_links, COUNT)
        self.assertEqual(out_links, COUNT)

        logger.log(f"Number of sender and receiver links match {COUNT}")

        # Run skstat with a limit more than 4,000
        outs = self.run_skstat(['--links', '--limit=6000'])
        out_list = outs.split("\n")

        logger.log("Ran skstat with limit 6000 to retrieve all link information from the router")

        out_links = 0
        in_links = 0
        for out in out_list:
            if "endpoint  in" in out and ADDRESS_SENDER in out:
                in_links += 1
            if "endpoint  out" in out and ADDRESS_RECEIVER in out:
                out_links += 1

        self.assertEqual(in_links, COUNT)
        self.assertEqual(out_links, COUNT)

        logger.log(f"Number of sender and receiver links still match {COUNT}")

        # Run skstat with a limit less than 4000
        count = 1500
        outs = self.run_skstat(['--links', '--limit=' + str(count)])
        out_list = outs.split("\n")

        logger.log("Ran skstat with limit " + str(count) + " to retrieve link information from the router")

        links = 0
        for out in out_list:
            if "endpoint" in out and "examples" in out:
                links += 1

        self.assertEqual(links, count)

        logger.log("Number of sender and receiver links match " + str(count))

        # Run skstat --csv with a limit less than 4000
        # repeat with --csv
        outs = self.run_skstat(['--links', '--limit=2000', '--csv'])
        out_list = outs.split("\n")

        logger.log("Ran skstat with limit 2000 and csv option to retrieve link information from the router")

        links = 0
        for out in out_list:
            if "endpoint" in out and "examples" in out:
                links += 1

        self.assertEqual(links, 2000)

        logger.log("Number of sender and receiver links still match 2000")

        # Run skstat with a limit of 700 because 700
        # is the maximum number of rows we get per request
        outs = self.run_skstat(['--links', '--limit=700'])
        out_list = outs.split("\n")

        logger.log("Ran skstat with limit 700 to retrieve link information from the router")

        links = 0
        for out in out_list:
            if "endpoint" in out and "examples" in out:
                links += 1

        self.assertEqual(links, 700)

        logger.log("Number of sender and receiver links match 700")

        # Run skstat with a limit of 700 because 700
        # is the maximum number of rows we get per request
        # repeat with --csv
        outs = self.run_skstat(['--links', '--limit=700', '--csv'])
        out_list = outs.split("\n")

        logger.log("Ran skstat with limit 700 and csv option to retrieve    link information from the router")

        links = 0
        for out in out_list:
            if "endpoint" in out and "examples" in out:
                links += 1

        self.assertEqual(links, 700)

        logger.log("Number of sender and receiver links still match 700")
        count = 200
        # Run skstat with a limit of 200 because 700
        # is the maximum number of rows we get per request
        # and we want to try something less than 700
        outs = self.run_skstat(['--links', '--limit=' + str(count)])
        out_list = outs.split("\n")

        logger.log("Ran skstat with limit " + str(count) + " to retrieve link information from the router")

        links = 0
        for out in out_list:
            if "endpoint" in out and "examples" in out:
                links += 1

        self.assertEqual(links, count)

        logger.log("Number of sender and receiver links match " + str(count))

        # Run skstat with a limit of 500 because 700
        # is the maximum number of rows we get per request
        # and we want to try something less than 700
        # repeat with --csv

        outs = self.run_skstat(['--links', '--limit=' + str(count), '--csv'])
        out_list = outs.split("\n")

        logger.log('Ran skstat with limit ' + str(count) + 'and csv option to retrieve all link information from the router')

        links = 0
        for out in out_list:
            if "endpoint" in out and "examples" in out:
                links += 1

        self.assertEqual(links, count)

        logger.log(f"Number of sender and receiver links still match {count}")

        # DISPATCH-1485. Try to run skstat with a limit=0. Without the fix for DISPATCH-1485
        # this following command will hang and the test will fail.
        outs = self.run_skstat(['--links', '--limit=0'])
        out_list = outs.split("\n")

        logger.log("Ran skstat with limit 0 to retrieve all link information from the router")

        links = 0
        for out in out_list:
            if "endpoint" in out and "examples" in out:
                links += 1
        self.assertEqual(links, COUNT * 2)

        logger.log(f"Number of sender and receiver links match {COUNT}")

        # DISPATCH-1485. Try to run skstat with a limit=0. Without the fix for DISPATCH-1485
        # this following command will hang and the test will fail.
        # repeat with --csv
        outs = self.run_skstat(['--links', '--limit=0', '--csv'])
        out_list = outs.split("\n")

        logger.log("Ran skstat with limit 0 and csv option to retrieve all link information from the router")

        links = 0
        for out in out_list:
            if "endpoint" in out and "examples" in out:
                links += 1
        self.assertEqual(links, COUNT * 2)

        logger.log(f"Number of sender and receiver links still match {COUNT}")

        # This test would fail without the fix for DISPATCH-974
        outs = self.run_skstat(['--address'])
        out_list = outs.split("\n")

        logger.log("Ran skstat --address to retrieve all address information from the router")

        sender_addresses = 0
        receiver_addresses = 0
        for out in out_list:
            if ADDRESS_SENDER in out:
                sender_addresses += 1
            if ADDRESS_RECEIVER in out:
                receiver_addresses += 1

        self.assertEqual(sender_addresses, COUNT)
        self.assertEqual(receiver_addresses, COUNT)

        logger.log(f"Number of sender and receiver addresses match {COUNT}")

        # Test if there is a non-zero uptime for the router in the output of
        # skstat -g
        non_zero_seconds = False
        outs = self.run_skstat(args=None)

        logger.log("Ran skstat with no options")

        parts = outs.split("\n")
        for part in parts:
            if "Uptime" in part:
                uptime_parts = part.split(" ")
                for uptime_part in uptime_parts:
                    if uptime_part.startswith("000"):
                        time_parts = uptime_part.split(":")
                        if int(time_parts[3]) > 0:
                            non_zero_seconds = True
                        if not non_zero_seconds:
                            if int(time_parts[2]) > 0:
                                non_zero_seconds = True
        self.assertTrue(non_zero_seconds)

        logger.log("Uptime test successful, end test")

        c.close()


class SkstatTestVhostPolicy(SkstatTestBase):
    """Test skstat-with-policy tool output"""
    @classmethod
    def setUpClass(cls):
        super(SkstatTestVhostPolicy, cls).setUpClass()
        config = Qdrouterd.Config([
            ('router', {'id': 'QDR.A', 'workerThreads': 1}),
            ('listener', {'port': cls.tester.get_port()}),
            ('policy', {'maxConnections': 100, 'enableVhostPolicy': 'true'}),
            ('vhost', {
                'hostname': '$default',
                'maxConnections': 2,
                'allowUnknownUser': 'true',
                'groups': {
                    '$default': {
                        'users': '*',
                        'remoteHosts': '*',
                        'sources': '*',
                        'targets': '*',
                        'allowDynamicSource': True
                    },
                    'HGCrawler': {
                        'users': 'Farmers',
                        'remoteHosts': '*',
                        'sources': '*',
                        'targets': '*',
                        'allowDynamicSource': True
                    },
                },
            })
        ])
        cls.router = cls.tester.qdrouterd('test-router', config)

    def test_vhost(self):
        out = self.run_skstat(['--vhosts'])
        self.assertIn("Vhosts", out)
        self.assertIn("allowUnknownUser", out)

    def test_vhost_csv(self):
        out = self.run_skstat(['--vhosts', '--csv'])
        self.assertIn("Vhosts", out)
        self.assertIn("allowUnknownUser", out)

    def test_vhostgroups(self):
        out = self.run_skstat(['--vhostgroups'])
        self.assertIn("Vhost Groups", out)
        self.assertIn("allowAdminStatusUpdate", out)
        self.assertIn("Vhost '$default' UserGroup '$default'", out)
        self.assertIn("Vhost '$default' UserGroup 'HGCrawler'", out)

    def test_vhostgroups_csv(self):
        out = self.run_skstat(['--vhostgroups', '--csv'])
        self.assertIn("Vhost Groups", out)
        self.assertIn("allowAdminStatusUpdate", out)
        self.assertIn("Vhost '$default' UserGroup '$default'", out)
        self.assertIn("Vhost '$default' UserGroup 'HGCrawler'", out)

    def test_vhoststats(self):
        out = self.run_skstat(['--vhoststats'])
        self.assertIn("Vhost Stats", out)
        self.assertIn("maxMessageSizeDenied", out)
        self.assertIn("Vhost User Stats", out)
        self.assertIn("remote hosts", out)

    def test_vhoststats_csv(self):
        out = self.run_skstat(['--vhoststats', '--csv'])
        self.assertIn("Vhost Stats", out)
        self.assertIn("maxMessageSizeDenied", out)
        self.assertIn("Vhost User Stats", out)
        self.assertIn("remote hosts", out)


class SkstatLinkPriorityTest(SkstatTestBase):
    """Need 2 routers to get inter-router links for the link priority test"""
    @classmethod
    def setUpClass(cls):
        super(SkstatLinkPriorityTest, cls).setUpClass()
        cls.inter_router_port = cls.tester.get_port()
        config_1 = Qdrouterd.Config([
            ('router', {'mode': 'interior', 'id': 'R1'}),
            ('listener', {'port': cls.tester.get_port()}),
            ('connector', {'role': 'inter-router', 'port': cls.inter_router_port})
        ])
        config_2 = Qdrouterd.Config([
            ('router', {'mode': 'interior', 'id': 'R2'}),
            ('listener', {'port': cls.tester.get_port()}),
            ('listener', {'role': 'inter-router', 'port': cls.inter_router_port}),
        ])
        cls.router_2 = cls.tester.qdrouterd('test_router_2', config_2, wait=True)
        cls.router_1 = cls.tester.qdrouterd('test_router_1', config_1, wait=True)
        cls.router_1.wait_router_connected('R2')
        cls.router_2.wait_router_connected('R1')

    def address(self):
        return self.router_1.addresses[0]

    def test_link_priority(self):
        out = self.run_skstat(['--links'])
        lines = out.split("\n")

        # make sure the output contains a header line
        self.assertTrue(len(lines) >= 2)

        # see if the header line has the word priority in it
        priorityregexp = r'pri'
        priority_column = re.search(priorityregexp, lines[4]).start()
        self.assertTrue(priority_column > -1)

        # extract the number in the priority column of every inter-router link
        priorities = {}
        for i in range(6, len(lines) - 1):
            if re.search(r'inter-router', lines[i]):
                pri = re.findall(r'[-\d]+', lines[i][priority_column:])
                # make sure the priority found is a number
                self.assertTrue(len(pri) > 0, "Can not find numeric priority in '%s'" % lines[i])
                self.assertTrue(pri[0] != '-')  # naked hypen disallowed
                priority = int(pri[0])
                # make sure the priority is from 0 to 9
                self.assertTrue(priority >= 0, "Priority was less than 0")
                self.assertTrue(priority <= 9, "Priority was greater than 9")

                # mark this priority as present
                priorities[priority] = True

        # make sure that all priorities are present in the list (currently 0-9)
        self.assertEqual(len(priorities.keys()), 10, "Not all priorities are present")

    def test_link_priority_csv(self):
        HEADER_ROW = 4
        TYPE_COL = 0
        PRI_COL = 7
        out = self.run_skstat(['--links', '--csv'])
        lines = out.split("\n")

        # make sure the output contains a header line
        self.assertTrue(len(lines) >= 2)

        # see if the header line has the word priority in it
        header_line = lines[HEADER_ROW].split(',')
        self.assertEqual(header_line[PRI_COL], '"pri"')

        # extract the number in the priority column of every inter-router link
        priorities = {}
        for i in range(HEADER_ROW + 1, len(lines) - 1):
            line = lines[i].split(',')
            if line[TYPE_COL] == '"inter-router"':
                pri = line[PRI_COL][1:-1]
                # make sure the priority found is a number
                self.assertTrue(len(pri) > 0, "Can not find numeric priority in '%s'" % lines[i])
                self.assertTrue(pri != '-')  # naked hypen disallowed
                priority = int(pri)
                # make sure the priority is from 0 to 9
                self.assertTrue(priority >= 0, "Priority was less than 0")
                self.assertTrue(priority <= 9, "Priority was greater than 9")

                # mark this priority as present
                priorities[priority] = True

        # make sure that all priorities are present in the list (currently 0-9)
        self.assertEqual(len(priorities.keys()), 10, "Not all priorities are present")

    def _test_links_all_routers(self, command):
        out = self.run_skstat(command)
        self.assertEqual(out.count('UTC'), 1)
        self.assertTrue(out.count('Router Links') == 2)
        self.assertTrue(out.count('inter-router') == 40)
        self.assertTrue(out.count('router-control') == 4)

    def test_links_all_routers(self):
        self._test_links_all_routers(['--links', '--all-routers'])

    def test_links_all_routers_csv(self):
        self._test_links_all_routers(['--links', '--all-routers', '--csv'])

    def _test_all_entities(self, command):
        out = self.run_skstat(command)

        self.assertEqual(2, out.count('UTC'))
        self.assertEqual(1, out.count('Router Links'))
        self.assertEqual(1, out.count('Router Addresses'))
        self.assertEqual(1, out.count('Total Connections'))
        self.assertEqual(2, out.count('AutoLinks'))
        self.assertEqual(1, out.count('Router Statistics'))
        self.assertEqual(1, out.count('Memory Pools'))
        self.assertEqual(1, out.count('AMQP Service Connections'))

    def test_all_entities(self):
        self._test_all_entities(['--all-entities'])

    def test_all_entities_csv(self):
        self._test_all_entities(['--all-entities', '--csv'])

    def _test_all_entities_all_routers(self, command):
        out = self.run_skstat(command)

        self.assertEqual(3, out.count('UTC'))
        self.assertEqual(2, out.count('Router Links'))
        self.assertEqual(2, out.count('Router Addresses'))
        self.assertEqual(2, out.count('Total Connections'))
        self.assertEqual(4, out.count('AutoLinks'))
        self.assertEqual(2, out.count('Router Statistics'))
        self.assertEqual(2, out.count('Memory Pools'))
        self.assertEqual(2, out.count('AMQP Service Connections'))

    def test_all_entities_all_routers(self):
        self._test_all_entities_all_routers(['--all-entities', '--all-routers'])

    def test_all_entities_all_routers_csv(self):
        self._test_all_entities_all_routers(['--all-entities', '--csv', '--all-routers'])


def _has_ssl():
    try:
        SSLDomain(SSLDomain.MODE_CLIENT)
        return True
    except SSLUnavailable:
        return False


@unittest.skipIf(_has_ssl() is False, "Proton SSL support unavailable")
class SkstatSslTest(SkstatTestBase):
    """Test skstat tool output"""

    @classmethod
    def setUpClass(cls):
        super(SkstatSslTest, cls).setUpClass()
        # Write SASL configuration file:
        with open('tests-mech-EXTERNAL.conf', 'w') as sasl_conf:
            sasl_conf.write("mech_list: EXTERNAL ANONYMOUS DIGEST-MD5 PLAIN\n")
        # qdrouterd configuration.  Note well: modifying the order of
        # listeners will require updating ssl_test()
        cls.strict_port = cls.tester.get_port()
        config = Qdrouterd.Config([
            ('router', {'id': 'QDR.B',
                        'saslConfigDir': os.getcwd(),
                        'workerThreads': 1,
                        'saslConfigName': 'tests-mech-EXTERNAL'}),
            ('sslProfile', {'name': 'server-ssl',
                            'caCertFile': CA_CERT,
                            'certFile': SERVER_CERTIFICATE,
                            'privateKeyFile': SERVER_PRIVATE_KEY,
                            'password': SERVER_PRIVATE_KEY_PASSWORD}),

            # 'none', 'none_s':
            ('listener', {'host': 'localhost', 'port': cls.tester.get_port()}),

            # 'strict', 'strict_s':
            ('listener', {'host': 'localhost', 'port': cls.strict_port, 'sslProfile': 'server-ssl',
                          'authenticatePeer': 'no', 'requireSsl': 'yes'}),

            # 'unsecured', 'unsecured_s':
            ('listener', {'host': 'localhost', 'port': cls.tester.get_port(), 'sslProfile': 'server-ssl',
                          'authenticatePeer': 'no', 'requireSsl': 'no'}),

            # 'auth', 'auth_s':
            ('listener', {'host': 'localhost', 'port': cls.tester.get_port(), 'sslProfile': 'server-ssl',
                          'authenticatePeer': 'yes', 'requireSsl': 'yes',
                          'saslMechanisms': 'EXTERNAL'})
        ])
        cls.router = cls.tester.qdrouterd('test-router', config)

    def get_ssl_args(self):
        """A map of short names to the corresponding skstat arguments.  A list
        of keys are passed to ssl_test() via the arg_names parameter list.
        """
        args = dict(
            sasl_external=['--sasl-mechanisms', 'EXTERNAL'],
            trustfile=['--ssl-trustfile', CA_CERT],
            bad_trustfile=['--ssl-trustfile', BAD_CA_CERT],
            client_cert=['--ssl-certificate', CLIENT_CERTIFICATE],
            client_key=['--ssl-key', CLIENT_PRIVATE_KEY],
            client_pass=['--ssl-password', CLIENT_PRIVATE_KEY_PASSWORD])
        args['client_cert_all'] = args['client_cert'] + args['client_key'] + args['client_pass']

        return args

    def ssl_test(self, url_name, arg_names, expect=Process.EXIT_OK):
        """Run simple SSL connection test with supplied parameters.

        :param url_name: a shorthand name used to select which router
        interface skstat will connect to:
        'none' = No SSL or SASL config
        'strict' = Require SSL, No SASL config
        'unsecured' = SSL not required, SASL not required
        'auth' = Require SASL (external) and SSL

        The '*_s' names simply replace 'amqp:' with 'amqps:' in the
        generated URL.

        See test_ssl_* below.
        """
        args = self.get_ssl_args()
        addrs = [self.router.addresses[i] for i in range(4)]
        urls = dict(zip(['none', 'strict', 'unsecured', 'auth'], addrs))
        urls.update(zip(['none_s', 'strict_s', 'unsecured_s', 'auth_s'],
                        (Url(a, scheme="amqps") for a in addrs)))
        self.run_skstat(['--general'] + sum([args[n] for n in arg_names], []),
                        address=str(urls[url_name]),
                        regex=r'(?s)Router Statistics.*Mode\s*Standalone',
                        expect=expect)

    def ssl_test_bad(self, url_name, arg_names):
        self.assertRaises(RuntimeError, self.ssl_test, url_name, arg_names, Process.EXIT_FAIL)

    # skstat -b amqp://localhost:<port> --general and makes sure
    # the router sends back a valid response.
    def test_ssl_none(self):
        self.ssl_test('none', [])

    # skstat -b amqps://localhost:<port> --general
    # Make sure that the command fails.
    def test_ssl_scheme_to_none(self):
        self.ssl_test_bad('none_s', [])

    # skstat -b amqp://localhost:<port> --general --ssl-certificate /path/to/client-certificate.pem
    # Makes sure the command fails.
    def test_ssl_cert_to_none(self):
        self.ssl_test_bad('none', ['client_cert'])

    # Tries to run the following command on a listener that requires SSL (requireSsl:yes)
    # skstat -b amqp://localhost:<port> --general
    # Makes sure the command fails.
    def test_ssl_none_to_strict(self):
        self.ssl_test_bad('strict', [])

    # skstat -b amqps://localhost:<port> --general
    def test_ssl_schema_to_strict(self):
        self.ssl_test_bad('strict_s', [])

    # skstat -b amqps://localhost:<port> --general --ssl-certificate /path/to/client-certificate.pem
    # --ssl-key /path/to/client-private-key.pem --ssl-password client-password'
    def test_ssl_cert_to_strict(self):
        self.ssl_test_bad('strict_s', ['client_cert_all'])

    # skstat -b amqps://localhost:<port> --general --ssl-trustfile /path/to/ca-certificate.pem
    def test_ssl_trustfile_to_strict(self):
        self.ssl_test('strict_s', ['trustfile'])

    # skstat -b amqps://localhost:<port> --general --ssl-trustfile
    # /path/to/ca-certificate.pem --ssl-certificate /path/to/client-certificate.pem
    # --ssl-key /path/to/client-private-key.pem --ssl-password client-password
    def test_ssl_trustfile_cert_to_strict(self):
        self.ssl_test('strict_s', ['trustfile', 'client_cert_all'])

    # skstat -b amqps://localhost:<port> --general --ssl-trustfile /path/to/bad-ca-certificate.pem
    # Send in a bad ca cert and make sure the test fails.
    def test_ssl_bad_trustfile_to_strict(self):
        self.ssl_test_bad('strict_s', ['bad_trustfile'])

    # Require-auth SSL listener
    # skstat -b amqp://localhost:<port> --general
    # Send in no certs to a 'authenticatePeer': 'yes', 'requireSsl': 'yes' listener and make sure it fails.
    # Also protocol is amqp not amqps
    def test_ssl_none_to_auth(self):
        self.ssl_test_bad('auth', [])

    # skstat -b amqps://localhost:28491 --general
    # Send in no certs to a 'authenticatePeer': 'yes', 'requireSsl': 'yes' listener and make sure it fails.
    def test_ssl_schema_to_auth(self):
        self.ssl_test_bad('auth_s', [])

    # skstat -b amqps://localhost:<port> --general --ssl-trustfile /path/to/ca-certificate.pem'
    # Send in just a trustfile to an 'authenticatePeer': 'yes', 'requireSsl': 'yes' listener and make sure it fails.
    def test_ssl_trustfile_to_auth(self):
        self.ssl_test_bad('auth_s', ['trustfile'])

    # skstat -b amqps://localhost:<port> --general --ssl-certificate /path/to/client-certificate.pem
    # --ssl-key /path/to/client-private-key.pem --ssl-password client-password
    # Without a trustfile, this test fails
    def test_ssl_cert_to_auth(self):
        self.ssl_test_bad('auth_s', ['client_cert_all'])

    # skstat -b amqps://localhost:<port> --general --ssl-trustfile /path/to/ca-certificate.pem
    # --ssl-certificate /path/to/client-certificate.pem
    # --ssl-key /path/to/client-private-key.pem --ssl-password client-password
    # This has everything, the test should pass.
    def test_ssl_trustfile_cert_to_auth(self):
        self.ssl_test('auth_s', ['trustfile', 'client_cert_all'])

    # skstat -b amqps://localhost:<port> --general --ssl-trustfile /path/to/bad-ca-certificate.pem
    # --ssl-certificate /path/to/client-certificate.pem --ssl-key /path/to/client-private-key.pem
    # --ssl-password client-password
    # Bad trustfile should be rejected.
    def test_ssl_bad_trustfile_to_auth(self):
        self.ssl_test_bad('auth_s', ['bad_trustfile', 'client_cert_all'])

    # skstat -b amqps://localhost:<port> --general --sasl-mechanisms EXTERNAL
    # --ssl-certificate /path/to/client-certificate.pem --ssl-key /path/to/client-private-key.pem
    # --ssl-password client-password --ssl-trustfile /path/to/ca-certificate.pem'
    def test_ssl_cert_explicit_external_to_auth(self):
        self.ssl_test('auth_s', ['sasl_external', 'client_cert_all', 'trustfile'])

    # Unsecured SSL listener, allows non-SSL
    # skstat -b amqp://localhost:<port> --general
    def test_ssl_none_to_unsecured(self):
        self.ssl_test('unsecured', [])

    # skstat -b amqps://localhost:<port> --general
    def test_ssl_schema_to_unsecured(self):
        self.ssl_test_bad('unsecured_s', [])

    # skstat -b amqps://localhost:<port> --general --ssl-certificate /path/to/client-certificate.pem --ssl-key
    # /path/to/client-private-key.pem --ssl-password client-password
    # A trustfile is required, test will fail
    def test_ssl_cert_to_unsecured(self):
        self.ssl_test_bad('unsecured_s', ['client_cert_all'])

    # skstat -b amqps://localhost:<port> --general --ssl-trustfile /path/to/ca-certificate.pem'
    # Just send in the trustfile, should be all good.
    def test_ssl_trustfile_to_unsecured(self):
        self.ssl_test('unsecured_s', ['trustfile'])

    # skstat -b amqps://localhost:<port> --general --ssl-trustfile /path/to/ca-certificate.pem
    # --ssl-certificate /path/to/client-certificate.pem --ssl-key /path/to/client-private-key.pem
    # --ssl-password client-password
    # We have everything, this should work.
    def test_ssl_trustfile_cert_to_unsecured(self):
        self.ssl_test('unsecured_s', ['trustfile', 'client_cert_all'])

    # skstat -b amqps://localhost:<port> --general --ssl-trustfile /path/to/bad-ca-certificate.pem']
    # Bad trustfile, test will fail.
    def test_ssl_bad_trustfile_to_unsecured(self):
        self.ssl_test_bad('unsecured_s', ['bad_trustfile'])

    def test_ssl_peer_name_verify_disabled(self):
        """Verify the --ssl-disable-peer-name-verify option"""
        params = self.get_ssl_args()['trustfile']

        # Expect the connection to fail, since the certificate has
        # 'localhost' as the peer name and we used '127.0.0.1' instead.

        with self.assertRaises(RuntimeError,
                               msg="expected fail: host name wrong") as exc:
            self.run_skstat(address="amqps://127.0.0.1:%s" % self.strict_port,
                            args=['--general'] + params, expect=Process.EXIT_FAIL)

        # repeat the same operation but using
        # --ssl-disable--peer-name-verify.  This should succeed:

        self.run_skstat(address="amqps://127.0.0.1:%s" % self.strict_port,
                        args=['--general',
                              '--ssl-disable-peer-name-verify'] + params)


@unittest.skipIf(_has_ssl() is False, "Proton SSL support unavailable")
class SkstatSslTestSslPasswordFile(SkstatSslTest):
    """
    Tests the --ssl-password-file command line parameter
    """

    def get_ssl_args(self):
        args = dict(
            sasl_external=['--sasl-mechanisms', 'EXTERNAL'],
            trustfile=['--ssl-trustfile', CA_CERT],
            bad_trustfile=['--ssl-trustfile', BAD_CA_CERT],
            client_cert=['--ssl-certificate', CLIENT_CERTIFICATE],
            client_key=['--ssl-key', CLIENT_PRIVATE_KEY],
            client_pass=['--ssl-password-file', CLIENT_PASSWORD_FILE])
        args['client_cert_all'] = args['client_cert'] + args['client_key'] + args['client_pass']

        return args


@unittest.skipIf(_has_ssl() is False, "Proton SSL support unavailable")
class SkstatSslNoExternalTest(SkstatTestBase):
    """Test skstat can't connect without sasl_mech EXTERNAL"""

    @classmethod
    def setUpClass(cls):
        super(SkstatSslNoExternalTest, cls).setUpClass()
        # Write SASL configuration file:
        with open('tests-mech-NOEXTERNAL.conf', 'w') as sasl_conf:
            sasl_conf.write("mech_list: ANONYMOUS DIGEST-MD5 PLAIN\n")
        # qdrouterd configuration:
        config = Qdrouterd.Config([
            ('router', {'id': 'QDR.C',
                        'saslConfigDir': os.getcwd(),
                        'workerThreads': 1,
                        'saslConfigName': 'tests-mech-NOEXTERNAL'}),
            ('sslProfile', {'name': 'server-ssl',
                            'caCertFile': CA_CERT,
                            'certFile': SERVER_CERTIFICATE,
                            'privateKeyFile': SERVER_PRIVATE_KEY,
                            'password': SERVER_PRIVATE_KEY_PASSWORD}),
            ('listener', {'port': cls.tester.get_port()}),
            ('listener', {'port': cls.tester.get_port(), 'sslProfile': 'server-ssl', 'authenticatePeer': 'no', 'requireSsl': 'yes'}),
            ('listener', {'port': cls.tester.get_port(), 'sslProfile': 'server-ssl', 'authenticatePeer': 'no', 'requireSsl': 'no'}),
            ('listener', {'port': cls.tester.get_port(), 'sslProfile': 'server-ssl', 'authenticatePeer': 'yes', 'requireSsl': 'yes',
                          'saslMechanisms': 'EXTERNAL'})
        ])
        cls.router = cls.tester.qdrouterd('test-router', config)

    def ssl_test(self, url_name, arg_names, expect=Process.EXIT_OK):
        """Run simple SSL connection test with supplied parameters.
        See test_ssl_* below.
        """
        args = dict(
            trustfile=['--ssl-trustfile', CA_CERT],
            bad_trustfile=['--ssl-trustfile', BAD_CA_CERT],
            client_cert=['--ssl-certificate', CLIENT_CERTIFICATE],
            client_key=['--ssl-key', CLIENT_PRIVATE_KEY],
            client_pass=['--ssl-password', CLIENT_PRIVATE_KEY_PASSWORD])
        args['client_cert_all'] = args['client_cert'] + args['client_key'] + args['client_pass']

        addrs = [self.router.addresses[i] for i in range(4)]
        urls = dict(zip(['none', 'strict', 'unsecured', 'auth'], addrs))
        urls.update(zip(['none_s', 'strict_s', 'unsecured_s', 'auth_s'],
                        (Url(a, scheme="amqps") for a in addrs)))

        self.run_skstat(['--general'] + sum([args[n] for n in arg_names], []),
                        address=str(urls[url_name]),
                        regex=r'(?s)Router Statistics.*Mode\s*Standalone',
                        expect=expect)

    def ssl_test_bad(self, url_name, arg_names):
        self.assertRaises(RuntimeError, self.ssl_test, url_name, arg_names, Process.EXIT_FAIL)

    @unittest.skipIf(not SASL.extended(), "Cyrus library not available. skipping test")
    def test_ssl_cert_to_auth_fail_no_sasl_external(self):
        self.ssl_test_bad('auth_s', ['client_cert_all'])

    def test_ssl_trustfile_cert_to_auth_fail_no_sasl_external(self):
        self.ssl_test_bad('auth_s', ['trustfile', 'client_cert_all'])


if __name__ == '__main__':
    unittest.main(main_module())
