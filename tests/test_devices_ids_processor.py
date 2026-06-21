from services.devices_ids_processor import process_devices_ids


def test_process_devices_ids_compacts_renile_response() -> None:
    devices_response = [
        {
            "name": "Greenhouse Climate Control",
            "id": "device-1",
            "_project": {"type": "Paradise Farms"},
        },
        {
            "name": "Incomplete Device",
        },
        {
            "name": "Local Climate monitoring system",
            "_id": "device-2",
        },
    ]

    devices_ids = process_devices_ids(devices_response)

    assert devices_ids == {
        "project_name": "Paradise Farms",
        "devices": [
            {"device_name": "Greenhouse Climate Control", "device_id": "device-1"},
            {"device_name": "Local Climate monitoring system", "device_id": "device-2"},
        ],
    }


def test_process_devices_ids_handles_empty_response() -> None:
    devices_ids = process_devices_ids([])

    assert devices_ids == {"project_name": None, "devices": []}
