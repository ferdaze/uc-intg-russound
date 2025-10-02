#!/usr/bin/env python3
"""
Simplified Russound RIO Integration Driver for Unfolded Circle Remote
This is a minimal working version for testing the build process
"""
import asyncio
import logging
import sys

# Test if ucapi can be imported
try:
    import ucapi
    from ucapi import IntegrationAPI, StatusCodes
except ImportError:
    print("ERROR: ucapi not found. Install with: pip install ucapi")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
_LOG = logging.getLogger(__name__)

# Driver configuration
DRIVER_ID = "russound_rio"
DRIVER_VERSION = "1.0.0"


def main():
    """Main entry point."""
    _LOG.info("Starting Russound Integration Driver v%s", DRIVER_VERSION)
    
    # Create API instance
    api = IntegrationAPI(DRIVER_ID)
    
    # Simple setup handler
    async def handle_setup(msg):
        _LOG.info("Setup called with: %s", msg.setup_data)
        return ucapi.SetupComplete()
    
    # Register setup handler
    api.set_setup_handler(handle_setup)
    
    try:
        # Initialize and run
        api.init("driver.json")
        _LOG.info("Driver initialized successfully")
        api.loop.run_forever()
    except KeyboardInterrupt:
        _LOG.info("Shutting down...")
    except Exception as e:
        _LOG.error("Fatal error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
