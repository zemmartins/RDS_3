#!/usr/bin/env python3
import argparse
import os
import sys
from time import sleep

import grpc

# Import P4Runtime lib from utils dir
# Probably there's a better way of doing this.
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),'../utils/'))

import p4runtime_lib.bmv2
import p4runtime_lib.helper
from p4runtime_lib.error_utils import printGrpcError
from p4runtime_lib.switch import ShutdownAllSwitchConnections

#port mac mapping
port_mac_mapping_r1 = {1: "00:aa:bb:00:00:03", 2: "00:aa:bb:00:00:02", 3:"00:aa:bb:00:00:01"}
port_mac_mapping_r2 = {1: "00:aa:dd:00:00:01", 2: "00:aa:dd:00:00:03", 3:"00:aa:dd:00:00:02"}
port_mac_mapping_r3 = {1: "00:aa:cc:00:00:02", 2: "00:aa:cc:00:00:03", 3:"00:aa:cc:00:00:01"}


def printGrpcError(e):
    print("gRPC Error:", e.details(), end=' ')
    status_code = e.code()
    print("(%s)" % status_code.name, end=' ')
    traceback = sys.exc_info()[2]
    print("[%s:%d]" % (traceback.tb_frame.f_code.co_filename, traceback.tb_lineno))
    if e.debug_error_string():
        print("Debug Error String: %s" % e.debug_error_string())


def readTableRules(p4info_helper, sw):
    """
    Reads the table entries from all tables on the switch.

    :param p4info_helper: the P4Info helper
    :param sw: the switch connection
    """
    print('\n----- Reading tables rules for %s -----' % sw.name)
    for response in sw.ReadTableEntries():
        for entity in response.entities:
            entry = entity.table_entry
            # you can use the p4info_helper to translate
            # the IDs in the entry to names
            table_name = p4info_helper.get_tables_name(entry.table_id)
            print('%s: ' % table_name, end=' ')
            for m in entry.match:
                print(p4info_helper.get_match_field_name(table_name, m.field_id), end=' ')
                print('%r' % (p4info_helper.get_match_field_value(m),), end=' ')
            action = entry.action.action
            action_name = p4info_helper.get_actions_name(action.action_id)
            print('->', action_name, end=' ')
            for p in action.params:
                print(p4info_helper.get_action_param_name(action_name, p.param_id), end=' ')
                print('%r' % p.value, end=' ')
            print()

def writeSrcMac(p4info_helper, sw, port_mac_mapping):
    for port, mac in port_mac_mapping.items():
        table_entry = p4info_helper.buildTableEntry(
            table_name="MyIngress.src_mac",
            match_fields={
                "standard_metadata.egress_spec": port
            },
            action_name="MyIngress.rewrite_src_mac",
            action_params={
                "src_mac": mac
            })
        sw.WriteTableEntry(table_entry)
    print("Installed MAC SRC rules on %s" % sw.name)


def writeFwdRules(p4info_helper, sw, dstAddr, mask, nextHop, port, dstMac):
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ipv4_lpm",
        match_fields={
            "hdr.ipv4.dstAddr": (dstAddr, mask)
        },
        action_name="MyIngress.ipv4_fwd",
        action_params={
            "nxt_hop": nextHop,
            "port": port
        })
    sw.WriteTableEntry(table_entry)

    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.dst_mac",
        match_fields={
            "meta.next_hop_ipv4": nextHop
        },
        action_name="MyIngress.rewrite_dst_mac",
        action_params={
            "dst_mac": dstMac
        })
    sw.WriteTableEntry(table_entry)
    print("Installed FWD rule on %s" % sw.name)



def writeFirewallRules(p4info_helper, sw, srcAddr, mask, dstAddr, protocol, dstPorts, srcPorts):
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.firewall",
        match_fields={
            "hdr.ipv4.srcAddr": (srcAddr, mask),
            "hdr.ipv4.dstAddr": dstAddr,
            "hdr.ipv4.protocol": protocol,
            "hdr.tcp.dstPort": dstPorts,
            "hdr.tcp.srcPort": srcPorts
        },
        action_name="MyIngress.drop",
        action_params = {},
        priority = 1
        )
    sw.WriteTableEntry(table_entry)
    print("Installed firewall on %s" % sw.name)

def printCounter(p4info_helper, sw, counter_name, index):
    for response in sw.ReadCounters(p4info_helper.get_counters_id(counter_name), index):
        for entity in response.entities:
            counter = entity.counter_entry
            print("%s %s %d: %d packets (%d bytes)" % (
                sw.name, counter_name, index,
                counter.data.packet_count, counter.data.byte_count
            ))


def main(p4info_file_path, bmv2_file_path):
    # Instantiate a P4Runtime helper from the p4info file
    p4info_helper = p4runtime_lib.helper.P4InfoHelper(p4info_file_path)

    try:
        # this is backed by a P4Runtime gRPC connection.
        # Also, dump all P4Runtime messages sent to switch to given txt files.
        r1 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='r1',
            address='127.0.0.1:50051',
            device_id=1,
            proto_dump_file='logs/r1-p4runtime-request.txt')
        r2 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='r2',
            address='127.0.0.1:50052',
            device_id=2,
            proto_dump_file='logs/r2-p4runtime-request.txt')
        r3 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name='r3',
            address='127.0.0.1:50053',
            device_id=3,
            proto_dump_file='logs/r3-p4runtime-request.txt')
        print("connection successful")

        # Send master arbitration update message to establish this controller as
        # master (required by P4Runtime before performing any other write operation)
        r1.MasterArbitrationUpdate()
        r2.MasterArbitrationUpdate()
        r3.MasterArbitrationUpdate()


        # Install the P4 program on the switches
        r1.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on r1")
        r2.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on r2")
        r3.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                       bmv2_json_file_path=bmv2_file_path)
        print("Installed P4 Program using SetForwardingPipelineConfig on r3")

        writeSrcMac(p4info_helper, r1, port_mac_mapping_r1)
        writeSrcMac(p4info_helper, r2, port_mac_mapping_r2)
        writeSrcMac(p4info_helper, r3, port_mac_mapping_r3)


        #r1 fwd
        writeFwdRules(p4info_helper, r1, "10.0.1.10",  32, "10.0.1.10",  3, "00:04:00:00:00:20")
        writeFwdRules(p4info_helper, r1, "10.0.1.20",  32, "10.0.1.20",  3, "00:04:00:00:00:30")
        writeFwdRules(p4info_helper, r1, "10.0.1.100", 32, "10.0.1.100", 3, "00:04:00:00:00:01")
        writeFwdRules(p4info_helper, r1, "10.0.2.0",   24, "10.0.5.250", 1, "00:aa:dd:00:00:01")
        writeFwdRules(p4info_helper, r1, "10.0.3.0",   24, "10.0.6.253", 2, "00:aa:cc:00:00:02")
        #r2 fwd
        writeFwdRules(p4info_helper, r2, "10.0.2.10",  32, "10.0.2.10",  3, "00:04:00:00:00:40")
        writeFwdRules(p4info_helper, r2, "10.0.2.20",  32, "10.0.2.20",  3, "00:04:00:00:00:50")
        writeFwdRules(p4info_helper, r2, "10.0.2.100", 32, "10.0.2.100", 3, "00:04:00:00:00:03")
        writeFwdRules(p4info_helper, r2, "10.0.1.0",   24, "10.0.5.251", 1, "00:aa:bb:00:00:03")
        writeFwdRules(p4info_helper, r2, "10.0.3.0",   24, "10.0.4.252", 2, "00:aa:cc:00:00:03")  
        #r3 fwd
        writeFwdRules(p4info_helper, r3, "10.0.3.10",  32, "10.0.3.10",  3, "00:04:00:00:00:60")
        writeFwdRules(p4info_helper, r3, "10.0.3.20",  32, "10.0.3.20",  3, "00:04:00:00:00:70")
        writeFwdRules(p4info_helper, r3, "10.0.3.100", 32, "10.0.3.100", 3, "00:04:00:00:00:02")
        writeFwdRules(p4info_helper, r3, "10.0.1.0",   24, "10.0.6.254", 1, "00:aa:bb:00:00:02")
        writeFwdRules(p4info_helper, r3, "10.0.2.0",   24, "10.0.4.250", 2, "00:aa:dd:00:00:03") 

        
        #r1 firewall
        writeFirewallRules(p4info_helper, r1, "10.0.2.0", 24, "10.0.1.10", 6,  [1,65535], [1,79])
        writeFirewallRules(p4info_helper, r1, "10.0.2.0", 24, "10.0.1.10", 6,  [1,65535], [81,65535])
        writeFirewallRules(p4info_helper, r1, "10.0.2.0", 24, "10.0.1.100", 6, [1,65535], [1,79])
        writeFirewallRules(p4info_helper, r1, "10.0.2.0", 24, "10.0.1.100", 6, [1,65535], [81,65535])
        writeFirewallRules(p4info_helper, r1, "10.0.3.0", 24, "10.0.1.20", 6,  [1,65535], [1,8079])
        writeFirewallRules(p4info_helper, r1, "10.0.3.0", 24, "10.0.1.20", 6,  [1,65535], [8081,65535])
        writeFirewallRules(p4info_helper, r1, "10.0.3.0", 24, "10.0.1.100", 6, [1,65535], [1,8079])
        writeFirewallRules(p4info_helper, r1, "10.0.3.0", 24, "10.0.1.100", 6, [1,65535], [8081,65535])
        writeFirewallRules(p4info_helper, r1, "10.0.2.0", 24, "10.0.1.20", 6,  [1,24], [1,79])
        writeFirewallRules(p4info_helper, r1, "10.0.2.0", 24, "10.0.1.20", 6,  [1,24], [81,65535])
        writeFirewallRules(p4info_helper, r1, "10.0.2.0", 24, "10.0.1.20", 6,  [26,65535], [1,79])
        writeFirewallRules(p4info_helper, r1, "10.0.2.0", 24, "10.0.1.20", 6,  [26,65535], [81,65535])
        writeFirewallRules(p4info_helper, r1, "10.0.3.0", 24, "10.0.1.10", 6,  [1,442], [1,8079])
        writeFirewallRules(p4info_helper, r1, "10.0.3.0", 24, "10.0.1.10", 6,  [1,442], [8081,65535])
        writeFirewallRules(p4info_helper, r1, "10.0.3.0", 24, "10.0.1.10", 6,  [444,65535], [1,8079])
        writeFirewallRules(p4info_helper, r1, "10.0.3.0", 24, "10.0.1.10", 6,  [444,65535], [8081,65535])

        #r2 firewall
        writeFirewallRules(p4info_helper, r2, "10.0.1.0", 24, "10.0.2.20", 6,  [1,65535], [1,24])
        writeFirewallRules(p4info_helper, r2, "10.0.1.0", 24, "10.0.2.20", 6,  [1,65535], [26,65535])
        writeFirewallRules(p4info_helper, r2, "10.0.1.0", 24, "10.0.2.100", 6, [1,65535], [1,24])
        writeFirewallRules(p4info_helper, r2, "10.0.1.0", 24, "10.0.2.100", 6, [1,65535], [26,65535])
        writeFirewallRules(p4info_helper, r2, "10.0.3.0", 24, "10.0.2.10", 6,  [1,65535], [1,442])
        writeFirewallRules(p4info_helper, r2, "10.0.3.0", 24, "10.0.2.10", 6,  [1,65535], [444,65535])
        writeFirewallRules(p4info_helper, r2, "10.0.3.0", 24, "10.0.2.100", 6, [1,65535], [1,442])
        writeFirewallRules(p4info_helper, r2, "10.0.3.0", 24, "10.0.2.100", 6, [1,65535], [444,65535])
        writeFirewallRules(p4info_helper, r2, "10.0.1.0", 24, "10.0.2.10", 6,  [1,79], [1,24])
        writeFirewallRules(p4info_helper, r2, "10.0.1.0", 24, "10.0.2.10", 6,  [1,79], [26,65535])
        writeFirewallRules(p4info_helper, r2, "10.0.1.0", 24, "10.0.2.10", 6,  [81,65535], [1,24])
        writeFirewallRules(p4info_helper, r2, "10.0.1.0", 24, "10.0.2.10", 6,  [81,65535], [26,65535])
        writeFirewallRules(p4info_helper, r2, "10.0.3.0", 24, "10.0.2.20", 6,  [1,21], [1,442])
        writeFirewallRules(p4info_helper, r2, "10.0.3.0", 24, "10.0.2.20", 6,  [1,21], [444,65535])
        writeFirewallRules(p4info_helper, r2, "10.0.3.0", 24, "10.0.2.20", 6,  [23,65535], [1,442])
        writeFirewallRules(p4info_helper, r2, "10.0.3.0", 24, "10.0.2.20", 6,  [23,65535], [444,65535])

        #r3 firewall
        writeFirewallRules(p4info_helper, r3, "10.0.1.0", 24, "10.0.3.20", 6,  [1,65535], [1,442])
        writeFirewallRules(p4info_helper, r3, "10.0.1.0", 24, "10.0.3.20", 6,  [1,65535], [444,65535])
        writeFirewallRules(p4info_helper, r3, "10.0.1.0", 24, "10.0.3.100", 6, [1,65535], [1,442])
        writeFirewallRules(p4info_helper, r3, "10.0.1.0", 24, "10.0.3.100", 6, [1,65535], [444,65535])
        writeFirewallRules(p4info_helper, r3, "10.0.2.0", 24, "10.0.3.10", 6,  [1,65535], [1,21])
        writeFirewallRules(p4info_helper, r3, "10.0.2.0", 24, "10.0.3.10", 6,  [1,65535], [23,65535])
        writeFirewallRules(p4info_helper, r3, "10.0.2.0", 24, "10.0.3.100", 6, [1,65535], [1,21])
        writeFirewallRules(p4info_helper, r3, "10.0.2.0", 24, "10.0.3.100", 6, [1,65535], [23,65535])
        writeFirewallRules(p4info_helper, r3, "10.0.1.0", 24, "10.0.3.10", 6,  [1,8079], [1,442])
        writeFirewallRules(p4info_helper, r3, "10.0.1.0", 24, "10.0.3.10", 6,  [1,8079], [444,65535])
        writeFirewallRules(p4info_helper, r3, "10.0.1.0", 24, "10.0.3.10", 6,  [8081,65535], [1,442])
        writeFirewallRules(p4info_helper, r3, "10.0.1.0", 24, "10.0.3.10", 6,  [8081,65535], [444,65535])
        writeFirewallRules(p4info_helper, r3, "10.0.2.0", 24, "10.0.3.20", 6,  [1,442], [1,21])
        writeFirewallRules(p4info_helper, r3, "10.0.2.0", 24, "10.0.3.20", 6,  [1,442], [23,65535])
        writeFirewallRules(p4info_helper, r3, "10.0.2.0", 24, "10.0.3.20", 6,  [444,65535], [1,21])
        writeFirewallRules(p4info_helper, r3, "10.0.2.0", 24, "10.0.3.20", 6,  [444,65535], [23,65535])


        readTableRules(p4info_helper, r1)
        readTableRules(p4info_helper, r2)
        readTableRules(p4info_helper, r3)


        while True:
            sleep(10)
            print('\n----- Reading counters -----')
            printCounter(p4info_helper, r1, "MyIngress.c", 1)
            printCounter(p4info_helper, r2, "MyIngress.c", 1)
            printCounter(p4info_helper, r3, "MyIngress.c", 1)

    except KeyboardInterrupt:
        print(" Shutting down.")
    except grpc.RpcError as e:
        printGrpcError(e)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='P4Runtime Controller')
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False,
                        default='build/s-router.p4.p4info.txt')
    parser.add_argument('--bmv2-json', help='BMv2 JSON file from p4c',
                        type=str, action="store", required=False,
                        default='build/s-router.json')
    args = parser.parse_args()

    if not os.path.exists(args.p4info):
        parser.print_help()
        print("\np4info file not found:")
        parser.exit(1)
    if not os.path.exists(args.bmv2_json):
        parser.print_help()
        print("\nBMv2 JSON file not found:")
        parser.exit(1)
    main(args.p4info, args.bmv2_json)