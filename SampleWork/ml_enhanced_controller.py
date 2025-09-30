# ml_enhanced_controller.py
"""
ML-Enhanced SDN Controller using trained XGBoost model
Real-time traffic classification for QoS management
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp, icmp
from ryu.lib.packet import ether_types
import time
import pickle
import numpy as np
from collections import defaultdict
import os

class MLEnhancedController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(MLEnhancedController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.flow_stats = defaultdict(dict)
        self.flow_features = defaultdict(list)
        
        # ML Model components
        self.model_loaded = False
        self.ml_model = None
        self.scaler = None
        self.label_encoder = None
        self.feature_selector = None
        self.selected_features = None
        self.class_names = None
        
        # Performance tracking
        self.classification_count = 0
        self.classification_successes = 0
        self.ml_processing_times = []
        
        # Load trained ML model
        self.load_ml_model()
        
    def load_ml_model(self):
        """Load the trained XGBoost model and preprocessing components"""
        model_path = 'optimized_xgboost_traffic_classifier.pkl'
        
        try:
            if os.path.exists(model_path):
                with open(model_path, 'rb') as f:
                    model_artifacts = pickle.load(f)
                
                self.ml_model = model_artifacts['model']
                self.scaler = model_artifacts['scaler']
                self.label_encoder = model_artifacts['label_encoder']
                self.feature_selector = model_artifacts['feature_selector']
                self.selected_features = model_artifacts['selected_features']
                self.class_names = model_artifacts['class_names']
                
                self.model_loaded = True
                self.logger.info(f"✓ ML model loaded successfully from {model_path}")
                self.logger.info(f"Model can classify {len(self.class_names)} traffic types")
                self.logger.info(f"Using {len(self.selected_features)} features")
                
            else:
                self.logger.warning(f"ML model file not found: {model_path}")
                self.logger.warning("Falling back to basic classification")
                
        except Exception as e:
            self.logger.error(f"Failed to load ML model: {e}")
            self.model_loaded = False
    
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

    def extract_flow_features(self, pkt, in_port, eth_src, eth_dst):
        """Extract flow-level features for ML classification"""
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
            features['ip_flags'] = ipv4_pkt.flags
            
            # TCP features
            tcp_pkt = pkt.get_protocol(tcp.tcp)
            if tcp_pkt:
                features['src_port'] = tcp_pkt.src_port
                features['dst_port'] = tcp_pkt.dst_port
                features['tcp_window'] = tcp_pkt.window_size
                features['tcp_flags'] = tcp_pkt.bits
                
                # TCP flag analysis
                features['tcp_fin'] = 1 if tcp_pkt.bits & 0x01 else 0
                features['tcp_syn'] = 1 if tcp_pkt.bits & 0x02 else 0
                features['tcp_rst'] = 1 if tcp_pkt.bits & 0x04 else 0
                features['tcp_psh'] = 1 if tcp_pkt.bits & 0x08 else 0
                features['tcp_ack'] = 1 if tcp_pkt.bits & 0x10 else 0
                features['tcp_urg'] = 1 if tcp_pkt.bits & 0x20 else 0
            
            # UDP features
            udp_pkt = pkt.get_protocol(udp.udp)
            if udp_pkt:
                features['src_port'] = udp_pkt.src_port
                features['dst_port'] = udp_pkt.dst_port
                features['udp_len'] = udp_pkt.total_length
        
        # Flow-based features (maintain flow state)
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
        else:
            features['inter_arrival_time'] = 0
        
        flow_stat['last_packet_time'] = current_time
        flow_stat['packet_sizes'].append(len(pkt.data))
        
        # Flow statistical features
        features['flow_duration'] = current_time - flow_stat['start_time']
        features['flow_packet_count'] = flow_stat['packet_count']
        features['flow_byte_count'] = flow_stat['byte_count']
        
        if len(flow_stat['inter_arrival_times']) > 1:
            features['avg_inter_arrival'] = np.mean(flow_stat['inter_arrival_times'])
            features['std_inter_arrival'] = np.std(flow_stat['inter_arrival_times'])
        else:
            features['avg_inter_arrival'] = 0
            features['std_inter_arrival'] = 0
        
        if len(flow_stat['packet_sizes']) > 1:
            features['avg_packet_size'] = np.mean(flow_stat['packet_sizes'])
            features['std_packet_size'] = np.std(flow_stat['packet_sizes'])
        else:
            features['avg_packet_size'] = len(pkt.data)
            features['std_packet_size'] = 0
        
        # Packet rate features
        if features['flow_duration'] > 0:
            features['packet_rate'] = flow_stat['packet_count'] / features['flow_duration']
            features['byte_rate'] = flow_stat['byte_count'] / features['flow_duration']
        else:
            features['packet_rate'] = 0
            features['byte_rate'] = 0
        
        return features

    def prepare_features_for_model(self, raw_features):
        """Prepare features for ML model prediction"""
        if not self.model_loaded:
            return None
        
        try:
            # Create feature vector with all possible features (fill missing with 0)
            feature_dict = {}
            
            # Map raw features to expected model features
            # This should match the features your model was trained on
            expected_features = [
                'packet_length', 'ip_proto', 'ip_ttl', 'ip_len', 'src_port', 'dst_port',
                'tcp_window', 'tcp_flags', 'tcp_fin', 'tcp_syn', 'tcp_rst', 'tcp_psh', 
                'tcp_ack', 'tcp_urg', 'flow_duration', 'flow_packet_count', 'flow_byte_count',
                'avg_inter_arrival', 'std_inter_arrival', 'avg_packet_size', 'std_packet_size',
                'packet_rate', 'byte_rate'
            ]
            
            # Fill feature vector
            for feature in expected_features:
                feature_dict[feature] = raw_features.get(feature, 0)
            
            # Convert to array
            feature_array = np.array([list(feature_dict.values())]).reshape(1, -1)
            
            return feature_array
            
        except Exception as e:
            self.logger.error(f"Feature preparation error: {e}")
            return None

    def ml_classify_traffic(self, pkt, raw_features):
        """Use ML model to classify traffic"""
        self.classification_count += 1
        
        if not self.model_loaded:
            return 'unknown', 0.1, 'ML model not loaded'
        
        start_time = time.time()
        
        try:
            # Prepare features
            feature_array = self.prepare_features_for_model(raw_features)
            if feature_array is None:
                return 'unknown', 0.1, 'Feature preparation failed'
            
            # Scale features (if scaler available)
            if self.scaler:
                feature_array = self.scaler.transform(feature_array)
            
            # Predict with model
            prediction = self.ml_model.predict(feature_array)[0]
            prediction_proba = self.ml_model.predict_proba(feature_array)[0]
            
            # Get class name
            predicted_class = self.class_names[prediction]
            confidence = max(prediction_proba)
            
            # Track processing time
            processing_time = time.time() - start_time
            self.ml_processing_times.append(processing_time)
            
            self.classification_successes += 1
            
            return predicted_class, confidence, f'ML prediction (confidence: {confidence:.3f})'
            
        except Exception as e:
            self.logger.error(f"ML classification error: {e}")
            return 'unknown', 0.1, f'ML error: {str(e)}'

    def fallback_classify_traffic(self, pkt, raw_features):
        """Fallback classification when ML fails"""
        # Basic port-based classification as fallback
        src_port = raw_features.get('src_port', 0)
        dst_port = raw_features.get('dst_port', 0)
        
        # Web traffic
        if dst_port in [80, 443, 8080, 8443] or src_port in [80, 443, 8080, 8443]:
            return 'Browsing', 0.7, 'Port-based fallback'
        
        # DNS
        elif dst_port == 53 or src_port == 53:
            return 'DNS', 0.8, 'Port-based fallback'
        
        # SSH
        elif dst_port == 22 or src_port == 22:
            return 'SSH', 0.7, 'Port-based fallback'
        
        # Default
        return 'unknown', 0.3, 'Fallback classification'

    def get_priority_from_ml_classification(self, traffic_class, confidence):
        """Convert ML classification to OpenFlow priority"""
        
        # High priority traffic types
        high_priority_classes = [
            'DNS', 'VOIP', 'Video-Streaming', 'Audio-Streaming', 'Chat'
        ]
        
        # Medium priority traffic types  
        medium_priority_classes = [
            'Browsing', 'Email', 'SSH'
        ]
        
        # Low priority traffic types
        low_priority_classes = [
            'File-Transfer', 'P2P', 'Bulk'
        ]
        
        base_priority = 1000  # Default
        
        if traffic_class in high_priority_classes:
            base_priority = 3000
        elif traffic_class in medium_priority_classes:
            base_priority = 2000
        elif traffic_class in low_priority_classes:
            base_priority = 1000
        
        # Confidence boost (higher confidence gets priority boost)
        confidence_boost = int(confidence * 500)  # Max 500 boost
        
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

        # ML-based traffic classification
        if out_port != ofproto.OFPP_FLOOD:
            # Extract features
            raw_features = self.extract_flow_features(pkt, in_port, src, dst)
            
            # ML classification
            traffic_class, confidence, method = self.ml_classify_traffic(pkt, raw_features)
            
            # Fallback if ML classification has low confidence
            if confidence < 0.3:
                traffic_class, confidence, method = self.fallback_classify_traffic(pkt, raw_features)
                method = f"Fallback after ML: {method}"
            
            # Get priority based on ML classification
            priority = self.get_priority_from_ml_classification(traffic_class, confidence)
            
            # Log classification result
            if self.classification_count % 50 == 0:  # Log every 50th classification
                self.logger.info(f"ML Classification: {traffic_class} (conf: {confidence:.3f}, priority: {priority}) - {method}")
            
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
            success_rate = (self.classification_successes / self.classification_count) * 100
            avg_processing_time = np.mean(self.ml_processing_times) if self.ml_processing_times else 0
            
            self.logger.info(f"ML Performance: {success_rate:.1f}% success rate, {avg_processing_time*1000:.2f}ms avg processing time ({self.classification_count} total classifications)")