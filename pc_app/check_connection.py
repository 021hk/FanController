"""
check_connection.py - Diagnostic tool for ESP8266 connection.

This script checks:
1. Are there any COM ports available?
2. Which one is the ESP8266 (CH340)?
3. Can we connect to it?
4. Is WiFi hotspot reachable?

Run it to see what's wrong with the connection.
"""

import sys
import os
import time
import socket
import json

def print_header(title):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print()

def check_com_ports():
    """List all available COM ports."""
    print_header("STEP 1: Checking COM ports")
    try:
        from serial.tools import list_ports
        ports = list(list_ports.comports())
        if not ports:
            print("❌ No COM ports found!")
            print()
            print("Possible causes:")
            print("  - ESP8266 is not connected via USB")
            print("  - USB cable is power-only (not data)")
            print("  - CH340 driver is not installed")
            print()
            print("Solutions:")
            print("  1. Plug ESP8266 to a different USB port")
            print("  2. Try a different USB cable (data cable)")
            print("  3. Install CH340 driver from:")
            print("     https://sparks.gogo.co.nz/ch340.html")
            return None

        print(f"✓ Found {len(ports)} COM port(s):")
        print()
        esp_port = None
        for p in ports:
            print(f"  Port:     {p.device}")
            print(f"  Name:     {p.name}")
            print(f"  Desc:     {p.description}")
            print(f"  HWID:     {p.hwid}")
            print(f"  VID:PID:  {hex(p.vid) if p.vid else 'N/A'}:{hex(p.pid) if p.pid else 'N/A'}")
            # CH340 has VID 0x1A86, CP2102 has VID 0x10C4
            if p.vid in (0x1A86, 0x10C4, 0x1D50):
                esp_port = p.device
                print(f"  >>> This looks like an ESP8266/USB-to-Serial! <<<")
            print()
        return esp_port
    except ImportError:
        print("❌ pyserial not installed")
        return None

def test_wifi():
    """Test if ESP8266 hotspot is reachable."""
    print_header("STEP 2: Testing WiFi connection")
    print("Trying to reach ESP8266 at 192.168.4.1:80 ...")

    # First check if we're connected to FanController WiFi
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        my_ip = s.getsockname()[0]
        s.close()
        print(f"Your IP: {my_ip}")
        if my_ip.startswith("192.168.4."):
            print("✓ You are connected to FanController WiFi!")
        else:
            print(f"⚠️  You are NOT connected to FanController WiFi")
            print(f"   Your IP is {my_ip}, expected 192.168.4.x")
            print()
            print("Solutions:")
            print("  1. Click WiFi icon in taskbar")
            print("  2. Find 'FanController' network")
            print("  3. Connect with password: 12345678")
            print("  4. Click 'Connect anyway' on 'No Internet' warning")
            return False
    except Exception as e:
        print(f"Could not determine IP: {e}")

    # Try to ping ESP8266
    print()
    print("Trying HTTP request to 192.168.4.1 ...")
    try:
        import urllib.request
        req = urllib.request.urlopen("http://192.168.4.1/status", timeout=3)
        data = json.loads(req.read())
        print("✓ ESP8266 is reachable!")
        print(f"  Status: {data}")
        return True
    except Exception as e:
        print(f"❌ Cannot reach ESP8266: {e}")
        print()
        print("Possible causes:")
        print("  - ESP8266 is not powered on")
        print("  - ESP8266 hotspot didn't start")
        print("  - Firewall is blocking the connection")
        return False

def test_serial_port(port):
    """Try to open the COM port."""
    print_header(f"STEP 3: Testing serial port {port}")
    try:
        import serial
        print(f"Opening {port} at 115200 baud...")
        s = serial.Serial(port, 115200, timeout=2, exclusive=True)
        print(f"✓ Port opened successfully!")

        # Send a status request
        print("Sending status request...")
        s.write(b'{"cmd":"status"}\n')
        time.sleep(1)

        # Try to read response
        if s.in_waiting > 0:
            data = s.read(s.in_waiting).decode(errors='replace')
            print(f"✓ Got response: {data[:200]}")
        else:
            print("⚠️  No response (but port opened OK)")
            print("   ESP8266 firmware might not be running properly")

        s.close()
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        if "PermissionError" in str(e) or "Access is denied" in str(e):
            print()
            print(">>> PORT IS LOCKED <<<")
            print("Another application is using this port:")
            print("  - Close Arduino IDE and Serial Monitor")
            print("  - Close any other serial terminal")
            print("  - Wait a few seconds and try again")
        elif "cannot configure" in str(e).lower():
            print()
            print(">>> CANNOT CONFIGURE PORT <<<")
            print("Try:")
            print("  1. Unplug ESP8266")
            print("  2. Wait 5 seconds")
            print("  3. Plug it back in")
            print("  4. Run this script again")
        return False

def main():
    print("=" * 60)
    print("  ESP8266 Fan Controller - Connection Diagnostic")
    print("=" * 60)
    print()
    print("This tool will help you figure out why the PC app")
    print("cannot connect to your ESP8266.")
    print()

    # Step 1: Check COM ports
    esp_port = check_com_ports()

    # Step 2: Test WiFi
    wifi_ok = test_wifi()

    # Step 3: Test serial port if found
    if esp_port:
        test_serial_port(esp_port)

    # Summary
    print_header("SUMMARY")
    if wifi_ok:
        print("✓ WiFi connection is working")
        print("  Your FanController app should connect via WebSocket")
        print("  If it doesn't, check the app.log file")
    else:
        print("❌ WiFi is not working")
        print("  The app will try USB fallback")

    if esp_port:
        print(f"✓ ESP8266 detected on {esp_port}")
    else:
        print("❌ No ESP8266 detected on USB")
        print("  Make sure ESP8266 is plugged in and powered")

    print()
    print("=" * 60)
    print("  If you still have issues:")
    print("  1. Close Arduino IDE (it locks the COM port)")
    print("  2. Unplug ESP8266, wait 5s, plug back in")
    print("  3. Restart FanController app")
    print("=" * 60)

if __name__ == "__main__":
    main()
