"""
Geography Service - Kenya Administrative & Electoral Hierarchy.
Loads authoritative reference data covering all 47 Counties, Constituencies/Sub-Counties,
Wards, and Popular Urban Localities (Runda, Karen, Embakasi, etc.).
"""

import os
import json
from typing import Dict, List, Optional, Any

class GeographyService:
    def __init__(self, json_path: Optional[str] = None):
        if not json_path:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
            json_path = os.path.join(base_dir, 'kenya_geography.json')
        self.json_path = json_path
        self._data: Dict[str, Any] = {}
        self._counties_by_name: Dict[str, Dict[str, Any]] = {}
        self._load_data()

    def _load_data(self):
        try:
            if os.path.exists(self.json_path):
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                    for c in self._data.get('counties', []):
                        self._counties_by_name[c['name'].lower()] = c
        except Exception as e:
            print(f"[GeographyService] Warning: Could not load {self.json_path}: {e}")

    def get_all_counties(self) -> List[Dict[str, Any]]:
        """Returns list of all 47 counties."""
        return [
            {"code": c.get("code"), "name": c["name"], "capital": c.get("capital", "")}
            for c in self._data.get("counties", [])
        ]

    def get_county_data(self, county_name: str) -> Optional[Dict[str, Any]]:
        if not county_name or county_name.lower() in ('all', 'all counties (kenya)'):
            return None
        return self._counties_by_name.get(county_name.lower().strip())

    def get_constituencies(self, county_name: str) -> List[str]:
        """Returns constituencies / sub-counties for a specific county."""
        c_data = self.get_county_data(county_name)
        if not c_data:
            return []
        return [c["name"] for c in c_data.get("constituencies", [])]

    def get_wards(self, county_name: str, constituency_name: Optional[str] = None) -> List[str]:
        """Returns wards for a county, optionally filtered by constituency."""
        c_data = self.get_county_data(county_name)
        if not c_data:
            return []
        wards = []
        for const in c_data.get("constituencies", []):
            if not constituency_name or constituency_name.lower() in ('all', 'all constituencies', 'all sub-counties') or const["name"].lower() == constituency_name.lower():
                wards.extend(const.get("wards", []))
        return sorted(list(set(wards)))

    def get_localities(self, county_name: str, constituency_name: Optional[str] = None) -> List[str]:
        """Returns popular localities / places for a county or constituency."""
        c_data = self.get_county_data(county_name)
        if not c_data:
            return []
        locs = list(c_data.get("localities", []))
        if constituency_name and constituency_name.lower() not in ('all', 'all constituencies', 'all sub-counties'):
            for const in c_data.get("constituencies", []):
                if const["name"].lower() == constituency_name.lower():
                    locs.extend(const.get("localities", []))
        return sorted(list(set(locs)))

    def search_location(self, query: str) -> List[Dict[str, Any]]:
        """Searches across counties, constituencies, wards, and localities."""
        q = (query or "").strip().lower()
        if not q or len(q) < 2:
            return []
        results = []
        for c in self._data.get("counties", []):
            c_name = c["name"]
            if q in c_name.lower():
                results.append({"type": "County", "name": c_name, "county": c_name})
            for const in c.get("constituencies", []):
                const_name = const["name"]
                if q in const_name.lower():
                    results.append({"type": "Sub-County / Constituency", "name": const_name, "county": c_name})
                for w in const.get("wards", []):
                    if q in w.lower():
                        results.append({"type": "Ward", "name": w, "county": c_name, "sub_county": const_name})
            for loc in c.get("localities", []):
                if q in loc.lower():
                    results.append({"type": "Locality", "name": loc, "county": c_name})
        return results[:30]


geography_service = GeographyService()

