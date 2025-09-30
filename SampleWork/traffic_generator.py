#!/usr/bin/env python3
# traffic_generator.py
"""
Simple traffic generator to test rule-based classification
Generates both encrypted and unencrypted traffic to show DPI limitations
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.topo import Topo
from mininet.log import setLogLevel, info
import time
import threading

class TestTopo(Topo):
    def __init__(self):
        Topo.__init__(self)
        switch = self.addSwitch('s1', protocols='OpenFlow13')
        for i in range(1, 5):
            host = self.addHost(f'h{i}', ip=f'10.0.0.{i}/24')
            self.addLink(host, switch, bw=100)

def generate_unencrypted_traffic(net):
    """Generate unencrypted HTTP traffic (DPI should work)"""
    info("=== Testing Unencrypted Traffic (DPI should succeed) ===\n")
    
    h1 = net.get('h1')
    h2 = net.get('h2')
    
    # Start simple HTTP server
    h2.cmd('python3 -m http.server 8080 &')
    time.sleep(2)
    
    # Generate HTTP requests (unencrypted)
    info("Generating unencrypted HTTP traffic...\n")
    for i in range(5):
        result = h1.cmd('curl -s http://10.0.0.2:8080/ > /dev/null')
        time.sleep(1)
    
    # Stop server
    h2.cmd('pkill -f "python3 -m http.server"')
    info("Unencrypted traffic test completed\n")

def generate_encrypted_traffic(net):
    """Generate encrypted HTTPS traffic (DPI should fail)"""
    info("=== Testing Encrypted Traffic (DPI should fail) ===\n")
    
    h1 = net.get('h1')
    h3 = net.get('h3')
    
    # Generate HTTPS requests (encrypted - DPI will fail)
    info("Generating encrypted HTTPS traffic...\n")
    for i in range(5):
        # Try to connect to external HTTPS (will fail but generate encrypted patterns)
        h1.cmd('timeout 2 curl -k https://10.0.0.3:443/ > /dev/null 2>&1 || true')
        time.sleep(1)
    
    info("Encrypted traffic test completed\n")

def generate_various_protocols(net):
    """Generate different protocol types for classification testing"""
    info("=== Testing Various Protocol Classifications ===\n")
    
    h1 = net.get('h1')
    h2 = net.get('h2')
    h3 = net.get('h3')
    h4 = net.get('h4')
    
    # DNS traffic (UDP port 53)
    info("Testing DNS traffic (UDP)...\n")
    h1.cmd('nslookup google.com 8.8.8.8 > /dev/null 2>&1 &')
    time.sleep(1)
    
    # SSH traffic (TCP port 22)
    info("Testing SSH traffic...\n")
    h2.cmd('nc -l 22 > /dev/null &')
    h1.cmd('timeout 2 nc 10.0.0.2 22 < /dev/null > /dev/null 2>&1 &')
    time.sleep(2)
    
    # Large file transfer (bulk traffic)
    info("Testing bulk transfer...\n")
    h3.cmd('nc -l 12345 > /dev/null &')
    h1.cmd('timeout 3 dd if=/dev/zero bs=1024 count=1000 | nc 10.0.0.3 12345 &')
    time.sleep(3)
    
    # Small packet traffic (control)
    info("Testing small packet traffic...\n")
    for i in range(10):
        h1.cmd('ping -c 1 -s 32 10.0.0.4 > /dev/null 2>&1 &')
        time.sleep(0.5)
    
    # Cleanup
    for host in [h1, h2, h3, h4]:
        host.cmd('pkill -f nc || true')
    
    info("Protocol classification tests completed\n")

def generate_mixed_traffic(net):
    """Generate mixed traffic patterns sequentially (avoid threading issues)"""
    info("=== Testing Mixed Traffic Patterns ===\n")
    
    h1, h2, h3, h4 = net.get('h1', 'h2', 'h3', 'h4')
    
    # Web traffic
    info("Starting web traffic...\n")
    h2.cmd('python3 -m http.server 8080 &')
    time.sleep(1)
    for i in range(5):
        h1.cmd('curl -s http://10.0.0.2:8080/ > /dev/null')
        time.sleep(0.5)
    h2.cmd('pkill -f "python3 -m http.server" || true')
    
    # Bulk transfer  
    info("Starting bulk transfer...\n")
    h4.cmd('nc -l 9999 > /dev/null &')
    time.sleep(1)
    h3.cmd('timeout 3 dd if=/dev/zero bs=1024 count=500 | nc 10.0.0.4 9999')
    h4.cmd('pkill -f nc || true')
    
    # Ping traffic
    info("Starting ping traffic...\n")
    for i in range(10):
        h1.cmd('ping -c 1 10.0.0.3 > /dev/null 2>&1')
        time.sleep(0.2)
    
    info("Mixed traffic test completed\n")

def run_classification_tests():
    """Run comprehensive classification tests"""
    info("*** Starting Rule-Based Classification Tests ***\n")
    
    topo = TestTopo()
    net = Mininet(
        topo=topo,
        controller=lambda name: RemoteController(name, ip='127.0.0.1', port=6633),
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=True
    )
    
    net.start()
    
    # Wait for network to stabilize
    info("Waiting for network to stabilize...\n")
    time.sleep(3)
    
    # Test connectivity
    info("Testing basic connectivity...\n")
    h1, h2 = net.get('h1', 'h2')
    result = h1.cmd('ping -c 2 10.0.0.2')
    if '2 packets transmitted, 2 received' in result:
        info("✓ Basic connectivity working\n")
    else:
        info("✗ Connectivity issue\n")
    
    try:
        # Run different traffic tests
        generate_unencrypted_traffic(net)
        time.sleep(2)
        
        generate_encrypted_traffic(net)
        time.sleep(2)
        
        generate_various_protocols(net)
        time.sleep(2)
        
        generate_mixed_traffic(net)
        time.sleep(2)
        
        info("*** All classification tests completed ***\n")
        info("Check controller logs to see classification results\n")
        info("DPI should succeed on unencrypted traffic, fail on encrypted\n")
        
    except KeyboardInterrupt:
        info("Tests interrupted by user\n")
    finally:
        # Cleanup
        for host in net.hosts:
            host.cmd('pkill -f python3 || true')
            host.cmd('pkill -f nc || true')
            host.cmd('pkill -f curl || true')
        
        net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    print("=== Rule-Based Traffic Classification Test ===")
    print("1. Start the enhanced controller first:")
    print("   ryu-manager enhanced_rule_controller.py --verbose")
    print("2. Then run this script")
    print("3. Watch controller logs for classification results")
    print()
    input("Press Enter when controller is ready...")
    
    run_classification_tests()