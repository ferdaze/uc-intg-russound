# uc-intg-russound
Unfolded Circle Remote R2/R3 Russound RIO Integration

# Russound RIO Integration - Complete Setup Guide

This guide will walk you through setting up the Russound RIO integration for your Unfolded Circle Remote R3.

## Prerequisites

- Unfolded Circle Remote R3 (firmware 2.0.0 or higher)
- Russound MCA-88 or compatible device with RIO protocol support
- Both devices connected to the same network
- IP address of your Russound controller

## Step 1: Find Your Russound Controller's IP Address

### Option A: Using Your Router
1. Log into your router's admin interface
2. Look for "Connected Devices" or "DHCP Client List"
3. Find your Russound device (often listed as "MCA-88" or similar)
4. Note the IP address

### Option B: Using the Russound App
1. Open the Russound app on your phone/tablet
2. Go to Settings → System Information
3. The IP address should be displayed

### Option C: Set a Static IP (Recommended)
1. Access your Russound controller's web interface
2. Configure a static IP address to prevent it from changing
3. This ensures the integration remains connected

## Step 2: Download the Integration

### From GitHub Releases (Recommended)
1. Visit: https://github.com/ferdaze/uc-intg-russound/releases
2. Download the latest `uc-intg-russound-aarch64.tar.gz` file
3. Save it to your computer

### Build from Source (Advanced)
If you want to build from source, see the main README.md for instructions.

## Step 3: Upload to Your Remote R3

1. **Access Web Configurator**
   - Open a web browser
   - Navigate to your Remote R3's IP address
   - Log in with your PIN

2. **Navigate to Integrations**
   - Click on the "Integrations" tab at the top
   - You should see a list of installed integrations

3. **Install Custom Integration**
   - Click "+ Add Integration"
   - Select "Install Custom"
   - Click "Choose File" and select the downloaded `.tar.gz` file
   - Click "Upload"
   - Wait for the upload to complete (this may take 30-60 seconds)

4. **Verify Installation**
   - The "Russound RIO" integration should now appear in your integrations list
   - Status should show as "Installed"

## Step 4: Configure the Integration

1. **Start Setup**
   - Click on the "Russound RIO" integration
   - Click "Start Setup" or the setup icon

2. **Enter Connection Details**
   - **IP Address**: Enter your Russound controller's IP address (e.g., 192.168.1.100)
   - **Port**: Leave as default (9621) unless you've changed it
   - Click "Next" or "Submit"

3. **Wait for Discovery**
   - The integration will connect to your Russound controller
   - It will automatically discover all enabled zones and sources
   - This usually takes 5-10 seconds

4. **Setup Complete**
   - You should see a success message
   - The integration will show all discovered zones

## Step 5: Add Zones to Your Remote

1. **Go to Entities**
   - In the web configurator, go to "Entities"
   - You should see all your Russound zones listed as Media Player entities
   - Each zone will be named according to your Russound configuration

2. **Add to Activities**
   - Create or edit an Activity
   - Add one or more Russound zone entities
   - Configure button mappings as desired

3. **Configure UI**
   - Drag zone entities onto your UI pages
   - Use the media player widget for full control
   - Add quick access buttons for common functions

## Step 6: Test the Integration

1. **Test Power Control**
   - Try turning a zone on/off from the Remote R3
   - Verify the zone responds correctly

2. **Test Volume**
   - Adjust volume using the slider
   - Try volume up/down buttons
   - Verify volume changes on your Russound

3. **Test Source Selection**
   - Change sources using the source selector
   - Verify the correct source is selected

4. **Test Real-time Updates**
   - Change something on your Russound keypad or app
   - Verify the Remote R3 reflects the change within a few seconds

## Troubleshooting

### Integration Won't Connect

**Check Network Connectivity**
```bash
# From a computer on the same network:
