#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
geofetch.registry
~~~~~~~~~~~~~

This module contains the Module Registry for the GeoFetch library. 

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import importlib
import copy

logger = logging.getLogger(__name__)

# =============================================================================
# GeoFetch Registry
# =============================================================================
class GeoFetchRegistry:
    """GeoFetch Module Registry with rich metadata for discovery."""
    
    _modules = {
        'https': {'mod': 'geofetch.core', 'cls': 'HttpDataset', 'category': 'Generic'},
        # GMRT
        'gmrt': {
            'mod': 'geofetch.modules.gmrt', 
            'cls': 'GMRT', 
            'category': 'Bathymetry',
            'desc': 'Global Multi-Resolution Topography Synthesis',
            'agency': 'Lamont-Doherty Earth Observatory',
            'tags': ['bathymetry', 'ocean', 'global', 'synthesis', 'grid'],
            'region': 'Global',
            'resolution': 'Varies (100m - 400m)',
            'license': 'CC-BY-4.0',
            'urls': {
                'home': 'https://www.gmrt.org',
                'citation': 'https://www.gmrt.org/about/citation.php'
            }
        },

        # Copernicus DEMs
        'copernicus': {
            'mod': 'geofetch.modules.copernicus', 
            'cls': 'CopernicusDEM', 
            'category': 'Topography',
            'desc': 'Copernicus Global/European Digital Elevation Models (COP-30/10)',
            'agency': 'ESA/Eurostat',
            'tags': ['satellite', 'dsm', 'radar', 'global', 'europe'],
            'region': 'Global (COP-30) / Europe (COP-10)',
            'resolution': '30m / 10m',
            'license': 'Open Data / attribution required',
            'urls': {
                'home': 'https://ec.europa.eu/eurostat/web/gisco/geodata/reference-data/elevation/copernicus-dem',
                'docs': 'https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model'
            }
        },
        # The National Map (TNM) / USGS
        'tnm': {
            'mod': 'geofetch.modules.tnm', 
            'cls': 'TheNationalMap', 
            'category': 'Topography',
            'desc': 'USGS 3DEP Products (NED, Lidar, Hydro) via The National Map',
            'agency': 'USGS',
            'tags': ['usgs', 'ned', '3dep', 'lidar', 'usa', 'elevation'],
            'region': 'USA',
            'resolution': 'Varies (1m - 1 arc-second)',
            'license': 'Public Domain (USGS)',
            'urls': {
                'home': 'https://apps.nationalmap.gov/',
                'api': 'https://tnmaccess.nationalmap.gov/api/v1/docs/'
            }
        },
        # TNM Shortcuts / Other USGS errata
        'ned': {
            'inherits': 'tnm',
            'mod': 'geofetch.modules.tnm', 
            'cls': 'NED', 
            'category': 'Topography', 
            'desc': 'USGS Seamless DEMs (1m, 1/3", 1")',
            'aliases': ['3dep_dem', 'NED']
        },
        '3dep': {
            'inherits': 'tnm',
            'mod': 'geofetch.modules.tnm', 
            'cls': 'TNM_LAZ', 
            'category': 'Topography', 
            'desc': 'USGS 3DEP Lidar Point Clouds (LAZ)',
            'aliases': ['3dep_lidar']
        },

        '3dep_cp': {
            'mod': 'geofetch.modules.checkpoints_3dep', 
            'cls': 'CheckPoints3DEP', 
            'category': 'Reference',
            'desc': 'USGS 3DEP Elevation Validation Checkpoints',
            'agency': 'USGS',
            'tags': ['usgs', '3dep', 'checkpoints', 'validation', 'accuracy', 'control-points'],
            'region': 'USA',
            'resolution': 'Point Data',
            'license': 'Public Domain',
            'urls': {
                'home': 'https://www.usgs.gov/3d-elevation-program',
                'source': 'https://www.sciencebase.gov/catalog/item/67075e6bd34e969edc59c3e7'
            }
        },

        # NASA EarthData
        'earthdata': {
            'mod': 'geofetch.modules.earthdata', 
            'cls': 'EarthData', 
            'category': 'Generic',
            'desc': 'NASA Earth Science Data via CMR & Harmony',
            'agency': 'NASA',
            'tags': ['nasa', 'cmr', 'harmony', 'satellite', 'earth-science', 'remote-sensing'],
            'region': 'Global',
            'resolution': 'Varies',
            'license': 'NASA Data and Information Policy (Open)',
            'urls': {
                'home': 'https://earthdata.nasa.gov/',
                'search': 'https://search.earthdata.nasa.gov/'
            }
        },
        # EarthData Shortcuts
        'icesat2': {
            'inherits': 'earthdata',
            'cls': 'IceSat2',
            'category': 'Topography',
            'desc': 'NASA IceSat-2 Laser Altimetry (ATL03/ATL08)',
            'tags': ['lidar', 'icesat2', 'atl03', 'atl08', 'elevation', 'photon'],
            'resolution': 'Photon / 100m'
        },        
        'swot': {
            'inherits': 'earthdata',
            'cls': 'SWOT',
            'category': 'Oceanography',
            'desc': 'Surface Water and Ocean Topography (SWOT) Ka-band Radar',
            'tags': ['swot', 'hydrology', 'oceanography', 'water-height', 'karin']
        },        
        'mur_sst': {
            'inherits': 'earthdata',
            'cls': 'MUR_SST',
            'category': 'Oceanography',
            'desc': 'MUR Level 4 Global Sea Surface Temperature',
            'tags': ['sst', 'temperature', 'ocean', 'mur', 'l4'],
            'resolution': '0.01 degree (~1km)'
        },

        # Multibeam (NOAA)
        'multibeam': {
            'mod': 'geofetch.modules.multibeam', 
            'cls': 'Multibeam', 
            'category': 'Bathymetry',
            'desc': 'NOAA NCEI Multibeam Bathymetry (Global)',
            'agency': 'NOAA NCEI',
            'tags': ['bathymetry', 'multibeam', 'ocean', 'sonar', 'noaa', 'ncei'],
            'region': 'Global',
            'resolution': 'Varies (10m - 100m)',
            'license': 'Public Domain',
            'urls': {'home': 'https://www.ngdc.noaa.gov/mgg/bathymetry/multibeam.html'}
        },        
        'mbdb': {
            'mod': 'geofetch.modules.multibeam', 
            'cls': 'MBDB', 
            'category': 'Bathymetry',
            'desc': 'NOAA Multibeam via ArcGIS Feature Server',
            'agency': 'NOAA NCEI',
            'tags': ['bathymetry', 'arcgis', 'feature-server'],
            'inherits': 'multibeam'
        },
        'r2r': {
            'mod': 'geofetch.modules.multibeam', 
            'cls': 'R2R', 
            'category': 'Bathymetry',
            'desc': 'Rolling Deck to Repository (R2R) Multibeam',
            'agency': 'NSF / R2R',
            'tags': ['bathymetry', 'research-vessels', 'academic', 'r2r'],
            'region': 'Global',
            'resolution': 'Raw Swath Data',
            'license': 'Academic / Public',
            'urls': {'home': 'https://www.rvdata.us/'}
        },

        # HydroNOS
        'nos_hydro': {
            'mod': 'geofetch.modules.hydronos', 
            'cls': 'HydroNOS', 
            'category': 'Bathymetry',
            'desc': 'NOAA NOS Hydrographic Surveys (BAG & XYZ)',
            'agency': 'NOAA NOS',
            'tags': ['bathymetry', 'hydrography', 'nos', 'noaa', 'bag', 'soundings'],
            'region': 'USA / Coastal',
            'resolution': 'Varies (0.5m - 30m)',
            'license': 'Public Domain',
            'urls': {'home': 'https://www.ngdc.noaa.gov/mgg/bathymetry/hydro.html'}
        },        
        # Shortcut for just BAGs
        'bag': {
            'mod': 'geofetch.modules.hydronos', 
            'cls': 'HydroNOS', 
            'category': 'Bathymetry',
            'desc': 'NOAA NOS Bathymetric Attributed Grids (BAG)',
            'inherits': 'nos_hydro'
        },

        # Nautical Charts (NOAA)
        'charts': {
            'mod': 'geofetch.modules.charts', 
            'cls': 'NOAACharts', 
            'category': 'Reference',
            'desc': 'NOAA Nautical Charts (ENC)',
            'agency': 'NOAA NOS',
            'tags': ['charts', 'nautical', 'enc', 'rnc', 'navigation', 'ocean'],
            'region': 'USA / Coastal',
            'resolution': 'Varies',
            'license': 'Public Domain',
            'urls': {'home': 'https://www.charts.noaa.gov/'}
        },        
        
        # Nominatum
        'nominatim': {
            'mod': 'geofetch.modules.nominatim', 
            'cls': 'Nominatim', 
            'category': 'Reference',
            'desc': 'Geocoding service using OpenStreetMap data',
            'agency': 'OpenStreetMap Foundation',
            'tags': ['geocode', 'osm', 'search', 'coordinates', 'place'],
            'region': 'Global',
            'resolution': 'N/A',
            'license': 'ODbL (Open Data Commons Open Database License)',
            'urls': {
                'home': 'https://nominatim.org/',
                'policy': 'https://operations.osmfoundation.org/policies/nominatim/'
            }
        },        
    }

    
    @classmethod
    def get_info(cls, mod_key: str) -> dict:
        """Retrieve the full metadata dictionary for a module, 
        resolving inheritance.
        """
        
        # Resolve aliases first
        if mod_key not in cls._modules:
            for k, v in cls._modules.items():
                if mod_key in v.get('aliases', []):
                    mod_key = k
                    break
        
        if mod_key not in cls._modules:
            return {}

        entry = cls._modules[mod_key]
        
        if 'inherits' in entry:
            parent_key = entry['inherits']
            parent = cls.get_info(parent_key)
            
            merged = copy.deepcopy(parent)
            
            for k, v in entry.items():
                if k == 'tags' and 'tags' in merged:
                    merged['tags'] = list(set(merged['tags'] + v))
                elif k == 'urls' and 'urls' in merged:
                    merged['urls'].update(v)
                else:
                    merged[k] = v
            
            return merged
            
        return entry

    
    @classmethod
    def load_module(cls, mod_key: str):
        """Dynamically import and return the class."""
        
        info = cls.get_info(mod_key)
        if not info:
            return None

        try:
            module = importlib.import_module(info['mod'])
            mod_cls = getattr(module, info['cls'])
            return mod_cls
        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to lazy load {mod_key}: {e}")
            return None

        
    @classmethod
    def search_modules(cls, query: str) -> list:
        """Search modules by matching the query string against:
        Name, Description, Agency, Tags, License, Category, and Aliases.
        """
        
        query = query.lower()
        matches = []
        
        for key in cls._modules.keys():
            meta = cls.get_info(key)
            
            searchable_text = [
                key,
                meta.get('desc', ''),
                meta.get('agency', ''),
                meta.get('category', ''),
                meta.get('license', '')
            ]
            
            searchable_text.extend(meta.get('tags', []))
            searchable_text.extend(meta.get('aliases', []))
            
            if any(query in s.lower() for s in searchable_text):
                matches.append(key)
                
        return sorted(matches)
