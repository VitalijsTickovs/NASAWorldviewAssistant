from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import List, Optional

from langchain_core.tools import tool


WV_CONFIG_URL = "https://worldview.earthdata.nasa.gov/config/wv.json"
WV_BASE = "https://worldview.earthdata.nasa.gov/"

# Basic bbox hints (lonW,latS,lonE,latN)
BBOX_HINTS: dict[str, str] = {
    "bangladesh": "87,20,93,27",
    "california": "-130,32,-114,43",
    "greece": "18,34,30,42",
    "sahara": "-20,15,30,35",
    "amazon": "-75,-15,-45,5",
    "philippines": "117,5,127,21",
    "western canada": "-140,45,-110,65",
    "alps": "5,43,15,48",
    "japan": "128,30,148,46",
    "iceland": "-26,62,-12,68",
    "middle east": "30,12,60,38",
    "northern india": "74,22,87,32",
    "eastern europe": "18,44,40,56",
    "portugal": "-10,36,-5,43",
    "gulf of mexico": "-97,18,-81,30",
}


def _fetch_wv_config(timeout: int = 10) -> dict:
    req = urllib.request.Request(WV_CONFIG_URL, headers={"User-Agent": "Luma-Agent/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _iso_date(dt: Optional[str]) -> str:
    if not dt:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT00:00:00Z")
    try:
        # Accept common forms: YYYY-MM-DD, YYYY-MM-DDTHH:MM:SSZ
        if "T" in dt:
            parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromisoformat(dt + "T00:00:00+00:00")
        parsed = parsed.astimezone(timezone.utc)
        return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        # Fallback to today
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT00:00:00Z")


def _default_bbox() -> str:
    # whole world extent (lonW,latS,lonE,latN)
    return "-180,-90,180,90"


def _prefer_true_color(config: dict) -> Optional[str]:
    preferred_ids = [
        "VIIRS_SNPP_CorrectedReflectance_TrueColor",
        "MODIS_Terra_CorrectedReflectance_TrueColor",
        "MODIS_Aqua_CorrectedReflectance_TrueColor",
    ]
    layers = config.get("layers", {})
    for pid in preferred_ids:
        if pid in layers:
            return pid
    # fallback: any layer id or title containing CorrectedReflectance_TrueColor
    for layer_id, meta in layers.items():
        title = str(meta.get("title", ""))
        if "CorrectedReflectance_TrueColor" in layer_id or "True Color" in title:
            return layer_id
    return None


KEYWORD_HINTS: dict[str, List[str]] = {
    # keyword -> patterns that, if present in layer id, boost score
    "fire": ["Thermal_Anomalies", "Fires", "FIRMS", "VIIRS", "MODIS"],
    "fires": ["Thermal_Anomalies", "Fires", "FIRMS", "VIIRS", "MODIS"],
    "smoke": ["Aerosol", "AOD", "Smoke"],
    "aerosol": ["Aerosol", "AOD", "OMI", "VIIRS", "MODIS"],
    "aod": ["AOD", "Aerosol"],
    "dust": ["Dust", "Aerosol", "AI"],
    "snow": ["Snow", "Snow_Cover", "SC"],
    "sst": ["Sea_Surface_Temperature", "SST", "GHRSST", "VIIRS"],
    "temperature": ["Temperature", "SST"],
    "true color": ["CorrectedReflectance_TrueColor"],
    "flood": ["Flood", "Surface_Water", "Water_Extent"],
    "flooding": ["Flood", "Surface_Water", "Water_Extent"],
}


def _offline_select_from_query(q: str) -> List[str]:
    """Heuristic layer picks when config search is unavailable or too narrow."""
    ql = q.lower()
    picks: List[str] = []
    if any(k in ql for k in ["fire", "fires", "wildfire", "wildfires"]):
        picks.append("MODIS_Terra_Thermal_Anomalies_Night")
    if any(k in ql for k in ["smoke", "aerosol", "aod", "haze", "plume"]):
        picks.append("MODIS_Terra_Aerosol")
    if any(k in ql for k in ["snow", "snow cover", "ice", "glacier"]):
        picks.append("MODIS_Terra_Snow_Cover_Daily")
    if any(k in ql for k in ["sst", "sea surface temperature", "sea-surface temperature", "ocean temp"]):
        picks.append("GHRSST_L4_MUR_Sea_Surface_Temperature")
    if any(k in ql for k in ["ash", "volcanic", "volcano", "so2"]):
        picks.append("OMI_SO2_Column_Amount")
    if any(k in ql for k in ["flood", "flooding", "surface water", "water extent", "inundation"]):
        picks.append("VIIRS_SNPP_Flood_Water_Composite")
    if any(k in ql for k in ["dust", "sand", "blowing dust"]):
        picks.append("OMI_Aerosol_Index")
    out: List[str] = []
    for lid in picks:
        if lid and lid not in out:
            out.append(lid)
    return out[:3]


def _split_query_parts(q: str) -> List[str]:
    q = q.lower()
    # split on common separators indicating multiple requested layers/phenomena
    seps = ["+", ",", " and ", " & "]
    parts = [q]
    for sep in seps:
        tmp = []
        for p in parts:
            tmp.extend([s.strip() for s in p.split(sep) if s.strip()])
    parts = tmp
    # strip leading connectors like "show", "give me", "over", "in"
    cleaned = []
    for p in parts:
        for prefix in ["show ", "give me ", "display ", "visualize ", "map ", "over ", "in ", "around ", "near "]:
            if p.startswith(prefix):
                p = p[len(prefix):]
        cleaned.append(p.strip())
    # dedupe while preserving order
    seen = set()
    out = []
    for p in cleaned:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _search_layers(config: dict, query: str, max_layers: int = 4) -> List[str]:
    """
    Keyword search across layer titles/IDs. Supports combined queries
    like "true color + smoke" and returns multiple best-matching layers.
    """
    layers = config.get("layers", {})
    if not isinstance(layers, dict) or not layers:
        return []

    parts = _split_query_parts(query)
    selected: list[str] = []

    def score_layer(layer_id: str, meta: dict, qpart: str) -> int:
        title = str(meta.get("title", ""))
        id_l = layer_id
        title_l = title.lower()
        score = 0
        # direct containment
        if qpart and (qpart in title_l or qpart in id_l.lower()):
            score += 10
        # token overlap
        tokens = [t for t in qpart.replace(",", " ").split() if t]
        for t in tokens:
            if t in title_l:
                score += 2
            if t in id_l.lower():
                score += 1
        # keyword hints
        for kw, patterns in KEYWORD_HINTS.items():
            if kw in qpart:
                for pat in patterns:
                    if pat.lower() in id_l.lower() or pat.lower() in title_l:
                        score += 3
        return score

    # Score and pick one best layer per query part (if available)
    for part in parts:
        scores: list[tuple[int, str]] = []
        for lid, meta in layers.items():
            s = score_layer(lid, meta, part)
            if s > 0:
                scores.append((s, lid))
        scores.sort(key=lambda x: x[0], reverse=True)
        for _, lid in scores:
            if lid not in selected:
                selected.append(lid)
                break
        if len(selected) >= max_layers:
            break

    # Ensure a base true color layer if user hinted at it or if we only picked 1 overlay
    has_true_color = any("CorrectedReflectance_TrueColor" in lid for lid in selected)
    if ("true color" in query.lower() or len(selected) == 1) and not has_true_color:
        tc = _prefer_true_color(config)
        if tc and tc not in selected:
            selected.insert(0, tc)

    # Trim to max_layers
    return selected[:max_layers]


def _build_worldview_url(layers: List[str], t: str, bbox: Optional[str]) -> str:
    params = []
    if layers:
        params.append("l=" + ",".join(layers))
    params.append("t=" + t)
    params.append("v=" + (bbox or _default_bbox()))
    return WV_BASE + "?" + "&".join(params)


def _infer_bbox(query: str, provided: Optional[str]) -> Optional[str]:
    if provided:
        return provided
    ql = query.lower()
    for key, value in BBOX_HINTS.items():
        if key in ql:
            return value
    return None


@tool("worldview_link", return_direct=False)
def worldview_link(
    query: str,
    date: Optional[str] = None,
    bbox: Optional[str] = None,
    layers: Optional[List[str]] = None,
) -> str:
    """
    Build a NASA Worldview URL for requested imagery.

    Inputs:
    - query: Natural-language description of desired layers (e.g., "fires in California")
    - date: Optional ISO date (YYYY-MM-DD or full ISO). Defaults to today.
    - bbox: Optional bounding box "lonW,latS,lonE,latN". Defaults to world extent.
    - layers: Optional explicit list of layer IDs to include; overrides search.

    Returns a direct Worldview URL that opens the map with those layers/date/bbox.
    """
    t = _iso_date(date)

    bbox_val = _infer_bbox(query, bbox)

    if layers and len(layers) > 0:
        selected = list(layers)
    else:
        config: Optional[dict] = None
        selected: List[str] = []
        try:
            config = _fetch_wv_config()
            selected = _search_layers(config, query)
            if not selected:
                selected = ["MODIS_Terra_CorrectedReflectance_TrueColor"]
        except Exception:
            selected = ["MODIS_Terra_CorrectedReflectance_TrueColor"]
            config = None

        heuristic = _offline_select_from_query(query)
        for lid in heuristic:
            if lid not in selected:
                selected.append(lid)
                if len(selected) >= 4:
                    break

        has_true_color = any("CorrectedReflectance_TrueColor" in lid for lid in selected)
        if not has_true_color:
            # Add base true color if user asked for it or we only have overlays
            if "true color" in query.lower() or (len(selected) == 1):
                if config is not None:
                    tc = _prefer_true_color(config)
                else:
                    tc = "MODIS_Terra_CorrectedReflectance_TrueColor"
                if tc and tc not in selected:
                    selected.insert(0, tc)

    selected = selected[:4]

    url = _build_worldview_url(selected, t, bbox_val)
    return url
