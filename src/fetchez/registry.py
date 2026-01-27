#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.registry
~~~~~~~~~~~~~

This module contains the Module Registry for the Fetchez library. 

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging
import importlib
import copy

logger = logging.getLogger(__name__)

# =============================================================================
# Fetchez Registry
#
# Each module in the registry should have *AT LEAST* `mod` and `cls` defined
# correctly for the specific module so fetchez can call it correctly.
#
# It is highly encouraged to fill out all the metadata for every fetchez module.
# In addition to the *MANDATORY* fields mentioned above, we would also like:
#   `category`, `desc`, `agency`, `tags, `region`, `resolution`, `license` and `urls`
#
# This will ensure the registry is robust and useful for everyone.
#
# You can also set the optional `aliases` field, to give the module aliases.
# If a fetchez module has the same metadata as one that already exists, you
# can set the `inherits` key to that other module to avoid duplicating
# metadata. (`mod` and `cls` still need to set correctly.
# =============================================================================
class FetchezRegistry:
    """Fetchez Module Registry with rich metadata for discovery."""
            
    _modules = {
        
        # Generic https module to send an argument to FetchModule.results
        'https': {'mod': 'fetchez.core', 'cls': 'HttpDataset', 'category': 'Generic'},
        
        # GMRT
        'gmrt': {
            'mod': 'fetchez.modules.gmrt', 
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
            'mod': 'fetchez.modules.copernicus', 
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

        # NOAA ETOPO-2022
        'etopo': {
            'mod': 'fetchez.modules.etopo', 
            'cls': 'ETOPO', 
            'category': 'Topography',
            'desc': 'ETOPO 2022 Global Relief Model (15s, 30s, 60s)',
            'agency': 'NOAA NCEI',
            'tags': ['topography', 'bathymetry', 'elevation', 'global', 'etopo', 'relief'],
            'region': 'Global',
            'resolution': '15s (~450m) to 60s (~1.8km)',
            'license': 'Public Domain',
            'urls': {'home': 'https://www.ncei.noaa.gov/products/etopo-global-relief-model'}
        },
        
        # The National Map (TNM) / USGS and Shortcuts (ned/3dep/etc)
        'tnm': {
            'mod': 'fetchez.modules.tnm', 
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
        'ned': {
            'inherits': 'tnm',
            'mod': 'fetchez.modules.tnm', 
            'cls': 'NED', 
            'category': 'Topography', 
            'desc': 'USGS Seamless DEMs (1m, 1/3", 1")',
            'aliases': ['3dep_dem', 'NED']
        },
        '3dep': {
            'inherits': 'tnm',
            'mod': 'fetchez.modules.tnm', 
            'cls': 'TNM_LAZ', 
            'category': 'Topography', 
            'desc': 'USGS 3DEP Lidar Point Clouds (LAZ)',
            'aliases': ['3dep_lidar']
        },

        # USGS Checkpoints
        '3dep_cp': {
            'mod': 'fetchez.modules.checkpoints_3dep', 
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

        # USGS Waterservices
        'waterservices': {
            'mod': 'fetchez.modules.waterservices', 
            'cls': 'WaterServices', 
            'category': 'Hydrography',
            'desc': 'USGS Water Services (Streamflow/River Data)',
            'agency': 'USGS',
            'tags': ['water', 'streamflow', 'river', 'usgs', 'hydrology', 'realtime'],
            'region': 'USA',
            'resolution': 'Point Data',
            'license': 'Public Domain',
            'urls': {'home': 'https://waterservices.usgs.gov/'}
        },
        
        # NASA EarthData
        'earthdata': {
            'mod': 'fetchez.modules.earthdata', 
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
            'mod': 'fetchez.modules.multibeam', 
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
            'mod': 'fetchez.modules.multibeam', 
            'cls': 'MBDB', 
            'category': 'Bathymetry',
            'desc': 'NOAA Multibeam via ArcGIS Feature Server',
            'agency': 'NOAA NCEI',
            'tags': ['bathymetry', 'arcgis', 'feature-server'],
            'inherits': 'multibeam'
        },
        'r2r': {
            'mod': 'fetchez.modules.multibeam', 
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
            'mod': 'fetchez.modules.hydronos', 
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
            'mod': 'fetchez.modules.hydronos', 
            'cls': 'HydroNOS', 
            'category': 'Bathymetry',
            'desc': 'NOAA NOS Bathymetric Attributed Grids (BAG)',
            'inherits': 'nos_hydro'
        },

        # Coast Survey's BlueTopo
        'bluetopo': {
            'mod': 'fetchez.modules.bluetopo', 
            'cls': 'BlueTopo', 
            'category': 'Bathymetry',
            'desc': 'NOAA BlueTopo (National Bathymetric Source)',
            'agency': 'NOAA OCS',
            'tags': ['bathymetry', 'noaa', 'bluetopo', 'nbs', 'ocean', 'elevation'],
            'region': 'USA',
            'resolution': 'Variable',
            'license': 'Public Domain',
            'urls': {'home': 'https://nauticalcharts.noaa.gov/data/bluetopo.html'}
        },
        
        # Nautical Charts (NOAA)
        'charts': {
            'mod': 'fetchez.modules.charts', 
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

        # World Settlement Footprint
        'wsf': {
            'mod': 'fetchez.modules.wsf', 
            'cls': 'WSF', 
            'category': 'Land Cover',
            'desc': 'World Settlement Footprint 2019 (10m)',
            'agency': 'DLR',
            'tags': ['urban', 'settlement', 'population', 'dlr', 'land-cover'],
            'region': 'Global',
            'resolution': '10m',
            'license': 'CC-BY 4.0',
            'urls': {'home': 'https://geoservice.dlr.de/web/maps/wsf2019'}
        },

        ## Crowd-Sourced Bathymetry
        'csb': {
            'mod': 'fetchez.modules.csb', 
            'cls': 'CSB', 
            'category': 'Bathymetry',
            'desc': 'NOAA Crowd Sourced Bathymetry (CSB)',
            'agency': 'NOAA NCEI',
            'tags': ['bathymetry', 'crowd-sourced', 'citizen-science', 'csv', 'depth', 'noaa'],
            'region': 'Global',
            'resolution': 'Varies',
            'license': 'CC0 / Public Domain',
            'urls': {'home': 'https://www.ngdc.noaa.gov/iho/'}
        },

        # NOAA Buoys
        'buoys': {
            'mod': 'fetchez.modules.buoys', 
            'cls': 'Buoys', 
            'category': 'Oceanography',
            'desc': 'NOAA NDBC Buoy Data (Realtime & Historical)',
            'agency': 'NOAA NDBC',
            'tags': ['buoy', 'ocean', 'waves', 'wind', 'meteorology', 'noaa'],
            'region': 'Global (NOAA network)',
            'resolution': 'Point Data',
            'license': 'Public Domain',
            'urls': {'home': 'https://www.ndbc.noaa.gov/'}
        },

        # CHS NONNA from Canada
        'chs': {
            'mod': 'fetchez.modules.chs', 
            'cls': 'CHS', 
            'category': 'Bathymetry',
            'desc': 'Canadian Hydrographic Service NONNA (10m & 100m)',
            'agency': 'CHS',
            'tags': ['bathymetry', 'canada', 'chs', 'nonna', 'wcs', 'topography'],
            'region': 'Canada',
            'resolution': '10m or 100m',
            'license': 'Open Government Licence - Canada',
            'urls': {'home': 'https://open.canada.ca/data/en/dataset/d3881c4c-650d-4070-bf9b-1e00aabf0a1d'}
        },
        
        # The following modules don't need a `region`,
        # they populate `FetchModule.results` in some other way.
        
        # Cpt-City
        'cpt_city': {
            'mod': 'fetchez.modules.cptcity', 
            'cls': 'CPTCity', 
            'category': 'Visualization',
            'desc': 'Color Palette Tables (CPT) from CPT City',
            'agency': 'SeaView Sensing / CPT City',
            'tags': ['visualization', 'color', 'palette', 'cpt', 'cartography'],
            'region': 'Global',
            'resolution': 'N/A',
            'license': 'Varies (Mostly Public/Open)',
            'urls': {'home': 'http://soliton.vm.bytemark.co.uk/pub/cpt-city/'}
        },
        
        # Nominatum
        'nominatim': {
            'mod': 'fetchez.modules.nominatim', 
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
    def load_module(cls, mod_key):
        """Import and return the (module or user-plugin) class using `importlib`."""    
            
        meta = cls._modules[mod_key]
        
        # User Plugin
        if '_class_obj' in meta:
            return meta['_class_obj']
            
        # Standard Module
        if mod_key not in cls._modules:
            return None
        
        info = cls.get_info(mod_key)
        if not info:
            return None

        try:
            module = importlib.import_module(info['mod'])
            mod_cls = getattr(module, info['cls'])
            return mod_cls
        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to load {mod_key}: {e}")
            return None
        
    @classmethod
    def load_user_plugins(cls):
        """Scan ~/.fetchez/plugins/ for external modules and register them."""

        import os, sys
        import inspect
        import importlib.util
        from . import core
        
        home_dir = os.path.expanduser("~")
        plugin_dir = os.path.join(home_dir, ".fetchez", "plugins")
        
        if not os.path.exists(plugin_dir):
            return

        # Add the plugin_dir to the system path for imports
        sys.path.insert(0, plugin_dir)
        
        for filename in os.listdir(plugin_dir):
            if filename.endswith(".py") and not filename.startswith("_"):
                filepath = os.path.join(plugin_dir, filename)
                module_name = f"user_plugin_{filename[:-3]}"
                
                try:
                    spec = importlib.util.spec_from_file_location(module_name, filepath)
                    if spec and spec.loader:
                        user_mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(user_mod)
                        
                        for name, obj in inspect.getmembers(user_mod):
                            if inspect.isclass(obj) and issubclass(obj, core.FetchModule):
                                if obj is core.FetchModule: continue
                                
                                # Check for @cli_opts metadata (optional but recommended)
                                # or defaults
                                mod_key = getattr(obj, 'name', name.lower())
                                logger.info(f"Loaded user plugin: {mod_key}")
                                
                                cls._modules[mod_key] = {
                                    'mod': f'user_plugin_{filename[:-3]}',
                                    'cls': name,
                                    'category': 'User Plugin',
                                    'desc': getattr(obj, '__doc__', 'User defined module').strip().split('\n')[0],
                                    'agency': 'External',
                                    '_class_obj': obj 
                                }
                                
                except Exception as e:
                    logger.warning(f"Failed to load plugin {filename}: {e}")

        # Remove the plugin_dir from the system path
        sys.path.pop(0)
        
        
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


FetchezRegistry.load_user_plugins()
