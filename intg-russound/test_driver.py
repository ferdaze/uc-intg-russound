#!/usr/bin/env python3
"""Minimal test driver to verify it runs."""
import logging
import sys
import os

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)

_LOG = logging.getLogger(__name__)

_LOG.info("=" * 60)
_LOG.info("RUSSOUND TEST DRIVER STARTING")
_LOG.info("=" * 60)
_LOG.info("Python version: %s", sys.version)
_LOG.info("Executable: %s", sys.executable)
_LOG.info("Frozen: %s", getattr(sys, 'frozen', False))
_LOG.info("Working directory: %s", os.getcwd())
_LOG.info("=" * 60)

# Log environment
_LOG.info("Environment variables:")
for key, value in sorted(os.environ.items()):
    if key.startswith("UC_") or key in ["HOME", "USER", "PATH"]:
        _LOG.info("  %s=%s", key, value)

# Find driver.json
if getattr(sys, 'frozen', False):
    driver_path = os.path.dirname(sys.executable)
    driver_json = os.path.join(os.path.dirname(driver_path), "driver.json")
else:
    driver_path = os.path.dirname(os.path.abspath(__file__))
    driver_json = os.path.join(os.path.dirname(driver_path), "driver.json")

_LOG.info("=" * 60)
_LOG.info("Looking for driver.json at: %s", driver_json)
_LOG.info("Exists: %s", os.path.exists(driver_json))

if os.path.exists(driver_json):
    _LOG.info("driver.json contents:")
    with open(driver_json) as f:
        _LOG.info(f.read())
else:
    parent = os.path.dirname(driver_json)
    _LOG.error("driver.json NOT FOUND!")
    _LOG.error("Contents of %s:", parent)
    try:
        for item in os.listdir(parent):
            item_path = os.path.join(parent, item)
            _LOG.error("  - %s %s", item, "(dir)" if os.path.isdir(item_path) else "")
    except Exception as e:
        _LOG.error("Cannot list: %s", e)

_LOG.info("=" * 60)

# Try to import and initialize ucapi
try:
    import ucapi
    _LOG.info("ucapi imported successfully: %s", ucapi.__version__ if hasattr(ucapi, '__version__') else "unknown version")
    
    api = ucapi.IntegrationAPI("russound_rio")
    _LOG.info("IntegrationAPI created")
    
    if os.path.exists(driver_json):
        api.init(driver_json)
        _LOG.info("API initialized with driver.json")
        _LOG.info("Driver is now running and waiting for connections...")
        api.loop.run_forever()
    else:
        _LOG.error("Cannot initialize without driver.json")
        sys.exit(1)
        
except Exception as e:
    _LOG.error("ERROR: %s", e, exc_info=True)
    sys.exit(1)
