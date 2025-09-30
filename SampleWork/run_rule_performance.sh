#!/bin/bash
# run_rule_performance.sh
# Comprehensive performance testing for rule-based SDN controller

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Rule-Based SDN Controller Performance Testing ===${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (for Mininet)${NC}"
   echo "Please run: sudo ./run_rule_performance.sh"
   exit 1
fi

# Check dependencies
echo -e "${BLUE}Checking dependencies...${NC}"

if ! command -v ryu-manager &> /dev/null; then
    echo -e "${RED}Ryu controller not found!${NC}"
    echo "Install with: pip install ryu"
    exit 1
fi

if ! command -v mn &> /dev/null; then
    echo -e "${RED}Mininet not found!${NC}"
    echo "Install with: sudo apt install mininet"
    exit 1
fi

if [ ! -f "enhanced_rule_controller.py" ]; then
    echo -e "${RED}enhanced_rule_controller.py not found!${NC}"
    echo "Please ensure the enhanced controller file is in the current directory"
    exit 1
fi

if [ ! -f "rule_based_performance_tester.py" ]; then
    echo -e "${RED}rule_based_performance_tester.py not found!${NC}"
    echo "Please ensure the performance tester is in the current directory"
    exit 1
fi

echo -e "${GREEN}✓ All dependencies found${NC}"

# Clean up any existing processes
echo -e "${BLUE}Cleaning up existing processes...${NC}"
killall ryu-manager 2>/dev/null || true
mn -c 2>/dev/null || true
killall python3 2>/dev/null || true
killall iperf 2>/dev/null || true
killall nc 2>/dev/null || true

# Make scripts executable
chmod +x rule_based_performance_tester.py

# Run the performance tests
echo -e "${GREEN}Starting comprehensive rule-based performance tests...${NC}"
echo -e "${YELLOW}This will take approximately 5-8 minutes to complete${NC}"
echo -e "${YELLOW}Tests include: Latency, Throughput, QoS, Flow Table Efficiency${NC}"
echo ""

python3 rule_based_performance_tester.py

echo -e "${GREEN}Rule-based performance testing completed!${NC}"

# Show results
if [ -d "rule_based_results" ]; then
    echo -e "${BLUE}Generated performance reports:${NC}"
    ls -la rule_based_results/ | grep -E "\.(json|csv|txt)$"
    echo ""
    
    # Show summary if available
    SUMMARY_FILE=$(ls rule_based_results/rule_based_performance_summary_*.txt 2>/dev/null | head -1)
    if [ -f "$SUMMARY_FILE" ]; then
        echo -e "${BLUE}=== PERFORMANCE SUMMARY PREVIEW ===${NC}"
        head -30 "$SUMMARY_FILE"
        echo ""
        echo -e "${GREEN}Full summary available in: $SUMMARY_FILE${NC}"
    fi
    
    echo -e "${YELLOW}=== NEXT STEPS FOR RESEARCH ===${NC}"
    echo "1. Compare these rule-based metrics with your ML approach results"
    echo "2. Analyze CSV files for detailed performance data"
    echo "3. Use JSON files for programmatic analysis"
    echo "4. Key comparison points:"
    echo "   • Latency: Rule-based vs ML classification speed"
    echo "   • Throughput: Efficiency differences"
    echo "   • QoS: Priority assignment accuracy"
    echo "   • Scalability: Flow processing rates"
fi