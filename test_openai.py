#!/usr/bin/env python3
"""
Test script to debug OpenAI client initialization issues
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("Testing OpenAI client initialization...")
print(f"OpenAI API Key present: {'Yes' if os.getenv('OPENAI_API_KEY') else 'No'}")

# Check for proxy-related environment variables
proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
for var in proxy_vars:
    value = os.getenv(var)
    if value:
        print(f"Found proxy environment variable {var}: {value}")

try:
    from openai import OpenAI
    print("OpenAI import successful")
    
    # Test basic initialization
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    print("OpenAI client initialization successful")
    
except Exception as e:
    print(f"Error during OpenAI initialization: {e}")
    print(f"Error type: {type(e)}")
    
    # Try alternative initialization
    try:
        print("Trying alternative initialization...")
        client = OpenAI()  # Will use OPENAI_API_KEY env var
        print("Alternative initialization successful")
    except Exception as e2:
        print(f"Alternative initialization also failed: {e2}")