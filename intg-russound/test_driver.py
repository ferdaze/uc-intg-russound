#!/usr/bin/env python3
"""Test driver for Russound integration."""
import logging
import sys
import os
import asyncio

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.StreamHandler(sys.stderr)
    ]
)

_LOG = logging.getLogger(__name__)

def main():
    _LOG.info("=" * 60)
    _LOG.info("RUSSOUND INTEGRATION DRIVER STARTING")
    _LOG.info("=" * 60)
    _LOG.info("Python: %s", sys.version)
    _LOG.info("Executable: %s", sys.executable)
    _LOG.info("Frozen: %s", getattr(sys, 'frozen', False))
    _LOG.info("CWD: %s", os.getcwd())
    _LOG.info("=" * 60)

    # Log ALL environment variables
    _LOG.info("ALL Environment variables:")
    for key, value in sorted(os.environ.items()):
        _LOG.info("  %s=%s", key, value)
    _LOG.info("=" * 60)

    # Find driver.json
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle
        driver_path = os.path.dirname(sys.executable)
        driver_json = os.path.join(os.path.dirname(driver_path), "driver.json")
        _LOG.info("Running as PyInstaller bundle")
    else:
        # Python script
        driver_path = os.path.dirname(os.path.abspath(__file__))
        driver_json = os.path.join(os.path.dirname(driver_path), "driver.json")
        _LOG.info("Running as Python script")
    
    _LOG.info("Driver path: %s", driver_path)
    _LOG.info("Driver JSON path: %s", driver_json)
    _LOG.info("Driver JSON exists: %s", os.path.exists(driver_json))
    _LOG.info("=" * 60)

    # List parent directory
    parent = os.path.dirname(driver_json)
    _LOG.info("Contents of %s:", parent)
    try:
        for item in sorted(os.listdir(parent)):
            item_path = os.path.join(parent, item)
            if os.path.isdir(item_path):
                _LOG.info("  [DIR]  %s", item)
            else:
                size = os.path.getsize(item_path)
                _LOG.info("  [FILE] %s (%d bytes)", item, size)
    except Exception as e:
        _LOG.error("Cannot list directory: %s", e)
    _LOG.info("=" * 60)

    # Read driver.json if exists
    if os.path.exists(driver_json):
        try:
            with open(driver_json, 'r') as f:
                content = f.read()
            _LOG.info("driver.json content:")
            _LOG.info(content)
        except Exception as e:
            _LOG.error("Cannot read driver.json: %s", e)
    else:
        _LOG.error("driver.json NOT FOUND at %s", driver_json)
        _LOG.error("Cannot continue without driver.json")
        sys.exit(1)
    
    _LOG.info("=" * 60)

    # Try to import ucapi
    try:
        _LOG.info("Importing ucapi...")
        import ucapi
        _LOG.info("ucapi imported successfully")
        _LOG.info("ucapi location: %s", ucapi.__file__ if hasattr(ucapi, '__file__') else "unknown")
        
        _LOG.info("Creating IntegrationAPI...")
        api = ucapi.IntegrationAPI("russound_rio")
        _LOG.info("IntegrationAPI created")
        
        # Simple setup handler
        async def setup_handler(msg):
            _LOG.info("Setup called with: %s", msg.setup_data)
            return ucapi.SetupComplete()
        
        api.set_setup_handler(setup_handler)
        _LOG.info("Setup handler registered")
        
        _LOG.info("Initializing API with driver.json...")
        api.init(driver_json)
        _LOG.info("API initialized successfully!")
        _LOG.info("=" * 60)
        _LOG.info("Driver is now running and listening for connections")
        _LOG.info("=" * 60)
        
        # Run the event loop
        api.loop.run_forever()
        
    except ImportError as e:
        _LOG.error("Failed to import ucapi: %s", e)
        _LOG.error("ucapi must be installed")
        sys.exit(1)
    except Exception as e:
        _LOG.error("Fatal error: %s", e, exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
