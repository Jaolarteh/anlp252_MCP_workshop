from typing import Any, Dict, List, Optional
import httpx
from mcp.server.fastmcp import FastMCP

# =========================================================
#  MCP Server: Weather (Open-Meteo)
# =========================================================
mcp = FastMCP("weather")

OPEN_METEO_BASE = "https://api.open-meteo.com/v1"
DEFAULT_TIMEOUT = 30.0

# ---------------------------------------------------------
# Utilidades
# ---------------------------------------------------------
def _units_map(units: str) -> Dict[str, str]:
    """
    Mapea 'metric'/'imperial' a parámetros de Open-Meteo.
    """
    u = (units or "metric").lower()
    if u == "imperial":
        return {
            "temperature_unit": "fahrenheit",
            "windspeed_unit": "mph",
            "precipitation_unit": "inch",
        }
    # default metric
    return {
        "temperature_unit": "celsius",
        "windspeed_unit": "kmh",
        "precipitation_unit": "mm",
    }

def _code_to_text(code: int, language: str = "es") -> str:
    """
    Traducción básica de weathercode de Open-Meteo.
    (Cobertura de los códigos más comunes)
    """
    # Referencia: https://open-meteo.com/en/docs (Weather codes)
    map_es = {
        0: "Despejado",
        1: "Mayormente despejado",
        2: "Parcialmente nublado",
        3: "Nublado",
        45: "Niebla",
        48: "Niebla con escarcha",
        51: "Llovizna ligera",
        53: "Llovizna moderada",
        55: "Llovizna intensa",
        56: "Llovizna congelante ligera",
        57: "Llovizna congelante intensa",
        61: "Lluvia ligera",
        63: "Lluvia moderada",
        65: "Lluvia fuerte",
        66: "Lluvia helada ligera",
        67: "Lluvia helada intensa",
        71: "Nevadas ligeras",
        73: "Nevadas moderadas",
        75: "Nevadas fuertes",
        77: "Granos de nieve",
        80: "Chubascos ligeros",
        81: "Chubascos moderados",
        82: "Chubascos violentos",
        85: "Chubascos de nieve ligeros",
        86: "Chubascos de nieve fuertes",
        95: "Tormenta",
        96: "Tormenta con granizo ligero",
        97: "Tormenta con granizo fuerte",
    }
    map_en = {
        0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Depositing rime fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        56: "Light freezing drizzle", 57: "Freezing drizzle",
        61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
        66: "Light freezing rain", 67: "Freezing rain",
        71: "Light snow", 73: "Moderate snow", 75: "Heavy snow",
        77: "Snow grains",
        80: "Light showers", 81: "Moderate showers", 82: "Violent showers",
        85: "Light snow showers", 86: "Heavy snow showers",
        95: "Thunderstorm", 96: "Thunderstorm with slight hail", 97: "…with heavy hail",
    }
    table = map_es if language.lower().startswith("es") else map_en
    return table.get(int(code), f"Código {code}")

async def _om_get(path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    GET a Open-Meteo con manejo de errores.
    """
    url = f"{OPEN_METEO_BASE}/{path}"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

def _fmt_alert_item(a: Dict[str, Any], language: str) -> str:
    # Estructura típica de warnings de Open-Meteo (puede variar por región/proveedor)
    # Tomamos campos comunes de forma defensiva.
    headline = a.get("headline") or a.get("event") or "Alerta"
    severity = a.get("severity") or a.get("level") or "desconocida"
    description = (
        a.get("description") or
        a.get("instruction") or
        a.get("text") or
        "Sin descripción"
    )
    sender = a.get("sender") or a.get("provider") or ""
    onset = a.get("onset") or a.get("effective") or ""
    expires = a.get("expires") or a.get("ends") or ""

    if language.lower().startswith("es"):
        return (
            f"⚠️ {headline}\n"
            f"Severidad: {severity}\n"
            f"Desde: {onset or 'N/D'}  Hasta: {expires or 'N/D'}\n"
            f"Fuente: {sender or 'N/D'}\n"
            f"Detalle: {description}\n"
        )
    else:
        return (
            f"⚠️ {headline}\n"
            f"Severity: {severity}\n"
            f"From: {onset or 'N/A'}  Until: {expires or 'N/A'}\n"
            f"Source: {sender or 'N/A'}\n"
            f"Details: {description}\n"
        )

# ---------------------------------------------------------
# Tools
# ---------------------------------------------------------
@mcp.tool()
async def get_forecast(
    latitude: float,
    longitude: float,
    days: int = 3,
    units: str = "metric",
    language: str = "es",
) -> str:
    """
    Pronóstico global vía Open-Meteo.

    Args:
        latitude: Latitud del punto.
        longitude: Longitud del punto.
        days: Días a pronosticar (1-16 aprox. según modelo).
        units: 'metric' (°C, km/h) o 'imperial' (°F, mph).
        language: 'es' o 'en' (afecta textos, no los datos crudos).
    """
    if days < 1:
        days = 1
    if days > 16:
        days = 16

    um = _units_map(units)
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "auto",
        "forecast_days": days,
        # resumen/daily
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "windspeed_10m_max",
            "weathercode",
        ],
        # condiciones actuales
        "current": ["temperature_2m", "windspeed_10m", "weathercode"],
        # unidades
        "temperature_unit": um["temperature_unit"],
        "windspeed_unit": um["windspeed_unit"],
        "precipitation_unit": um["precipitation_unit"],
    }

    data = await _om_get("forecast", params)
    if not data:
        return "No pude obtener el pronóstico de Open-Meteo."

    out: List[str] = []
    cur = data.get("current", {})
    if cur:
        tc = cur.get("temperature_2m")
        wc = cur.get("weathercode")
        ws = cur.get("windspeed_10m")
        line = (
            f"Ahora: {tc}° "
            f"| Viento: {ws} {um['windspeed_unit']} "
            f"| Cielo: {_code_to_text(wc, language)}"
        )
        out.append(line)

    daily = data.get("daily", {})
    dates = daily.get("time", []) or []
    tmax = daily.get("temperature_2m_max", []) or []
    tmin = daily.get("temperature_2m_min", []) or []
    prcp = daily.get("precipitation_sum", []) or []
    wmax = daily.get("windspeed_10m_max", []) or []
    wcode = daily.get("weathercode", []) or []

    out.append("")  # separación

    for i, d in enumerate(dates):
        try:
            line = (
                f"{d}: "
                f"máx {tmax[i]}°, mín {tmin[i]}°, "
                f"lluvia {prcp[i]} {um['precipitation_unit']}, "
                f"viento máx {wmax[i]} {um['windspeed_unit']}, "
                f"{_code_to_text(wcode[i], language)}"
            )
            out.append(line)
        except Exception:
            # por si alguna lista viene más corta
            continue

    return "\n".join(out).strip()

@mcp.tool()
async def get_alerts(
    latitude: float,
    longitude: float,
    language: str = "es",
) -> str:
    """
    Alertas/avisos severos cercanos vía Open-Meteo Warnings.

    Args:
        latitude: Latitud
        longitude: Longitud
        language: 'es' o 'en'
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "auto",
        # algunos proveedores soportan 'severity', 'origin', etc.; mantenemos simple
    }
    data = await _om_get("warnings", params)
    if not data:
        return "No pude obtener alertas (o el servicio no tiene cobertura para esta ubicación)."

    # Open-Meteo suele devolver una lista 'warnings' o similar.
    warnings = data.get("warnings") or data.get("events") or data.get("alerts") or []
    if not warnings:
        return "Sin alertas activas para estas coordenadas."

    formatted = [_fmt_alert_item(w, language) for w in warnings]
    return "\n---\n".join(formatted)


if __name__ == "__main__":
    mcp.run()
