# Mock response of the ReNile device-status API, used until the real endpoint exists.
DEVICES_STATUS_RESPONSE = {
    "devices": [
        {
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "name": "Greenhouse Sensor 01",
            "connectivityType": "4G",
            "connectivityRenewType": "automatic",
            "expiration_date": None,
            "readings": {
                "temperature": {"value": 27.4, "unit": "°C", "last_read_at": "2026-10-01T12:45:00+03:00", "normal_range": {"min": 15, "max": 35}},
                "humidity": {"value": 68.2, "unit": "%", "last_read_at": "2026-10-01T12:44:00+03:00", "normal_range": {"min": 40, "max": 85}},
                "ph": {"value": 6.7, "unit": "pH", "last_read_at": "2026-10-01T12:40:00+03:00", "normal_range": {"min": 5.5, "max": 7.5}},
                "soil_moisture": {"value": 42.5, "unit": "%", "last_read_at": "2026-10-01T12:43:00+03:00", "normal_range": {"min": 30, "max": 70}},
                "light_intensity": {"value": 0, "unit": "lux", "last_read_at": "2026-10-01T12:45:00+03:00", "normal_range": {"min": 500, "max": 50000}},
            },
        },
        {
            "id": "550e8400-e29b-41d4-a716-446655440002",
            "name": "Farm Station 02",
            "connectivityType": "4G",
            "connectivityRenewType": "manual",
            "expiration_date": "2026-09-15",
            "readings": {
                "temperature": {"value": 31.8, "unit": "°C", "last_read_at": "2026-10-01T12:38:00+03:00", "normal_range": {"min": 15, "max": 40}},
                "humidity": {"value": 54.6, "unit": "%", "last_read_at": "2026-10-01T12:37:00+03:00", "normal_range": {"min": 35, "max": 85}},
                "ph": {"value": 7.1, "unit": "pH", "last_read_at": "2026-09-29T10:20:00+03:00", "normal_range": {"min": 5.5, "max": 7.5}},
                "soil_moisture": {"value": 36.8, "unit": "%", "last_read_at": "2026-10-01T12:35:00+03:00", "normal_range": {"min": 30, "max": 70}},
                "wind_speed": {"value": 12.4, "unit": "km/h", "last_read_at": "2026-10-01T12:39:00+03:00", "normal_range": {"min": 0, "max": 50}},
            },
        },
        {
            "id": "550e8400-e29b-41d4-a716-446655440003",
            "name": "Irrigation Controller 03",
            "connectivityType": "4G",
            "connectivityRenewType": "manual",
            "expiration_date": "2026-10-20",
            "readings": {
                "temperature": {"value": 26.9, "unit": "°C", "last_read_at": "2026-10-01T12:42:00+03:00", "normal_range": {"min": 15, "max": 35}},
                "humidity": {"value": 71.3, "unit": "%", "last_read_at": "2026-10-01T12:41:00+03:00", "normal_range": {"min": 40, "max": 85}},
                "soil_moisture": {"value": 58.7, "unit": "%", "last_read_at": "2026-09-28T09:15:00+03:00", "normal_range": {"min": 30, "max": 70}},
                "water_flow": {"value": 0, "unit": "L/min", "last_read_at": "2026-10-01T12:42:00+03:00", "normal_range": {"min": 5, "max": 30}},
                "water_pressure": {"value": 2.8, "unit": "bar", "last_read_at": "2026-10-01T12:42:00+03:00", "normal_range": {"min": 1.5, "max": 4}},
            },
        },
        {
            "id": "550e8400-e29b-41d4-a716-446655440004",
            "name": "Soil Monitor 04",
            "connectivityType": "WIFI",
            "connectivityRenewType": None,
            "expiration_date": None,
            "readings": {
                "temperature": {"value": 25.6, "unit": "°C", "last_read_at": "2026-10-01T12:30:00+03:00", "normal_range": {"min": 15, "max": 35}},
                "humidity": {"value": 73.8, "unit": "%", "last_read_at": "2026-10-01T12:31:00+03:00", "normal_range": {"min": 40, "max": 85}},
                "ph": {"value": 6.4, "unit": "pH", "last_read_at": "2026-09-30T08:20:00+03:00", "normal_range": {"min": 5.5, "max": 7.5}},
                "soil_moisture": {"value": 61.2, "unit": "%", "last_read_at": "2026-10-01T12:29:00+03:00", "normal_range": {"min": 30, "max": 70}},
                "soil_conductivity": {"value": 1.32, "unit": "mS/cm", "last_read_at": "2026-09-28T14:10:00+03:00", "normal_range": {"min": 0.5, "max": 2.5}},
            },
        },
        {
            "id": "550e8400-e29b-41d4-a716-446655440005",
            "name": "Weather Station 05",
            "connectivityType": "4G",
            "connectivityRenewType": "automatic",
            "expiration_date": None,
            "readings": {
                "temperature": {"value": 29.7, "unit": "°C", "last_read_at": "2026-10-01T12:46:00+03:00", "normal_range": {"min": 10, "max": 45}},
                "humidity": {"value": 59.4, "unit": "%", "last_read_at": "2026-10-01T12:46:00+03:00", "normal_range": {"min": 20, "max": 90}},
                "wind_speed": {"value": 8.7, "unit": "km/h", "last_read_at": "2026-10-01T12:45:00+03:00", "normal_range": {"min": 0, "max": 60}},
                "rainfall": {"value": 0, "unit": "mm", "last_read_at": "2026-10-01T12:46:00+03:00", "normal_range": {"min": 0, "max": 100}},
                "atmospheric_pressure": {"value": 1012.6, "unit": "hPa", "last_read_at": "2026-10-01T12:45:00+03:00", "normal_range": {"min": 980, "max": 1040}},
            },
        },
        {
            "id": "550e8400-e29b-41d4-a716-446655440006",
            "name": "Water Pump 06",
            "connectivityType": "WIFI",
            "connectivityRenewType": None,
            "expiration_date": None,
            "readings": {
                "water_flow": {"value": 18.6, "unit": "L/min", "last_read_at": "2026-10-01T12:40:00+03:00", "normal_range": {"min": 5, "max": 30}},
                "water_pressure": {"value": 3.2, "unit": "bar", "last_read_at": "2026-10-01T12:40:00+03:00", "normal_range": {"min": 1.5, "max": 4}},
                "pump_speed": {"value": 1450, "unit": "RPM", "last_read_at": "2026-10-01T12:39:00+03:00", "normal_range": {"min": 800, "max": 1800}},
                "power_consumption": {"value": 2.4, "unit": "kW", "last_read_at": "2026-10-01T12:39:00+03:00", "normal_range": {"min": 0.5, "max": 5}},
                "motor_temperature": {"value": 0, "unit": "°C", "last_read_at": "2026-10-01T12:40:00+03:00", "normal_range": {"min": 10, "max": 70}},
            },
        },
        {
            "id": "550e8400-e29b-41d4-a716-446655440007",
            "name": "Greenhouse Sensor 07",
            "connectivityType": "4G",
            "connectivityRenewType": "manual",
            "expiration_date": "2026-09-28",
            "readings": {
                "temperature": {"value": 30.2, "unit": "°C", "last_read_at": "2026-10-01T12:43:00+03:00", "normal_range": {"min": 15, "max": 35}},
                "humidity": {"value": 64.7, "unit": "%", "last_read_at": "2026-10-01T12:43:00+03:00", "normal_range": {"min": 40, "max": 85}},
                "ph": {"value": 6.9, "unit": "pH", "last_read_at": "2026-09-29T11:30:00+03:00", "normal_range": {"min": 5.5, "max": 7.5}},
                "soil_moisture": {"value": 47.3, "unit": "%", "last_read_at": "2026-10-01T12:42:00+03:00", "normal_range": {"min": 30, "max": 70}},
                "co2": {"value": 684, "unit": "ppm", "last_read_at": "2026-10-01T12:43:00+03:00", "normal_range": {"min": 400, "max": 1200}},
            },
        },
        {
            "id": "550e8400-e29b-41d4-a716-446655440008",
            "name": "Farm Station 08",
            "connectivityType": "WIFI",
            "connectivityRenewType": None,
            "expiration_date": None,
            "readings": {
                "temperature": {"value": 28.5, "unit": "°C", "last_read_at": "2026-10-01T12:35:00+03:00", "normal_range": {"min": 15, "max": 40}},
                "humidity": {"value": 61.9, "unit": "%", "last_read_at": "2026-10-01T12:35:00+03:00", "normal_range": {"min": 35, "max": 85}},
                "soil_moisture": {"value": 44.6, "unit": "%", "last_read_at": "2026-09-30T15:20:00+03:00", "normal_range": {"min": 30, "max": 70}},
                "wind_speed": {"value": 6.3, "unit": "km/h", "last_read_at": "2026-10-01T12:34:00+03:00", "normal_range": {"min": 0, "max": 50}},
                "rainfall": {"value": 0, "unit": "mm", "last_read_at": "2026-10-01T12:35:00+03:00", "normal_range": {"min": 0, "max": 100}},
            },
        },
        {
            "id": "550e8400-e29b-41d4-a716-446655440009",
            "name": "Irrigation Controller 09",
            "connectivityType": "4G",
            "connectivityRenewType": "manual",
            "expiration_date": "2026-10-12",
            "readings": {
                "temperature": {"value": 27.1, "unit": "°C", "last_read_at": "2026-10-01T12:41:00+03:00", "normal_range": {"min": 15, "max": 35}},
                "humidity": {"value": 69.5, "unit": "%", "last_read_at": "2026-10-01T12:41:00+03:00", "normal_range": {"min": 40, "max": 85}},
                "soil_moisture": {"value": 52.4, "unit": "%", "last_read_at": "2026-09-28T16:00:00+03:00", "normal_range": {"min": 30, "max": 70}},
                "water_flow": {"value": 11.8, "unit": "L/min", "last_read_at": "2026-10-01T12:40:00+03:00", "normal_range": {"min": 5, "max": 30}},
                "water_pressure": {"value": 2.5, "unit": "bar", "last_read_at": "2026-10-01T12:40:00+03:00", "normal_range": {"min": 1.5, "max": 4}},
            },
        },
        {
            "id": "550e8400-e29b-41d4-a716-446655440010",
            "name": "Soil Monitor 10",
            "connectivityType": "4G",
            "connectivityRenewType": "automatic",
            "expiration_date": None,
            "readings": {
                "temperature": {"value": 24.8, "unit": "°C", "last_read_at": "2026-10-01T12:44:00+03:00", "normal_range": {"min": 15, "max": 35}},
                "humidity": {"value": 76.2, "unit": "%", "last_read_at": "2026-10-01T12:44:00+03:00", "normal_range": {"min": 40, "max": 85}},
                "ph": {"value": 6.2, "unit": "pH", "last_read_at": "2026-09-28T13:45:00+03:00", "normal_range": {"min": 5.5, "max": 7.5}},
                "soil_moisture": {"value": 67.8, "unit": "%", "last_read_at": "2026-10-01T12:44:00+03:00", "normal_range": {"min": 30, "max": 70}},
                "nitrogen": {"value": 42, "unit": "mg/kg", "last_read_at": "2026-09-29T09:30:00+03:00", "normal_range": {"min": 20, "max": 80}},
            },
        },
        {
  "id": "550e8400-e29b-41d4-a716-446655440011",
  "name": "Field Sensor Hub 11",
  "connectivityType": "4G",
  "connectivityRenewType": "automatic",
  "expiration_date": "null",
  "readings": {
    "temperature": {
      "value": 0,
      "unit": "°C",
      "last_read_at": "2026-10-01T12:50:00+03:00",
      "normal_range": { "min": 15, "max": 35 }
    },
    "humidity": {
      "value": 0,
      "unit": "%",
      "last_read_at": "2026-10-01T12:50:00+03:00",
      "normal_range": { "min": 40, "max": 85 }
    },
    "ph": {
      "value": 0,
      "unit": "pH",
      "last_read_at": "2026-10-01T12:49:00+03:00",
      "normal_range": { "min": 5.5, "max": 7.5 }
    },
    "soil_moisture": {
      "value": 0,
      "unit": "%",
      "last_read_at": "2026-10-01T12:50:00+03:00",
      "normal_range": { "min": 30, "max": 70 }
    },
    "light_intensity": {
      "value": 0,
      "unit": "lux",
      "last_read_at": "2026-10-01T12:50:00+03:00",
      "normal_range": { "min": 500, "max": 50000 }
    }
  }
},
{
  "id": "550e8400-e29b-41d4-a716-446655440012",
  "name": "Field Sensor Hub 12",
  "connectivityType": "WIFI",
  "connectivityRenewType": "null",
  "expiration_date": "null",
  "readings": {
    "temperature": {
      "value": 0,
      "unit": "°C",
      "last_read_at": "2026-10-01T12:48:00+03:00",
      "normal_range": { "min": 15, "max": 35 }
    },
    "humidity": {
      "value": 0,
      "unit": "%",
      "last_read_at": "2026-10-01T12:48:00+03:00",
      "normal_range": { "min": 40, "max": 85 }
    },
    "ph": {
      "value": 0,
      "unit": "pH",
      "last_read_at": "2026-10-01T12:47:00+03:00",
      "normal_range": { "min": 5.5, "max": 7.5 }
    },
    "soil_moisture": {
      "value": 0,
      "unit": "%",
      "last_read_at": "2026-10-01T12:48:00+03:00",
      "normal_range": { "min": 30, "max": 70 }
    },
    "soil_conductivity": {
      "value": 0,
      "unit": "mS/cm",
      "last_read_at": "2026-10-01T12:48:00+03:00",
      "normal_range": { "min": 0.5, "max": 2.5 }
    }
  }
}
    ]
}
