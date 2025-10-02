# Unfolded Circle Remote R2/R3 Russound RIO Integration - Complete Setup Guide

## Table of Contents

1. [Introduction](#introduction)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Initial Setup](#initial-setup)
5. [Using the Integration](#using-the-integration)
6. [Advanced Features](#advanced-features)
7. [Troubleshooting](#troubleshooting)
8. [FAQs](#faqs)

---

## Introduction

This integration allows you to control your Russound MCA-88 (and other RIO-compatible) multi-zone audio systems directly from your Unfolded Circle Remote R3. The integration runs natively on the remote—no external servers or computers required.

### What You Can Control

- **All 8 Zones**: Power on/off each zone independently
- **Volume Control**: Adjust volume with precision (0-50 scale)
- **Source Selection**: Switch between all connected audio sources
- **Mute Function**: Instantly mute/unmute any zone
- **Tone Controls**: Adjust bass, treble, and balance per zone
- **Real-time Updates**: See changes instantly when controlled from other devices

---

## Prerequisites

### Hardware Requirements

1. **Russound Controller** (one of the following):
   - MCA-88, MCA-88X
   - MCA-66, MCA-C5, MCA-C3
   - MBX-PRE, MBX-AMP
   - Any Russound device with RIO protocol support

2. **Unfolded Circle Remote R3** with firmware 2.0.0 or later

3. **Network Setup**:
   - Russound controller connected to your network via Ethernet
   - Remote R3 connected to the same network (Wi-Fi or Ethernet)
   - Both devices must be able to communicate (same subnet recommended)

### Finding Your Russound IP Address

#### Method 1: Via Russound App
1. Open the Russound app on your phone/tablet
2. Go to Settings → System Information
3. Note the IP address

#### Method 2: Via Router
1. Log into your router's admin interface
2. Look for connected devices
3. Find "Russound" or check devices on port 9621

#### Method 3: Network Scanner
Use a network scanning app like Fing to find devices on port 9621

---

## Installation

### Step 1: Download the Integration

1. Go to [https://github.com/ferdaze/uc-intg-russound/releases](https://github.com/ferdaze/uc-intg-russound/releases)
2. Download the latest `uc-intg-russound.tar.gz` file
3. Save it to your computer

### Step 2: Access Remote Web Configurator

1. Find your Remote R3's IP address:
   - On the remote: Settings → Network → IP Address
   
2. Open a web browser on your computer

3. Navigate to: `http://[REMOTE-IP-ADDRESS]`
   - Example: `http://192.168.1.50`

4. Log in:
   - Username: `web-configurator`
   - Password: Your remote's PIN (found in Settings → Web Configurator)

### Step 3: Upload Integration

1. In the web configurator, click the **Integrations** tab

2. Click **Add Integration** (blue + button)

3. Select **Install Custom**

4. Click **Choose File** and select the downloaded `uc-intg-russound.tar.gz`

5. Click **Upload**

6. Wait for the upload to complete (usually 10-30 seconds)

7. You should see "Russound RIO" appear in your integrations list

---

## Initial Setup

### Step 1: Start Configuration

1. In the Integrations list, find **Russound RIO**

2. Click on it to open the integration card

3. Click **Start Setup**

### Step 2: Enter Connection Details

You'll see a setup form with three fields:

#### IP Address
- Enter your Russound controller's IP address
- Example: `192.168.1.100`
- Must be reachable from your Remote R3

#### Port
- Default: `9621`
- Only change if you've customized your Russound network settings
- Most users should leave this as 9621

#### Controller Name
- A friendly name for your system
- Examples: "Home Audio", "Theater System", "Whole House Audio"
- This helps identify your system if you have multiple integrations

### Step 3: Test Connection

1. Click **Next** after entering details

2. The integration will test the connection:
   - ✅ **Success**: You'll see "Connected successfully"
   - ❌ **Failed**: Check your IP address and network connectivity

3. If successful, the integration automatically discovers:
   - All active zones
   - All configured sources
   - Current states of all zones

### Step 4: Select Zones

1. You'll see a list of all discovered zones:
   ```
   ☐ Zone 1 - Living Room
   ☐ Zone 2 - Kitchen
   ☐ Zone 3 - Master Bedroom
   ☐ Zone 4 - Patio
   ...
   ```

2. Check the boxes for zones you want to control

3. **Tip**: You can add/remove zones later by reconfiguring

### Step 5: Complete Setup

1. Click **Finish**

2. The integration is now active!

3. Zones will appear in your **Entities** list

---

## Using the Integration

### Adding Zones to Activities

#### Create a New Activity

1. On your Remote R3, go to **Activities**

2. Tap **+** to create a new activity

3. Name it (e.g., "Listen to Music")

4. In the **Entities** section:
   - Tap **Add Entity**
   - Find your Russound zones under "Russound RIO"
   - Select the zone(s) you want

5. Configure buttons and commands

#### Add to Existing Activity

1. Open an existing activity

2. Tap **Edit**

3. Go to **Entities** → **Add Entity**

4. Select Russound zones

5. Save changes

### Zone Control Interface

Each zone provides these controls:

#### Power
- **On Button**: Powers on the zone
- **Off Button**: Powers off the zone  
- **Toggle**: Switches between on/off states

#### Volume
- **Volume Slider**: Drag to set exact volume (0-100%)
- **Volume Up**: Increases volume by 2 steps
- **Volume Down**: Decreases volume by 2 steps
- Volume is displayed as percentage (0-100%)
  - Note: Russound uses 0-50 scale internally

#### Mute
- **Mute Toggle**: Instantly mutes/unmutes the zone
- Mute state is displayed with an icon

#### Source Selection
- **Source Dropdown**: Lists all available sources
- Tap to switch to a different source
- Sources are named as configured in your Russound system

#### Media Information (when available)
If the current source provides metadata:
- Track Title
- Artist Name
- Album Name
- Album Artwork
- Playback Position

### Creating Macros

Combine multiple actions into one button:

#### Example: "Party Mode"
```
1. Zone 1 (Living Room) → Power On
2. Zone 2 (Kitchen) → Power On  
3. Zone 4 (Patio) → Power On
4. Zone 1 → Volume 60%
5. Zone 2 → Volume 60%
6. Zone 4 → Volume 60%
7. All Zones → Select Source "Spotify"
```

#### Example: "Goodnight"
```
1. Zone 3 (Master Bedroom) → Power On
2. Zone 3 → Volume 20%
3. Zone 3 → Select Source "White Noise"
4. Wait 30 seconds
5. All Other Zones → Power Off
```

### Using the Media Widget

1. Add a zone to your UI page

2. Tap on the zone card

3. The media widget shows:
   - Current source name
   - Play/pause (if supported)
   - Track information
   - Album artwork
   - Progress bar

4. Control directly from the widget

---

## Advanced Features

### Multiple Controller Support

If you have cascaded Russound controllers:

1. Connect to the **primary** controller's IP address
2. The integration automatically discovers all zones across all controllers
3. Zones are numbered sequentially (1-48 possible with 6 controllers)

**Example Setup:**
- Controller 1 (Primary): Zones 1-8
- Controller 2 (Linked): Zones 9-16
- Controller 3 (Linked): Zones 17-24

### Customizing Source Names

Source names come from your Russound configuration:

1. Use the Russound app or keypad
2. Rename sources as desired
3. Restart the integration in the web configurator
4. New names will appear automatically

### Tone Control (Advanced)

Access tone controls via the Remote R3 UI editor:

1. Edit your activity/page
2. Add custom buttons
3. Map to Russound entity attributes:
   - `bass` (-10 to +10)
   - `treble` (-10 to +10)
   - `balance` (-10 to +10, left to right)

### Scenes and Scheduling

Create automated scenes:

#### Morning Wake-Up
- Trigger: 7:00 AM (weekdays)
- Action: 
  - Kitchen zone on
  - Volume 30%
  - Source: News Radio

#### Evening Wind-Down
- Trigger: 9:00 PM
- Action:
  - Living room dimmed
  - Master bedroom on
  - Volume 25%
  - Source: Jazz playlist

---

## Troubleshooting

### Connection Issues

#### Problem: "Cannot connect to Russound"

**Solutions:**
1. Verify IP address is correct
2. Ping the Russound from another device
3. Check that port 9621 is not blocked by firewall
4. Ensure Russound is powered on
5. Try rebooting the Russound controller

#### Problem: "Connection lost" during use

**Solutions:**
1. Check network stability
2. Verify Russound hasn't changed IP (use DHCP reservation)
3. Check for network congestion
4. Restart the integration

### Zone Issues

#### Problem: Zone not discovered

**Solutions:**
1. Verify zone is enabled in Russound configuration
2. Check zone is not disabled at the controller
3. Run setup again to re-discover

#### Problem: Zone commands not working

**Solutions:**
1. Check zone is powered on
2. Verify speakers are connected
3. Try controlling from Russound app to confirm functionality
4. Restart integration

### Volume Issues

#### Problem: Volume changes not reflecting

**Solutions:**
1. Check if zone is muted
2. Verify max volume settings in Russound
3. Some zones may have volume limits

#### Problem: Volume too quiet or too loud

**Solutions:**
1. Adjust "Turn On Volume" in Russound settings
2. Check amplifier levels if using external amps
3. Verify speaker impedance settings

### Source Issues

#### Problem: Sources not appearing

**Solutions:**
1. Verify sources are enabled in Russound
2. Check source naming in Russound app
3. Re-run setup to discover sources

#### Problem: Metadata not showing

**Solutions:**
1. Verify source supports metadata (streaming sources typically do)
2. Some sources (like analog inputs) don't provide metadata
3. Check source is actively playing content

### Integration Issues

#### Problem: Integration won't start

**Solutions:**
1. Check Remote R3 firmware is up to date
2. Verify .tar.gz file wasn't corrupted
3. Try removing and re-uploading integration
4. Check web configurator logs

#### Problem: Integration crashes or restarts

**Solutions:**
1. Check for conflicting integrations
2. Verify network stability
3. Update to latest integration version
4. Report issue on GitHub with logs

---

## FAQs

### General Questions

**Q: Do I need to keep my computer running?**  
A: No! The integration runs entirely on your Remote R3.

**Q: Can I control multiple Russound systems?**  
A: Yes, install the integration multiple times with different IPs.

**Q: Does this work with other Unfolded Circle remotes?**  
A: Currently designed for Remote R3. Remote 2 compatibility depends on firmware.

**Q: Will this interfere with my Russound app?**  
A: No, multiple clients can connect simultaneously.

### Technical Questions

**Q: What network port does it use?**  
A: TCP port 9621 (standard RIO protocol port)

**Q: Does it support RS-232 connection?**  
A: No, only TCP/IP (Ethernet) connection is supported.

**Q: Can I use it with RNET protocol?**  
A: No, this integration requires RIO protocol. MCA-series use RIO.

**Q: What's the difference between RIO and RNET?**  
A: RIO is newer, supports TCP/IP, and provides more features. All MCA and MBX devices use RIO.

### Feature Questions

**Q: Can I adjust bass/treble from the remote?**  
A: Yes, though you need to create custom controls in the UI editor.

**Q: Does it support party mode?**  
A: Yes, create a macro that powers on and synchronizes multiple zones.

**Q: Can I see what's playing on each zone?**  
A: Yes, if the source provides metadata (streaming sources typically do).

**Q: Does it support presets?**  
A: Not in v1.0. Preset support may be added in future versions.

### Troubleshooting Questions

**Q: Why are zones numbered differently than my Russound app?**  
A: Zone numbers come from the controller configuration. Check Russound settings.

**Q: Can I rename zones?**  
A: Zone names come from Russound. Rename them in the Russound app, then restart the integration.

**Q: Volume scale is different - why?**  
A: Russound uses 0-50 internally. The integration converts to 0-100% for consistency.

**Q: Some sources don't work - why?**  
A: Ensure sources are properly configured and enabled in your Russound system.

---

## Getting Help

### Before Asking for Help

1. Check this user guide thoroughly
2. Review the troubleshooting section
3. Check GitHub Issues for similar problems
4. Verify your Russound firmware is current

### Where to Get Help

**GitHub Issues** (Bug Reports):  
[https://github.com/ferdaze/uc-intg-russound/issues](https://github.com/ferdaze/uc-intg-russound/issues)

**GitHub Discussions** (General Questions):  
[https://github.com/ferdaze/uc-intg-russound/discussions](https://github.com/ferdaze/uc-intg-russound/discussions)

**Unfolded Circle Discord**:  
[https://discord.gg/unfoldedcircle](https://discord.gg/unfoldedcircle)

### When Reporting Issues

Please include:
1. Integration version
2. Remote R3 firmware version
3. Russound model number
4. Error messages or logs
5. Steps to reproduce the problem
6. Network configuration (same subnet, router model, etc.)

---

## Tips & Best Practices

### Network Setup
- Use DHCP reservation for consistent Russound IP
- Keep Remote and Russound on same subnet
- Use wired connection for Russound if possible

### Organization
- Name zones clearly (room names work best)
- Group zones logically in activities
- Use macros for common multi-zone scenarios

### Performance
- Don't poll too frequently (integration handles updates)
- Keep firmware updated on both devices
- Monitor network quality for stability

### Maintenance
- Periodically check for integration updates
- Keep Russound firmware current
- Test after any network changes

---

## Appendix

### Russound Volume Scale Conversion

|
