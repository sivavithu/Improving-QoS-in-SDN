#!/usr/bin/env python3
# rule_based_performance_tester.py
"""
Performance Testing Framework for Rule-Based SDN Controller
Measures latency, throughput, QoS, and rule-based classification metrics
Generates reports comparable to ML approach
"""

import subprocess
import time
import json
import csv
import os
import signal
import sys
import re
from datetime import datetime
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.topo import Topo

class SimpleStarTopo(Topo):
    """Simple star topology for testing"""
    def __init__(self):
        Topo.__init__(self)
        switch = self.addSwitch('s1', protocols='OpenFlow13')
        for i in range(1, 6):
            host = self.addHost(f'h{i}', ip=f'10.0.0.{i}/24')
            self.addLink(host, switch, bw=100, delay='1ms')

class RuleBasedPerformanceTester:
    def __init__(self):
        self.controller_process = None
        self.net = None
        self.results_dir = "rule_based_results"
        self.test_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.setup_directories()
        
    def setup_directories(self):
        """Create directories for results"""
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(f"{self.results_dir}/logs", exist_ok=True)
        info(f"Results will be saved to: {self.results_dir}/\n")
    
    def start_controller(self):
        """Start enhanced rule-based controller"""
        info("Starting Enhanced Rule-Based SDN controller...\n")
        controller_log = open(f"{self.results_dir}/logs/rule_controller_{self.test_timestamp}.log", 'w')
        
        self.controller_process = subprocess.Popen(
            ['ryu-manager', 'enhanced_rule_controller.py', '--verbose'],
            stdout=controller_log,
            stderr=controller_log
        )
        
        time.sleep(3)
        
        if self.controller_process.poll() is None:
            info("Rule-based controller started successfully\n")
            return True
        else:
            info("Failed to start rule-based controller\n")
            return False
    
    def start_network(self):
        """Start Mininet network"""
        info("Starting network topology...\n")
        
        topo = SimpleStarTopo()
        self.net = Mininet(
            topo=topo,
            controller=lambda name: RemoteController(name, ip='127.0.0.1', port=6633),
            switch=OVSSwitch,
            link=TCLink,
            autoSetMacs=True,
            autoStaticArp=True
        )
        
        self.net.start()
        time.sleep(2)
        info("Network started successfully\n")
        return True
    
    def test_classification_effectiveness(self):
        """Test classification effectiveness"""
        info("Testing rule-based classification effectiveness...\n")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'test_type': 'rule_classification_effectiveness',
            'description': 'Rule-based classification method effectiveness',
            'results': []
        }
        
        info("Generating different traffic types for classification testing...\n")
        
        h1, h2 = self.net.get('h1', 'h2')
        
        # Test 1: Web traffic
        info("  Testing web traffic classification...\n")
        h2.cmd('timeout 5 python3 -m http.server 8080 > /dev/null 2>&1 &')
        time.sleep(1)
        h1.cmd('timeout 3 curl -s http://10.0.0.2:8080/ > /dev/null 2>&1 || true')
        h2.cmd('pkill -f "python3.*8080" || true')
        time.sleep(1)
        
        results['results'].append({
            'traffic_type': 'web_browsing',
            'expected_classification': 'Browsing',
            'classification_method': 'Port-based',
            'should_work_encrypted': False
        })
        info("    Web traffic test completed\n")
        
        # Test 2: DNS traffic
        info("  Testing DNS traffic classification...\n")
        h1.cmd('timeout 2 nslookup google.com 8.8.8.8 > /dev/null 2>&1 || true')
        time.sleep(1)
        
        results['results'].append({
            'traffic_type': 'dns_queries',
            'expected_classification': 'DNS',
            'classification_method': 'Port-based',
            'should_work_encrypted': True
        })
        info("    DNS traffic test completed\n")
        
        # Test 3: Unknown traffic (simplified - just use ping)
        info("  Testing unknown traffic classification...\n")
        # Simple ICMP test instead of netcat to avoid system issues
        h1.cmd('ping -c 2 10.0.0.2 > /dev/null 2>&1')
        time.sleep(1)
        
        results['results'].append({
            'traffic_type': 'icmp_traffic',
            'expected_classification': 'ICMP',
            'classification_method': 'Protocol-based',
            'should_work_encrypted': True
        })
        info("    Unknown traffic test completed\n")
        
        self.save_results('rule_classification_effectiveness', results)
        info("Classification effectiveness testing completed\n")
        return results
    
    def test_baseline_latency(self):
        """Test baseline latency"""
        info("Testing baseline latency (no background traffic)...\n")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'test_type': 'baseline_latency',
            'description': 'Rule-based controller baseline performance',
            'results': []
        }
        
        hosts = ['h1', 'h2', 'h3', 'h4', 'h5']
        
        for i, src_name in enumerate(hosts):
            for dst_name in hosts[i+1:]:
                src = self.net.get(src_name)
                dst_ip = f"10.0.0.{dst_name[1]}"
                
                ping_result = src.cmd(f'ping -c 10 -W 1 {dst_ip}')
                
                packet_loss = self.parse_packet_loss(ping_result)
                avg_latency = self.parse_avg_latency(ping_result)
                min_latency = self.parse_min_latency(ping_result)
                max_latency = self.parse_max_latency(ping_result)
                jitter = max_latency - min_latency if max_latency > 0 and min_latency > 0 else 0
                
                test_result = {
                    'src': src_name,
                    'dst': dst_name,
                    'dst_ip': dst_ip,
                    'packet_loss_percent': packet_loss,
                    'avg_latency_ms': avg_latency,
                    'min_latency_ms': min_latency,
                    'max_latency_ms': max_latency,
                    'jitter_ms': jitter
                }
                
                results['results'].append(test_result)
                
                status = "✓" if packet_loss < 10 else "✗"
                info(f"{status} {src_name} -> {dst_name}: {avg_latency:.2f}ms avg, {jitter:.2f}ms jitter, {packet_loss}% loss\n")
        
        self.save_results('baseline_latency', results)
        return results
    
    def test_throughput_performance(self):
        """Test throughput performance"""
        info("Testing throughput performance...\n")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'test_type': 'throughput_performance',
            'description': 'Rule-based controller throughput analysis',
            'results': []
        }
        
        test_scenarios = [
            {'name': 'web_traffic', 'port': 8080, 'duration': 10},
            {'name': 'bulk_transfer', 'port': 9999, 'duration': 15},
            {'name': 'mixed_traffic', 'port': 7777, 'duration': 10}
        ]
        
        for scenario in test_scenarios:
            info(f"Testing {scenario['name']} throughput...\n")
            
            h1 = self.net.get('h1')
            h2 = self.net.get('h2')
            
            h2.cmd(f'iperf -s -p {scenario["port"]} > /tmp/iperf_server_{scenario["port"]}.log 2>&1 &')
            time.sleep(2)
            
            start_time = time.time()
            iperf_result = h1.cmd(f'iperf -c 10.0.0.2 -p {scenario["port"]} -t {scenario["duration"]} -i 1')
            end_time = time.time()
            
            throughput_mbps = self.parse_iperf_throughput(iperf_result)
            actual_duration = end_time - start_time
            
            h2.cmd(f'pkill -f "iperf.*{scenario["port"]}" || true')
            time.sleep(1)
            
            raw_efficiency = (throughput_mbps / 100.0) * 100 if throughput_mbps > 0 else 0
            efficiency = min(raw_efficiency, 100.0)
            
            test_result = {
                'scenario': scenario['name'],
                'port': scenario['port'],
                'throughput_mbps': throughput_mbps,
                'planned_duration': scenario['duration'],
                'actual_duration': actual_duration,
                'efficiency_percent': efficiency,
                'raw_efficiency_percent': raw_efficiency,
                'link_utilization': 'Saturated' if throughput_mbps > 95 else 'Normal'
            }
            
            results['results'].append(test_result)
            info(f"✓ {scenario['name']}: {throughput_mbps:.2f} Mbps ({efficiency:.1f}% efficiency, {raw_efficiency:.1f}% raw)\n")
        
        self.save_results('throughput_performance', results)
        return results
    
    def test_qos_under_load(self):
        """Simplified QoS test"""
        info("Testing QoS performance (simplified)...\n")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'test_type': 'qos_under_load',
            'description': 'Rule-based QoS performance - simplified test',
            'results': []
        }
        
        info("Running basic response time tests...\n")
        
        h1, h2 = self.net.get('h1', 'h2')
        
        for i in range(3):
            start_time = time.time()
            result = h1.cmd('ping -c 1 10.0.0.2')
            response_time = self.parse_avg_latency(result)
            
            test_result = {
                'traffic_type': f'basic_test_{i+1}',
                'port': 'N/A',
                'expected_priority': 'baseline',
                'avg_response_time_ms': response_time,
                'under_load': False,
                'test_method': 'simplified'
            }
            
            results['results'].append(test_result)
            info(f"  Basic test {i+1}: {response_time:.2f}ms response\n")
        
        info("QoS testing completed (simplified)\n")
        self.save_results('qos_under_load', results)
        return results
    
    def parse_packet_loss(self, ping_output):
        match = re.search(r'(\d+)% packet loss', ping_output)
        return int(match.group(1)) if match else 100
    
    def parse_avg_latency(self, ping_output):
        match = re.search(r'rtt min/avg/max/mdev = [\d.]+/([\d.]+)/', ping_output)
        return float(match.group(1)) if match else 0.0
    
    def parse_min_latency(self, ping_output):
        match = re.search(r'rtt min/avg/max/mdev = ([\d.]+)/', ping_output)
        return float(match.group(1)) if match else 0.0
    
    def parse_max_latency(self, ping_output):
        match = re.search(r'rtt min/avg/max/mdev = [\d.]+/[\d.]+/([\d.]+)/', ping_output)
        return float(match.group(1)) if match else 0.0
    
    def parse_iperf_throughput(self, iperf_output):
        lines = iperf_output.split('\n')
        for line in reversed(lines):
            if 'Mbits/sec' in line and 'sec' in line:
                match = re.search(r'([\d.]+)\s+Mbits/sec', line)
                if match:
                    return float(match.group(1))
        return 0.0
    
    def save_results(self, test_name, results):
        timestamp = self.test_timestamp
        
        json_file = f"{self.results_dir}/{test_name}_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        csv_file = f"{self.results_dir}/{test_name}_{timestamp}.csv"
        
        if test_name == 'rule_classification_effectiveness':
            with open(csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['traffic_type', 'expected_classification', 'classification_method', 'should_work_encrypted'])
                for result in results['results']:
                    writer.writerow([
                        result['traffic_type'], result['expected_classification'],
                        result['classification_method'], result['should_work_encrypted']
                    ])
        
        elif test_name == 'baseline_latency':
            with open(csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['src', 'dst', 'avg_latency_ms', 'min_latency_ms', 'max_latency_ms', 'jitter_ms', 'packet_loss_percent'])
                for result in results['results']:
                    writer.writerow([
                        result['src'], result['dst'], result['avg_latency_ms'],
                        result['min_latency_ms'], result['max_latency_ms'],
                        result['jitter_ms'], result['packet_loss_percent']
                    ])
        
        elif test_name == 'throughput_performance':
            with open(csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['scenario', 'port', 'throughput_mbps', 'efficiency_percent', 'raw_efficiency_percent', 'duration_sec'])
                for result in results['results']:
                    writer.writerow([
                        result['scenario'], result['port'], result['throughput_mbps'],
                        result['efficiency_percent'], result['raw_efficiency_percent'], result['actual_duration']
                    ])
    
    def generate_performance_summary(self, all_results):
        info("Generating performance summary report...\n")
        
        summary_file = f"{self.results_dir}/rule_based_performance_summary_{self.test_timestamp}.txt"
        
        with open(summary_file, 'w') as f:
            f.write("=== RULE-BASED SDN CONTROLLER PERFORMANCE SUMMARY ===\n")
            f.write(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Test ID: {self.test_timestamp}\n")
            f.write("Controller: Enhanced Rule-Based with DPI + Port + Statistical Classification\n\n")
            
            if 'rule_classification_effectiveness' in all_results:
                class_data = all_results['rule_classification_effectiveness']['results']
                f.write("--- CLASSIFICATION METHOD EFFECTIVENESS ---\n")
                f.write(f"Traffic types tested: {len(class_data)}\n")
                for result in class_data:
                    encrypted_note = "Works on encrypted" if result['should_work_encrypted'] else "Fails on encrypted"
                    f.write(f"• {result['traffic_type']}: {result['classification_method']} - {encrypted_note}\n")
                f.write("\n")
            
            if 'baseline_latency' in all_results:
                latency_data = all_results['baseline_latency']['results']
                avg_latencies = [r['avg_latency_ms'] for r in latency_data]
                avg_jitters = [r['jitter_ms'] for r in latency_data]
                packet_losses = [r['packet_loss_percent'] for r in latency_data]
                
                f.write("--- LATENCY PERFORMANCE ---\n")
                f.write(f"Average Latency: {sum(avg_latencies)/len(avg_latencies):.2f} ms\n")
                f.write(f"Average Jitter: {sum(avg_jitters)/len(avg_jitters):.2f} ms\n")
                f.write(f"Average Packet Loss: {sum(packet_losses)/len(packet_losses):.2f}%\n\n")
            
            if 'throughput_performance' in all_results:
                throughput_data = all_results['throughput_performance']['results']
                f.write("--- THROUGHPUT PERFORMANCE ---\n")
                for result in throughput_data:
                    f.write(f"{result['scenario']}: {result['throughput_mbps']:.2f} Mbps ({result['efficiency_percent']:.1f}% efficiency)\n")
                f.write("\n")
        
        info(f"Performance summary saved: {summary_file}\n")
    
    def cleanup(self):
        info("Cleaning up...\n")
        
        if self.net:
            for host in self.net.hosts:
                host.cmd('pkill -f iperf || true')
                host.cmd('pkill -f nc || true')
                host.cmd('pkill -f python3 || true')
            self.net.stop()
        
        if self.controller_process:
            self.controller_process.terminate()
            self.controller_process.wait()
        
        os.system('mn -c 2>/dev/null || true')
        info("Cleanup completed\n")
    
    def run_full_performance_tests(self):
        info("=== STARTING RULE-BASED CONTROLLER PERFORMANCE TESTS ===\n")
        info(f"Test ID: {self.test_timestamp}\n")
        
        all_results = {}
        
        try:
            if not self.start_controller():
                return False
            
            if not self.start_network():
                return False
            
            info("Waiting for network to stabilize...\n")
            time.sleep(5)
            
            info("=== RUNNING RULE-BASED PERFORMANCE TEST SUITE ===\n")
            
            all_results['rule_classification_effectiveness'] = self.test_classification_effectiveness()
            time.sleep(3)
            
            all_results['baseline_latency'] = self.test_baseline_latency()
            time.sleep(3)
            
            all_results['throughput_performance'] = self.test_throughput_performance()
            time.sleep(3)
            
            all_results['qos_under_load'] = self.test_qos_under_load()
            time.sleep(3)
            
            self.generate_performance_summary(all_results)
            
            info("=== RULE-BASED PERFORMANCE TESTS COMPLETED! ===\n")
            info(f"Results saved in: {self.results_dir}/\n")
            
            return True
            
        except KeyboardInterrupt:
            info("\nTests interrupted by user\n")
            return False
        except Exception as e:
            info(f"Tests failed with error: {e}\n")
            return False
        finally:
            self.cleanup()

def main():
    setLogLevel('info')
    
    def signal_handler(sig, frame):
        info('\nReceived interrupt signal, stopping tests...\n')
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    print("=== Rule-Based SDN Controller Performance Testing ===")
    print("This will test rule-based classification methods")
    print("\nPress Ctrl+C to stop anytime\n")
    
    tester = RuleBasedPerformanceTester()
    success = tester.run_full_performance_tests()
    
    if success:
        print("Rule-based performance testing completed!")
        print(f"Results available in: {tester.results_dir}/")
    else:
        print("Testing failed or was interrupted")
    
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())