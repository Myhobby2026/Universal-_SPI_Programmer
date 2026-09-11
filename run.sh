#!/bin/bash
echo "Universal Programmer - Starting..."
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Python3 not found! Please install Python 3.8+"
    exit 1
fi

echo "Checking dependencies..."
pip3 install -r requirements.txt

echo "Starting GUI..."
python3 app.py
