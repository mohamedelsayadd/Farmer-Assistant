from services.current_readings_processor import process_current_readings, reading_status


def test_reading_status() -> None:
    assert reading_status(None, 1, 3) == "unknown"
    assert reading_status(0, 1, 3) == "below_limit"
    assert reading_status(4, 1, 3) == "above_limit"
    assert reading_status(2, 1, 3) == "normal"
    assert reading_status(2, None, None) == "normal"


def test_process_current_readings_compacts_renile_response() -> None:
    raw_devices = [
        {
            "name": "Greenhouse Climate Control",
            "_project": {"type": "Paradise Farms"},
            "sensortypes": [
                {
                    "sensor_type": {
                        "type": "ambient_temp",
                        "measurement_unit": "°C",
                    },
                    "lower_limit": 11,
                    "upper_limit": 30,
                }
            ],
            "lastRead": [
                {
                    "name": "ambient_temp",
                    "reading": 22.75,
                    "createdAt": "2026-06-19T20:42:50.919Z",
                }
            ],
        }
    ]

    processed_readings = process_current_readings(raw_devices)

    assert processed_readings == {
        "project_name": "Paradise Farms",
        "devices": [
            {
                "device_name": "Greenhouse Climate Control",
                "readings": [
                    {
                        "sensor": "ambient_temp",
                        "value": 22.75,
                        "unit": "°C",
                        "lower_limit": 11,
                        "upper_limit": 30,
                        "status": "normal",
                        "timestamp": "2026-06-19T20:42:50.919Z",
                    }
                ],
            }
        ],
    }
