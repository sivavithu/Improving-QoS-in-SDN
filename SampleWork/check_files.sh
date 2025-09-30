#!/bin/bash
# check_files.sh
# Verify you have all required files for SDN performance testing

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== SDN Performance Testing - File Checker ===${NC}"
echo

# Required files for complete testing
REQUIRED_FILES=(
    "enhanced_rule_controller.py"
    "ml_enhanced_controller.py" 
    "rule_based_performance_tester.py"
    "ml_based_performance_tester.py"
    "compare_results.py"
    "run_rule_performance.sh"
    "run_ml_performance.sh"
    "run_complete_comparison.sh"
    "optimized_xgboost_traffic_classifier.pkl"
)

# Optional files (helpful but not required)
OPTIONAL_FILES=(
    "triangle_controller.py"
    "triangle_topo.py"
    "traffic_generator.py"
    "run_rule_tests.sh"
)

echo -e "${BLUE}Checking required files...${NC}"
echo

MISSING_REQUIRED=0
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file ${RED}(MISSING - REQUIRED)${NC}"
        MISSING_REQUIRED=1
    fi
done

echo
echo -e "${BLUE}Checking optional files...${NC}"
echo

for file in "${OPTIONAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${YELLOW}○${NC} $file ${YELLOW}(missing - optional)${NC}"
    fi
done

echo
echo -e "${BLUE}=== SUMMARY ===${NC}"

if [ $MISSING_REQUIRED -eq 0 ]; then
    echo -e "${GREEN}🎉 All required files found!${NC}"
    echo -e "${GREEN}You can run the complete comparison:${NC}"
    echo "   chmod +x *.sh"
    echo "   sudo ./run_complete_comparison.sh"
else
    echo -e "${RED}❌ Missing required files!${NC}"
    echo -e "${YELLOW}Please make sure you have all the files listed above.${NC}"
fi

echo
echo -e "${BLUE}=== FILE DESCRIPTIONS ===${NC}"
echo "🎯 run_complete_comparison.sh    - Main script (runs everything)"
echo "🤖 enhanced_rule_controller.py   - Rule-based SDN controller"  
echo "🤖 ml_enhanced_controller.py     - ML-enhanced SDN controller"
echo "🧪 rule_based_performance_tester.py - Tests rule-based performance"
echo "🧪 ml_based_performance_tester.py   - Tests ML performance"
echo "📊 compare_results.py            - Creates comparison reports"
echo "📊 optimized_xgboost_traffic_classifier.pkl - Your trained ML model"