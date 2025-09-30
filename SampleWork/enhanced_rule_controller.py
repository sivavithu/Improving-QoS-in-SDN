# enhanced_rule_controller.py
"""
Enhanced Rule-Based SDN Controller - Comparable to ML Version
Uses traditional classification methods (DPI, ports, statistics)
Same structure as ML controller for fair comparison
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp, icmp
from ryu.lib.packet import ether_types
import time
import numpy as np
from collections import defaultdict

class EnhancedRuleController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(EnhancedRuleController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.flow_stats = defaultdict(dict)
        
        # Performance tracking
        self.classification_count = 0
        self.dpi_attempts = 0
        self.dpi_successes = 0
        self.rule_classification_times = []
        
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
        
        self.logger.info("Rule-based controller initialized")

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                  priority=priority, match=match, instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                  match=match, instructions=inst)
        datapath.send_msg(mod)

    def extract_flow_features(self, pkt, in_port, eth_src, eth_dst):
        """Extract same flow-level features as ML controller"""
        features = {}
        current_time = time.time()
        
        # Basic packet features
        features['packet_length'] = len(pkt.data)
        features['in_port'] = in_port
        
        # Protocol analysis
        ipv4_pkt = pkt.get_protocol(ipv4.ipv4)
        if ipv4_pkt:
            features['ip_proto'] = ipv4_pkt.proto
            features['ip_ttl'] = ipv4_pkt.ttl
            features['ip_len'] = ipv4_pkt.total_length
            
            # TCP features
            tcp_pkt = pkt.get_protocol(tcp.tcp)
            if tcp_pkt:
                features['src_port'] = tcp_pkt.src_port
                features['dst_port'] = tcp_pkt.dst_port
                features['tcp_flags'] = tcp_pkt.bits
                features['protocol_type'] = 'TCP'
            
            # UDP features
            udp_pkt = pkt.get_protocol(udp.udp)
            if udp_pkt:
                features['src_port'] = udp_pkt.src_port
                features['dst_port'] = udp_pkt.dst_port
                features['protocol_type'] = 'UDP'
            
            # ICMP
            icmp_pkt = pkt.get_protocol(icmp.icmp)
            if icmp_pkt:
                features['protocol_type'] = 'ICMP'
        
        # Flow-based features (maintain flow state like ML controller)
        flow_key = f"{eth_src}-{eth_dst}"
        
        if flow_key not in self.flow_stats:
            self.flow_stats[flow_key] = {
                'packet_count': 0,
                'byte_count': 0,
                'start_time': current_time,
                'last_packet_time': current_time,
                'inter_arrival_times': [],
                'packet_sizes': []
            }
        
        flow_stat = self.flow_stats[flow_key]
        flow_stat['packet_count'] += 1
        flow_stat['byte_count'] += len(pkt.data)
        
        # Inter-arrival time
        if flow_stat['last_packet_time']:
            inter_arrival = current_time - flow_stat['last_packet_time']
            flow_stat['inter_arrival_times'].append(inter_arrival)
            features['inter_arrival_time'] = inter_arrival
        
        flow_stat['last_packet_time'] = current_time
        flow_stat['packet_sizes'].append(len(pkt.data))
        
        # Flow statistical features
        features['flow_duration'] = current_time - flow_stat['start_time']
        features['flow_packet_count'] = flow_stat['packet_count']
        features['flow_byte_count'] = flow_stat['byte_count']
        
        if len(flow_stat['inter_arrival_times']) > 1:
            features['avg_inter_arrival'] = np.mean(flow_stat['inter_arrival_times'])
        
        if len(flow_stat['packet_sizes']) > 1:
            features['avg_packet_size'] = np.mean(flow_stat['packet_sizes'])
        
        if features['flow_duration'] > 0:
            features['packet_rate'] = flow_stat['packet_count'] / features['flow_duration']
            features['byte_rate'] = flow_stat['byte_count'] / features['flow_duration']
        
        return features

    def attempt_dpi_classification(self, pkt_data):
        """Traditional DPI - fails on encrypted traffic"""
        self.dpi_attempts += 1
        
        try:
            # Look for HTTP patterns (only works on unencrypted)
            http_patterns = [b'GET ', b'POST ', b'HTTP/', b'Host:']
            
            for pattern in http_patterns:
                if pattern in pkt_data:
                    self.dpi_successes += 1
                    return 'Browsing', 0.9, 'DPI'
            
            # Look for other unencrypted protocols
            if b'SSH-' in pkt_data:
                self.dpi_successes += 1
                return 'SSH', 0.8, 'DPI'
            
            # DPI failed (likely encrypted)
            return None, 0.0, 'DPI_Failed'
            
        except:
            return None, 0.0, 'DPI_Error'

    def port_based_classification(self, features):
        """Traditional port-based classification"""
        src_port = features.get('src_port', 0)
        dst_port = features.get('dst_port', 0)
        
        # DNS (high priority)
        if dst_port == 53 or src_port == 53:
            return 'DNS', 0.9, 'Port-based'
        
        # Web traffic (medium-high priority)
        if dst_port in [80, 443, 8080, 8443] or src_port in [80, 443, 8080, 8443]:
            return 'Browsing', 0.8, 'Port-based'
        
        # SSH (medium priority)
        if dst_port == 22 or src_port == 22:
            return 'SSH', 0.7, 'Port-based'
        
        # Email (medium priority)
        if dst_port in [25, 587, 993, 995] or src_port in [25, 587, 993, 995]:
            return 'Email', 0.6, 'Port-based'
        
        # FTP (low priority)
        if dst_port in [20, 21] or src_port in [20, 21]:
            return 'File-Transfer', 0.6, 'Port-based'
        
        # VoIP ports (high priority)
        if 16384 <= dst_port <= 32768 or 16384 <= src_port <= 32768:
            return 'VOIP', 0.5, 'Port-based'
        
        return None, 0.0, 'Port-unknown'

    def statistical_classification(self, features):
        """Statistical analysis of flow characteristics"""
        pkt_len = features.get('packet_length', 0)
        avg_pkt_size = features.get('avg_packet_size', 0)
        byte_rate = features.get('byte_rate', 0)
        packet_rate = features.get('packet_rate', 0)
        
        # Video streaming: large packets, steady rate
        if avg_pkt_size > 1000 and byte_rate > 100000:
            return 'Video-Streaming', 0.6, 'Statistical'
        
        # Bulk transfer: very large packets, high throughput
        if avg_pkt_size > 1200 and byte_rate > 500000:
            return 'File-Transfer', 0.6, 'Statistical'
        
        # Small packet (likely control/interactive)
        if pkt_len <= 64:
            return 'Chat', 0.5, 'Statistical'
        
        # ICMP
        if features.get('protocol_type') == 'ICMP':
            return 'ICMP', 0.8, 'Statistical'
        
        return None, 0.0, 'Statistical-unknown'

    def rule_based_classify_traffic(self, pkt, raw_features):
        """Multi-stage rule-based classification - comparable to ML"""
        self.classification_count += 1
        start_time = time.time()
        
        # Stage 1: DPI Attempt (highest confidence when successful)
        dpi_class, dpi_conf, dpi_method = self.attempt_dpi_classification(pkt.data)
        if dpi_conf > 0.7:
            processing_time = time.time() - start_time
            self.rule_classification_times.append(processing_time)
            return dpi_class, dpi_conf, dpi_method
        
        # Stage 2: Port-based Classification
        port_class, port_conf, port_method = self.port_based_classification(raw_features)
        if port_conf > 0.5:
            processing_time = time.time() - start_time
            self.rule_classification_times.append(processing_time)
            return port_class, port_conf, port_method
        
        # Stage 3: Statistical Analysis
        stat_class, stat_conf, stat_method = self.statistical_classification(raw_features)
        if stat_conf > 0.4:
            processing_time = time.time() - start_time
            self.rule_classification_times.append(processing_time)
            return stat_class, stat_conf, stat_method
        
        # Stage 4: Protocol-based fallback
        protocol_type = raw_features.get('protocol_type', 'unknown')
        if protocol_type == 'TCP':
            processing_time = time.time() - start_time
            self.rule_classification_times.append(processing_time)
            return 'TCP-Generic', 0.3, 'Protocol-fallback'
        
        processing_time = time.time() - start_time
        self.rule_classification_times.append(processing_time)
        return 'unknown', 0.1, 'No-classification'

    def get_priority_from_rule_classification(self, traffic_class, confidence):
        """Convert rule classification to OpenFlow priority - same as ML"""
        
        # High priority traffic types
        high_priority_classes = [
            'DNS', 'VOIP', 'Video-Streaming', 'Audio-Streaming', 'Chat', 'ICMP'
        ]
        
        # Medium priority traffic types  
        medium_priority_classes = [
            'Browsing', 'Email', 'SSH'
        ]
        
        # Low priority traffic types
        low_priority_classes = [
            'File-Transfer', 'P2P', 'Bulk', 'TCP-Generic'
        ]
        
        base_priority = 1000  # Default
        
        if traffic_class in high_priority_classes:
            base_priority = 3000
        elif traffic_class in medium_priority_classes:
            base_priority = 2000
        elif traffic_class in low_priority_classes:
            base_priority = 1000
        
        # Confidence boost (same as ML approach)
        confidence_boost = int(confidence * 500)
        
        final_priority = min(base_priority + confidence_boost, 3500)
        
        return final_priority

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Rule-based traffic classification (comparable to ML approach)
        if out_port != ofproto.OFPP_FLOOD:
            # Extract features (same as ML)
            raw_features = self.extract_flow_features(pkt, in_port, src, dst)
            
            # Rule-based classification (instead of ML)
            traffic_class, confidence, method = self.rule_based_classify_traffic(pkt, raw_features)
            
            # Get priority based on classification (same logic as ML)
            priority = self.get_priority_from_rule_classification(traffic_class, confidence)
            
            # Log classification result
            if self.classification_count % 50 == 0:
                self.logger.info(f"Rule Classification: {traffic_class} (conf: {confidence:.3f}, priority: {priority}) - {method}")
            
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, priority, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, priority, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
        
        # Periodic performance reporting
        if self.classification_count > 0 and self.classification_count % 200 == 0:
            dpi_rate = (self.dpi_successes / self.dpi_attempts * 100) if self.dpi_attempts > 0 else 0
            avg_processing_time = np.mean(self.rule_classification_times) if self.rule_classification_times else 0
            
            self.logger.info(f"Rule-based Performance: DPI {dpi_rate:.1f}% success, {avg_processing_time*1000:.2f}ms avg processing ({self.classification_count} classifications)")

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp, icmp
from ryu.lib.packet import ether_types
import time
import re

class EnhancedRuleController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(EnhancedRuleController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.flow_stats = {}  # Track flow statistics
        self.dpi_attempts = 0
        self.dpi_successes = 0
        
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

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                  priority=priority, match=match, instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                  match=match, instructions=inst)
        datapath.send_msg(mod)

    def attempt_dpi_classification(self, pkt_data):
        """Traditional DPI attempt - will fail on encrypted traffic"""
        self.dpi_attempts += 1
        
        try:
            # Convert packet data to string for pattern matching
            data_str = str(pkt_data)
            
            # Look for HTTP patterns (only works on unencrypted)
            http_patterns = [
                b'GET ', b'POST ', b'HTTP/', b'Host:', 
                b'User-Agent:', b'Content-Type:'
            ]
            
            for pattern in http_patterns:
                if pattern in pkt_data:
                    self.dpi_successes += 1
                    return 'web_traffic', 0.9  # High confidence
            
            # Look for other unencrypted protocols
            if b'SSH-' in pkt_data:
                self.dpi_successes += 1
                return 'ssh_traffic', 0.8
            
            if b'SMTP' in pkt_data or b'MAIL' in pkt_data:
                self.dpi_successes += 1
                return 'email_traffic', 0.7
            
            # DPI failed (likely encrypted)
            return 'unknown', 0.0
            
        except:
            return 'unknown', 0.0

    def port_based_classification(self, tcp_pkt, udp_pkt):
        """Traditional port-based classification"""
        if tcp_pkt:
            src_port = tcp_pkt.src_port
            dst_port = tcp_pkt.dst_port
            
            # Web traffic (high priority)
            if dst_port in [80, 443, 8080, 8443] or src_port in [80, 443, 8080, 8443]:
                return 'web_traffic', 0.8
            
            # SSH (high priority)
            elif dst_port == 22 or src_port == 22:
                return 'ssh_traffic', 0.7
            
            # Email (medium priority)
            elif dst_port in [25, 587, 993, 995] or src_port in [25, 587, 993, 995]:
                return 'email_traffic', 0.6
            
            # FTP (low priority)
            elif dst_port in [20, 21] or src_port in [20, 21]:
                return 'ftp_traffic', 0.5
            
            # Gaming ports (high priority for interactive)
            elif dst_port in range(27015, 27030) or src_port in range(27015, 27030):
                return 'gaming_traffic', 0.8
        
        elif udp_pkt:
            dst_port = udp_pkt.dst_port
            src_port = udp_pkt.src_port
            
            # DNS (high priority)
            if dst_port == 53 or src_port == 53:
                return 'dns_traffic', 0.9
            
            # VoIP (high priority)
            elif dst_port in range(16384, 32768) or src_port in range(16384, 32768):
                return 'voip_traffic', 0.7
        
        return 'unknown', 0.0

    def statistical_flow_analysis(self, pkt, tcp_pkt, udp_pkt):
        """Basic statistical analysis of flow characteristics"""
        pkt_len = len(pkt.data)
        current_time = time.time()
        
        # Small packet analysis (likely control traffic)
        if pkt_len <= 64:
            return 'control_traffic', 0.6
        
        # Large packet analysis (likely bulk transfer)
        elif pkt_len >= 1400:
            return 'bulk_traffic', 0.4
        
        # TCP-specific analysis
        if tcp_pkt:
            # SYN packets (connection establishment)
            if tcp_pkt.bits & 0x02:  # SYN flag
                return 'connection_setup', 0.7
            
            # ACK-only packets (likely interactive)
            elif tcp_pkt.bits == 0x10:  # ACK only
                return 'interactive_traffic', 0.6
        
        # UDP analysis (likely real-time)
        elif udp_pkt:
            return 'realtime_traffic', 0.5
        
        return 'unknown', 0.0

    def protocol_based_classification(self, pkt):
        """Basic protocol-level classification"""
        ipv4_pkt = pkt.get_protocol(ipv4.ipv4)
        if not ipv4_pkt:
            return 'non_ip', 0.1
        
        # TCP traffic (reliable, likely interactive)
        if ipv4_pkt.proto == 6:  # TCP
            return 'tcp_traffic', 0.5
        
        # UDP traffic (unreliable, likely real-time)
        elif ipv4_pkt.proto == 17:  # UDP
            return 'udp_traffic', 0.4
        
        # ICMP traffic (control)
        elif ipv4_pkt.proto == 1:  # ICMP
            return 'icmp_traffic', 0.8
        
        return 'other_protocol', 0.2

    def classify_traffic(self, pkt, pkt_data):
        """Multi-stage classification with confidence scoring"""
        tcp_pkt = pkt.get_protocol(tcp.tcp)
        udp_pkt = pkt.get_protocol(udp.udp)
        
        classifications = []
        
        # Stage 1: DPI Attempt (highest confidence when successful)
        dpi_result, dpi_conf = self.attempt_dpi_classification(pkt_data)
        if dpi_conf > 0.0:
            classifications.append((dpi_result, dpi_conf, 'DPI'))
        
        # Stage 2: Port-based Classification
        port_result, port_conf = self.port_based_classification(tcp_pkt, udp_pkt)
        if port_conf > 0.0:
            classifications.append((port_result, port_conf, 'Port'))
        
        # Stage 3: Statistical Analysis
        stat_result, stat_conf = self.statistical_flow_analysis(pkt, tcp_pkt, udp_pkt)
        if stat_conf > 0.0:
            classifications.append((stat_result, stat_conf, 'Statistical'))
        
        # Stage 4: Protocol-based Fallback
        proto_result, proto_conf = self.protocol_based_classification(pkt)
        classifications.append((proto_result, proto_conf, 'Protocol'))
        
        # Choose best classification
        if classifications:
            best = max(classifications, key=lambda x: x[1])
            print(f"Classification: {best[0]} (confidence: {best[1]:.2f}, method: {best[2]})")
            return best[0], best[1]
        
        return 'unknown', 0.0

    def get_priority_from_classification(self, traffic_type, confidence):
        """Convert traffic classification to OpenFlow priority"""
        base_priorities = {
            'dns_traffic': 3000,
            'icmp_traffic': 2800,
            'web_traffic': 2500,
            'ssh_traffic': 2400,
            'gaming_traffic': 2300,
            'voip_traffic': 2200,
            'interactive_traffic': 2000,
            'connection_setup': 1800,
            'control_traffic': 1600,
            'email_traffic': 1400,
            'realtime_traffic': 1200,
            'tcp_traffic': 1000,
            'udp_traffic': 900,
            'bulk_traffic': 800,
            'ftp_traffic': 700,
            'other_protocol': 500,
            'non_ip': 300,
            'unknown': 100
        }
        
        base_priority = base_priorities.get(traffic_type, 100)
        
        # Adjust priority based on confidence
        # Higher confidence gets priority boost
        confidence_boost = int(confidence * 200)
        
        return min(base_priority + confidence_boost, 3200)  # Cap at 3200

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Enhanced classification
        if out_port != ofproto.OFPP_FLOOD:
            traffic_type, confidence = self.classify_traffic(pkt, msg.data)
            priority = self.get_priority_from_classification(traffic_type, confidence)
            
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            
            # Add flow with calculated priority
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, priority, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, priority, match, actions)
        
        # Send packet out
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
        
        # Print DPI success rate periodically
        if self.dpi_attempts > 0 and self.dpi_attempts % 100 == 0:
            success_rate = (self.dpi_successes / self.dpi_attempts) * 100
            print(f"DPI Success Rate: {success_rate:.1f}% ({self.dpi_successes}/{self.dpi_attempts})")