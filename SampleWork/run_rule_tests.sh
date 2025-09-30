#!/bin/bash
# run_rule_tests.sh
# Simple script to test rule-based classification

set -e

echo "=== Rule-Based Classification Testing ==="
echo

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (for Mininet)"
   echo "Please run: sudo ./run_rule_tests.sh"
   exit 1
fi

# Cleanup any existing processes
echo "Cleaning up existing processes..."
killall ryu-manager 2>/dev/null || true
mn -c 2>/dev/null || true

# Make scripts executable
chmod +x traffic_generator.py

# Start controller in background
echo "Starting enhanced rule controller..."
ryu-manager enhanced_rule_controller.py --verbose > controller_output.log 2>&1 &
CONTROLLER_PID=$!

# Wait for controller to start
echo "Waiting for controller to start..."
sleep 3

# Check if controller started successfully
if ps -p $CONTROLLER_PID > /dev/null; then
    echo "✓ Controller started successfully"
else
    echo "✗ Failed to start controller"
    cat controller_output.log
    exit 1
fi

echo
echo "Starting traffic classification tests..."
echo "This will test:"
echo "1. Unencrypted HTTP traffic (DPI should work)"
echo "2. Encrypted HTTPS traffic (DPI should fail)" 
echo "3. Various protocol classifications"
echo "4. Mixed traffic patterns"
echo

# Run traffic tests
python3 traffic_generator.py

echo
echo "=== Test Results ==="
echo "Check controller_output.log for detailed classification results"
echo

# Show DPI success rate from log
echo "DPI Success Rate Summary:"
grep -i "dpi success rate" controller_output.log | tail -5 || echo "No DPI stats found yet"

echo
echo "Sample Classifications:"
grep -i "classification:" controller_output.log | tail -10 || echo "No classification logs found"

# Show results before cleanup
echo
echo "=== RESULTS ANALYSIS ==="
echo

# Check if controller log exists
if [ -f "controller_output.log" ]; then
    echo "Controller log file found. Analyzing results..."
    echo
    
    # Count classifications
    echo "Classification Summary:"
    grep -i "classification:" controller_output.log | cut -d' ' -f2 | sort | uniq -c | sort -nr || echo "No classification logs found"
    echo
    
    # DPI success rate
    echo "DPI Performance:"
    grep -i "dpi success rate" controller_output.log | tail -1 || echo "No DPI stats found"
    echo
    
    # Show some example classifications
    echo "Sample Classifications (last 10):"
    grep -i "classification:" controller_output.log | tail -10 || echo "No classification logs found"
    echo
else
    echo "Controller log file not found!"
fi

# Cleanup
echo "Stopping controller..."
kill $CONTROLLER_PID 2>/dev/null || true
mn -c 2>/dev/null || true

echo "✓ Tests completed!"
echo "Full controller log saved in: controller_output.log"