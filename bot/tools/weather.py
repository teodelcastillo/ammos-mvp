import httpx

weather_tools = [
    {
        "name": "weather_get_forecast",
        "description": "Obtiene el pronóstico del clima. Por defecto para Córdoba, Argentina.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Ciudad para el pronóstico (default: Córdoba)",
                },
                "days": {
                    "type": "integer",
                    "description": "Días de pronóstico, 1 a 7 (default: 3)",
                },
            },
            "required": [],
        },
    },
]

_WEATHER_CODES = {
    0: "Despejado",
    1: "Mayormente despejado",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Niebla",
    48: "Niebla con escarcha",
    51: "Llovizna leve",
    53: "Llovizna moderada",
    55: "Llovizna intensa",
    61: "Lluvia leve",
    63: "Lluvia moderada",
    65: "Lluvia intensa",
    71: "Nevada leve",
    73: "Nevada moderada",
    75: "Nevada intensa",
    80: "Chubascos leves",
    81: "Chubascos moderados",
    82: "Chubascos intensos",
    95: "Tormenta",
    96: "Tormenta con granizo leve",
    99: "Tormenta con granizo fuerte",
}


async def handle_weather_tool(name: str, input_data: dict) -> dict:
    if name == "weather_get_forecast":
        return await _get_forecast(input_data)
    return {"error": f"Tool desconocido: {name}"}


async def _get_forecast(data: dict) -> dict:
    city = data.get("city", "Córdoba")
    days = min(max(data.get("days", 3), 1), 7)

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Geocode city
        geo = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "es"},
        )
        geo_data = geo.json()

        if not geo_data.get("results"):
            return {"error": f"No se encontró la ciudad: {city}"}

        loc = geo_data["results"][0]

        # Weather forecast
        wx = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                "current_weather": True,
                "timezone": "America/Argentina/Cordoba",
                "forecast_days": days,
            },
        )
        wx_data = wx.json()

        current = wx_data.get("current_weather", {})
        daily = wx_data.get("daily", {})

        forecast = []
        for i in range(len(daily.get("time", []))):
            code = daily["weathercode"][i]
            forecast.append(
                {
                    "date": daily["time"][i],
                    "temp_max": daily["temperature_2m_max"][i],
                    "temp_min": daily["temperature_2m_min"][i],
                    "precipitation_probability": daily["precipitation_probability_max"][i],
                    "condition": _WEATHER_CODES.get(code, f"Código {code}"),
                }
            )

        return {
            "city": loc["name"],
            "country": loc.get("country", ""),
            "current": {
                "temperature": current.get("temperature"),
                "condition": _WEATHER_CODES.get(current.get("weathercode", -1), "Desconocido"),
                "windspeed": current.get("windspeed"),
            },
            "forecast": forecast,
        }
