#!/usr/bin/env python3
import subprocess
import sys
import os

def install_requirements():
    print("Installing Pinterest Scraper requirements...")
    
    # Check if requirements.txt exists
    if not os.path.exists("requirements.txt"):
        print("Error: requirements.txt not found!")
        return False
    
    try:
        # Install requirements using pip
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("\nAll requirements installed successfully!")
        print("You can now run the scraper using: python run.py")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to install requirements: {str(e)}")
        return False

if __name__ == "__main__":
    install_requirements() 