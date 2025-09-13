# Ryu Controller + Mininet Setup Guide

## Prerequisites
- Ubuntu 20.04/22.04 (recommended)
- Python 3.8+
- Git
- sudo privileges

## Step 1: Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install essential packages
sudo apt install -y python3-pip python3-dev python3-setuptools
sudo apt install -y git build-essential
sudo apt install -y curl wget

# Install networking tools
sudo apt install -y net-tools bridge-utils
sudo apt install -y openvswitch-switch openvswitch-common
```

## Step 2: Install Mininet

```bash
# Option 1: Install from package (recommended for beginners)
sudo apt install -y mininet

# Option 2: Install from source (for latest version)
git clone https://github.com/mininet/mininet
cd mininet
sudo ./util/install.sh -nfv

# Verify Mininet installation
sudo mn --version
```

## Step 3: Install Ryu Controller

```bash
# Install Ryu using pip
sudo pip3 install ryu

# Verify Ryu installation
ryu-manager --version

# Clone Ryu source for examples and apps
git clone https://github.com/osrg/ryu.git
cd ryu
sudo python3 setup.py install
sudo pip install eventlet==0.30.2
```

## Step 4: Basic Ryu Controller Application

Create a simple L2 learning switch controller:

```python
# File: simple_switch.py
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types

class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        # Extract packet information
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            # Ignore LLDP packets
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        self.mac_to_port.setdefault(dpid, {})

        self.logger.info("packet in %s %s %s %s", dpid, src, dst, in_port)

        # Learn MAC address to avoid flooding next time
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            self.add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
```

## Step 5: Create Basic Network Topologies

### Single Switch Topology
```python
# File: single_switch_topo.py
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel

class SingleSwitchTopo(Topo):
    def build(self):
        # Add switch
        s1 = self.addSwitch('s1')
        
        # Add hosts
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')
        h4 = self.addHost('h4')
        
        # Add links
        self.addLink(h1, s1)
        self.addLink(h2, s1)
        self.addLink(h3, s1)
        self.addLink(h4, s1)

def run_topology():
    # Create topology
    topo = SingleSwitchTopo()
    
    # Create network with remote controller
    net = Mininet(topo=topo, 
                  controller=RemoteController('c0', ip='127.0.0.1', port=6653),
                  switch=OVSKernelSwitch)
    
    # Start network
    net.start()
    
    # Drop into CLI for testing
    CLI(net)
    
    # Clean up
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run_topology()
```

### Linear Topology (for traffic flow testing)
```python
# File: linear_topo.py
from mininet.topo import Topo

class LinearTopo(Topo):
    def build(self, n=3):
        # Add switches
        switches = []
        for i in range(n):
            switch = self.addSwitch(f's{i+1}')
            switches.append(switch)
        
        # Connect switches in a line
        for i in range(n-1):
            self.addLink(switches[i], switches[i+1])
        
        # Add hosts (2 per switch)
        for i in range(n):
            h1 = self.addHost(f'h{2*i+1}')
            h2 = self.addHost(f'h{2*i+2}')
            self.addLink(h1, switches[i])
            self.addLink(h2, switches[i])

# Usage: mn --custom linear_topo.py --topo linear,3 --controller remote
```

## Step 6: Verification Steps

### Terminal 1: Start Ryu Controller
```bash
# Navigate to your controller directory
cd /path/to/your/controller/files

# Start Ryu with your simple switch
ryu-manager simple_switch.py --verbose

# Expected output:
# loading app simple_switch.py
# instantiating app simple_switch.py of SimpleSwitch13
# BRICK SimpleSwitch13
```

### Terminal 2: Start Mininet with Remote Controller
```bash
# Simple test with built-in topology
sudo mn --controller remote --switch ovsk

# Or with custom topology
sudo python3 single_switch_topo.py

# Expected output:
# *** Creating network
# *** Adding controller
# *** Adding hosts and switches
# *** Adding links
# *** Configuring hosts
# *** Starting controller
# *** Starting switches
# *** Starting CLI:
```

### Terminal 3: Verify Connectivity
In Mininet CLI:
```bash
# Check if all nodes are connected
mininet> nodes

# Ping between hosts
mininet> h1 ping h2

# Check flow table
mininet> sh ovs-ofctl dump-flows s1

# Test connectivity matrix
mininet> pingall
```

## Step 7: Verify Controller-Switch Communication

### Check OpenFlow Connection
```bash
# In controller terminal, you should see:
# EVENT ofp_event.EventOFPSwitchFeatures
# switch features ev version=0x4,msg_type=0x6

# Check switch connection
sudo ovs-vsctl show

# Check OpenFlow version
sudo ovs-ofctl -O OpenFlow13 show s1
```

### Monitor Flow Installation
```bash
# Watch flows being installed
watch -n 1 'sudo ovs-ofctl -O OpenFlow13 dump-flows s1'

# Generate traffic and observe
# In Mininet: h1 ping h2
```

## Step 8: Basic Traffic Generation Test

```python
# File: test_traffic.py
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
import time

def test_basic_traffic():
    net = Mininet(controller=RemoteController('c0', ip='127.0.0.1', port=6653))
    
    # Add hosts and switch
    h1 = net.addHost('h1')
    h2 = net.addHost('h2')
    s1 = net.addSwitch('s1')
    
    # Add links
    net.addLink(h1, s1)
    net.addLink(h2, s1)
    
    net.start()
    
    # Test connectivity
    print("Testing connectivity...")
    result = net.ping([h1, h2])
    print(f"Ping result: {result}")
    
    # Generate some traffic
    print("Generating traffic...")
    h1.cmd('iperf -s &')
    time.sleep(1)
    h2.cmd('iperf -c', h1.IP(), '-t 10')
    
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    test_basic_traffic()
```

## Troubleshooting Common Issues

### 1. Controller Connection Issues
```bash
# Check if Ryu is listening
netstat -tlnp | grep 6653

# Check firewall
sudo ufw status
sudo ufw allow 6653

# Test controller connectivity
telnet 127.0.0.1 6653
```

### 2. OpenFlow Version Mismatch
```bash
# Force OpenFlow 1.3
sudo ovs-vsctl set bridge s1 protocols=OpenFlow13
```

### 3. Switch Not Connecting
```bash
# Check OVS status
sudo systemctl status openvswitch-switch

# Restart OVS if needed
sudo systemctl restart openvswitch-switch

# Clear old flows
sudo ovs-ofctl del-flows s1
```

## Next Steps

Once this basic setup is working:

1. **Monitor Flow Statistics**: Add flow monitoring to your Ryu app
2. **Implement QoS Rules**: Extend the controller for traffic prioritization
3. **Add Flow Classification Logic**: Integrate your ML model hooks
4. **Scale the Topology**: Test with larger, more complex topologies

Your environment should now be ready for the next phase: traffic generation and data collection!
