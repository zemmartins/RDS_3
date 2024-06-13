#!/usr/bin/env python3

from mininet.net import Mininet
from mininet.topo import Topo
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.node import OVSKernelSwitch

from p4_mininet import P4Switch, P4Host
from p4runtime_switch import P4RuntimeSwitch

import subprocess
import argparse
from time import sleep


class SimpleRouter(Topo):
    def __init__(self, sw_path, thrift_port, grpc_port, **opts):
        # Initialize topology and default options
        Topo.__init__(self, **opts)
        # adding a P4Switch
        
        router1 = self.addSwitch('r1',
                        cls = P4RuntimeSwitch,
                        sw_path = sw_path,
                        #json_path = json_path,
                        thrift_port = thrift_port,
                        grpc_port = grpc_port,
                        device_id = 1,
                        cpu_port = 510)
        router2 = self.addSwitch('r2',
                        cls = P4RuntimeSwitch,
                        sw_path = sw_path,
                        #json_path = json_path,
                        thrift_port = thrift_port+1,
                        grpc_port = grpc_port+1,
                        device_id = 2,
                        cpu_port = 510)
        router3 = self.addSwitch('r3',
                        cls = P4RuntimeSwitch,
                        sw_path = sw_path,
                        #json_path = json_path,
                        thrift_port = thrift_port+2,
                        grpc_port = grpc_port+2,
                        device_id = 3,
                        cpu_port = 510)


         # switchs
        switch1 = self.addSwitch('s1', cls = OVSKernelSwitch)
        switch2 = self.addSwitch('s2', cls = OVSKernelSwitch)
        switch3 = self.addSwitch('s3', cls = OVSKernelSwitch)

        host11 = self.addHost('h11', ip = "10.0.1.100/24", mac="00:04:00:00:00:01")
        self.addLink(host11, switch1, addr2="00:aa:00:00:00:11")
        server11 = self.addHost('server11', ip = "10.0.1.10/24", mac="00:04:00:00:00:20")
        self.addLink(server11, switch1, addr2="00:aa:00:00:00:12")
        server12 = self.addHost('server12', ip = "10.0.1.20/24", mac="00:04:00:00:00:30")
        self.addLink(server12, switch1, addr2="00:aa:00:00:00:13")


        host21 = self.addHost('h21', ip = "10.0.2.100/24", mac="00:04:00:00:00:03")
        self.addLink(host21, switch2, addr2="00:aa:00:00:00:21")
        server21 = self.addHost('server21', ip = "10.0.2.10/24", mac="00:04:00:00:00:40")
        self.addLink(server21, switch2, addr2="00:aa:00:00:00:22")
        server22 = self.addHost('server22', ip = "10.0.2.20/24", mac="00:04:00:00:00:50")
        self.addLink(server22, switch2, addr2="00:aa:00:00:00:23")

        host31 = self.addHost('h31', ip = "10.0.3.100/24", mac="00:04:00:00:00:02")
        self.addLink(host31, switch3, addr2="00:aa:00:00:00:31")
        server31 = self.addHost('server31', ip = "10.0.3.10/24", mac="00:04:00:00:00:60")
        self.addLink(server31, switch3, addr2="00:aa:00:00:00:32")
        server32 = self.addHost('server32', ip = "10.0.3.20/24", mac="00:04:00:00:00:70")
        self.addLink(server32, switch3, addr2="00:aa:00:00:00:33")


        # Ligacoes entre routers

        self.addLink(router1, router2, port1=1, port2=1, addr1="00:aa:bb:00:00:03", addr2="00:aa:dd:00:00:01")
        self.addLink(router1, router3, port1=2, port2=1, addr1="00:aa:bb:00:00:02", addr2="00:aa:cc:00:00:02")
        self.addLink(router2, router3, port1=2, port2=2, addr1="00:aa:dd:00:00:03", addr2="00:aa:cc:00:00:03")

        # Ligacoes entre switches e routers

        self.addLink(router1, switch1, addr1="00:aa:bb:00:00:01", addr2="00:aa:00:00:00:10")
        self.addLink(router2, switch2, addr1="00:aa:dd:00:00:02", addr2="00:aa:00:00:00:20")
        self.addLink(router3, switch3, addr1="00:aa:cc:00:00:01", addr2="00:aa:00:00:00:30")

        # self.addLink(s1, r1, port2=1, addr2="00:bb:bb:00:01:01")

        # self.addLink(s2, r2, port2=1, addr2="00:bb:bb:00:02:01")

        # self.addLink(r1, r2, port1=2, port2=2, addr1="00:bb:bb:00:01:02", addr2="00:bb:bb:00:02:02")

def main():
    parser = argparse.ArgumentParser(description='Mininet demo')
    parser.add_argument('--behavioral-exe', help='Path to behavioral executable',
                        type=str, action="store", default='simple_switch_grpc')
    parser.add_argument('--thrift-port', help='Thrift server port for table updates',
                        type=int, action="store", default=9091)
    parser.add_argument('--grpc-port', help='gRPC server port for controller comm',
                        type=int, action="store", default=50051)
    #parser.add_argument('--json', help='Path to JSON config file',
    #                    type=str, action="store", required=True)

    args = parser.parse_args()



    topo = SimpleRouter(args.behavioral_exe,
                        args.thrift_port,
                        args.grpc_port)
                        #args.json)

    # the host class is the P4Host
    # the switch class is the P4Switch
    net = Mininet(topo = topo,
                  host = P4Host,
                  #switch = P4Switch,
                  controller = None)

    # Here, the mininet will use the constructor (__init__()) of the P4Switch class, 
    # with the arguments passed to the SingleSwitchTopo class in order to create 
    # our software switch.
    net.start()

    commands = [
        'sudo ovs-ofctl add-flow s1 in_port=1,actions=normal',
        'sudo ovs-ofctl add-flow s1 in_port=2,actions=normal',
        'sudo ovs-ofctl add-flow s1 in_port=3,actions=normal',
        'sudo ovs-ofctl add-flow s1 in_port=4,actions=normal',
        'sudo ovs-ofctl add-flow s2 in_port=1,actions=normal',
        'sudo ovs-ofctl add-flow s2 in_port=2,actions=normal',
        'sudo ovs-ofctl add-flow s2 in_port=3,actions=normal',
        'sudo ovs-ofctl add-flow s2 in_port=4,actions=normal',
        'sudo ovs-ofctl add-flow s3 in_port=1,actions=normal',
        'sudo ovs-ofctl add-flow s3 in_port=2,actions=normal',
        'sudo ovs-ofctl add-flow s3 in_port=3,actions=normal',
        'sudo ovs-ofctl add-flow s3 in_port=4,actions=normal'
    ]

    # Execute each command in the list
    for cmd in commands:
        print('Running ...')
        subprocess.call(cmd, shell=True)


    gateway_mac_r1 = "00:aa:bb:00:00:01"
    gateway_ip_r1  = "10.0.1.254"
    gateway_mac_r2 = "00:aa:dd:00:00:02"
    gateway_ip_r2  = "10.0.2.250"
    gateway_mac_r3 = "00:aa:cc:00:00:01"
    gateway_ip_r3  = "10.0.3.253"

    
    h11 = net.get('h11')
    h11.setARP(gateway_ip_r1,gateway_mac_r1)
    h11.setDefaultRoute("dev eth0 via %s" % gateway_ip_r1)

    srv11 = net.get('server11')
    srv11.setARP(gateway_ip_r1,gateway_mac_r1)
    srv11.setDefaultRoute("dev eth0 via %s" % gateway_ip_r1)
    
    srv12 = net.get('server12')
    srv12.setARP(gateway_ip_r1,gateway_mac_r1)
    srv12.setDefaultRoute("dev eth0 via %s" % gateway_ip_r1)


    h21 = net.get('h21')
    h21.setARP(gateway_ip_r2,gateway_mac_r2)
    h21.setDefaultRoute("dev eth0 via %s" % gateway_ip_r2)

    srv21 = net.get('server21')
    srv21.setARP(gateway_ip_r2,gateway_mac_r2)
    srv21.setDefaultRoute("dev eth0 via %s" % gateway_ip_r2)

    srv22 = net.get('server22')
    srv22.setARP(gateway_ip_r2,gateway_mac_r2)
    srv22.setDefaultRoute("dev eth0 via %s" % gateway_ip_r2)

    
    h31 = net.get('h31')
    h31.setARP(gateway_ip_r3,gateway_mac_r3)
    h31.setDefaultRoute("dev eth0 via %s" % gateway_ip_r3)

    srv31 = net.get('server31')
    srv31.setARP(gateway_ip_r3,gateway_mac_r3)
    srv31.setDefaultRoute("dev eth0 via %s" % gateway_ip_r3)

    srv32 = net.get('server32')
    srv32.setARP(gateway_ip_r3,gateway_mac_r3)
    srv32.setDefaultRoute("dev eth0 via %s" % gateway_ip_r3)


    sleep(1)  # time for the host and switch confs to take effect
    

    print("Ready !")

    CLI( net )
    net.stop()

if __name__ == '__main__':
    setLogLevel( 'info' )
    main()
