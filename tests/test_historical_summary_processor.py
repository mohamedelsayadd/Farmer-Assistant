from services.historical_summary_processor import parse_decimal_value, process_daily_sensor_response


def test_parse_decimal_value() -> None:
    assert parse_decimal_value({"$numberDecimal": "23.5"}) == 23.5
    assert parse_decimal_value(10) == 10
    assert parse_decimal_value(10.5) == 10.5
    assert parse_decimal_value(None) is None
    assert parse_decimal_value({"$numberDecimal": "bad"}) is None
    assert parse_decimal_value({"other": "23.5"}) is None


def test_process_daily_sensor_response_converts_sensor_payload_to_daily_rows() -> None:
    response = {
        "CO2": {
            "labels": ["2026-06-01T00:00:00.000Z", "2026-06-02T00:00:00.000Z"],
            "data": [{"$numberDecimal": "505.94"}, {"$numberDecimal": "499.17"}],
        },
        "ambient_temp": {
            "labels": ["2026-06-01T00:00:00.000Z", "2026-06-02T00:00:00.000Z"],
            "data": [{"$numberDecimal": "23.10"}, {"$numberDecimal": "24.48"}],
        },
    }

    daily_rows = process_daily_sensor_response(response)

    assert daily_rows == [
        {"date": "2026-06-01", "CO2": 505.94, "ambient_temp": 23.1},
        {"date": "2026-06-02", "CO2": 499.17, "ambient_temp": 24.48},
    ]
