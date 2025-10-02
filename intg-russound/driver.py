{
  "driver_id": "russound_rio",
  "version": "1.0.0",
  "min_core_api": "1.0.0",
  "name": {
    "en": "Russound RIO"
  },
  "description": {
    "en": "Integration for Russound MCA-88 and other RIO-compatible multi-zone audio controllers"
  },
  "port": 9095,
  "developer": {
    "name": "Russound Integration",
    "url": "https://github.com/ferdaze/uc-intg-russound"
  },
  "home_page": "https://github.com/ferdaze/uc-intg-russound",
  "setup_data_schema": {
    "title": {
      "en": "Russound RIO Setup"
    },
    "settings": [
      {
        "id": "host",
        "label": {
          "en": "IP Address"
        },
        "field": {
          "text": {
            "default": ""
          }
        }
      },
      {
        "id": "port",
        "label": {
          "en": "Port"
        },
        "field": {
          "number": {
            "default": 9621,
            "min": 1,
            "max": 65535
          }
        }
      },
      {
        "id": "name",
        "label": {
          "en": "Controller Name"
        },
        "field": {
          "text": {
            "default": "Russound"
          }
        }
      }
    ]
  },
  "release_date": "2025-09-30"
}
