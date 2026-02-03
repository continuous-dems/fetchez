import os
import io
import json
import logging
from tqdm import tqdm
import requests
from fetchez.hooks import FetchHook
from fetchez import utils

try:
    from shapely.geometry import box, mapping
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

logger = logging.getLogger(__name__)

class MultibeamIndex(FetchHook):
    """Pre-fetch hook to parse Multibeam .inf files and generate a GeoJSON coverage map."""
    
    name = "mb_index"
    desc = "Generate GeoJSON coverage from .inf files. Usage: --hook mb_index:out=surveys.geojson"
    stage = 'pre'

    def __init__(self, out='surveys.geojson', **kwargs):
        super().__init__(**kwargs)
        self.outfile = out
        

    def run(self, all_entries):
        """Input: List of (module, entry_dict) tuples."""
        
        logger.info("Scanning queue for multibeam metadata (.inf)...")
        
        survey_features = []
        
        inf_entries = [entry for _, entry in all_entries if entry.get('url', '').endswith('.inf')]

        if not inf_entries:
            logger.warning("No .inf files found. Is this the 'multibeam' module?")
            return all_entries

        logger.info(f"Found {len(inf_entries)} metadata files. Parsing...")

        with requests.Session() as session:
            with tqdm(total=len(inf_entries),desc=f'Parsing Multibeam inf files.>', position=0, leave=True) as pbar:
                for i, entry in enumerate(inf_entries):
                    pbar.update()
                    url = entry.get('url')

                    filename = os.path.basename(entry.get('dst_fn'))
                    survey_id = filename.split('.')[0]
                    #if self.group_by_survey and survey_id in seen_surveys:
                    #    continue

                    try:
                        resp = session.get(url, timeout=5)
                        if resp.status_code == 200:
                            meta = self._parse_inf(resp.text)                        
                            if meta:
                                props = {
                                    'name': meta.get('name'),
                                    'survey_id': survey_id,
                                    'metadata_url': url,
                                    'data_url': url.replace('.inf', '.gz'),
                                    'year': meta.get('date'),
                                    'ship': meta.get('ship'),
                                    'records': meta.get('records')
                                }

                                geom = self._create_geometry(meta)

                                feature = {
                                    "type": "Feature",
                                    "properties": props,
                                    "geometry": geom
                                }

                                survey_features.append(feature)

                    except Exception as e:
                        logger.debug(f"Failed to parse {survey_id}: {e}")

                    # if i % 10 == 0:
                    #     print(f"Indexed {len(survey_features)} surveys...", end='\r')

        if survey_features:
            geojson = {
                "type": "FeatureCollection",
                "name": "Multibeam Index",
                "features": survey_features
            }
            
            with open(self.outfile, 'w') as f:
                json.dump(geojson, f, indent=2)
                
            logger.info(f"\nSuccessfully wrote {len(survey_features)} surveys to {self.outfile}")
        else:
            logger.warning("\nNo valid survey metadata could be parsed.")

        return all_entries

    
    def _parse_inf(self, text):
        import math

        meta = {}
        bounds = {}
        cm_grid = []
        reading_cm = False
        
        for line in text.splitlines():
            line = line.strip()
            if not line: continue

            parts = line.split()
            
            if len(parts) > 3 and parts[0] == 'Swath' and parts[2] == 'File:':
                meta['name'] = parts[3]

            if parts[0] == 'Number' and parts[2] == 'Records:':
                meta['records'] = utils.int_or(parts[3])

            
            elif parts[0] == 'Time:':
                meta['date'] = parts[3]
                
            if parts[0] == 'Minimum' and len(parts) >= 6:
                try:
                    val1 = utils.float_or(parts[2])
                    val2 = utils.float_or(parts[5])
                    
                    if parts[1] == 'Longitude:':
                        bounds['xmin'] = val1
                        bounds['xmax'] = val2
                    elif parts[1] == 'Latitude:':
                        bounds['ymin'] = val1
                        bounds['ymax'] = val2
                except:
                    pass

            if parts[0] == 'CM' and parts[1] == 'dimensions:':
                reading_cm = True
                continue
            
            if reading_cm and parts[0] == 'CM:':
                row = [int(x) for x in parts[1:]]
                cm_grid.append(row)
                
                if len(cm_grid) >= 10:
                    reading_cm = False

        if len(bounds) == 4:
            if bounds['xmin'] > bounds['xmax']: bounds['xmin'], bounds['xmax'] = bounds['xmax'], bounds['xmin']
            if bounds['ymin'] > bounds['ymax']: bounds['ymin'], bounds['ymax'] = bounds['ymax'], bounds['ymin']

            meta['bounds'] = bounds
            
            if len(cm_grid) == 10 and len(cm_grid[0]) == 10:
                meta['cm_grid'] = cm_grid

            return meta

        return None    

    
    def _create_geometry(self, meta):
        """Convert bounds + CM grid into a tight polygon.
        If CM grid is missing or Shapely is unavailable, falls back to BBox.
        """
        
        bounds = meta['bounds']
        xmin, xmax = bounds['xmin'], bounds['xmax']
        ymin, ymax = bounds['ymin'], bounds['ymax']
        
        if 'cm_grid' in meta and HAS_SHAPELY:
            from shapely.geometry import box, mapping
            from shapely.ops import unary_union
            
            grid = meta['cm_grid']
            rows = len(grid)
            cols = len(grid[0])
            
            width = xmax - xmin
            height = ymax - ymin
            cell_w = width / cols
            cell_h = height / rows
            
            active_cells = []

            for r in range(rows):
                for c in range(cols):
                    if grid[r][c] == 1:
                        c_xmin = xmin + (c * cell_w)
                        c_xmax = c_xmin + cell_w
                        c_ymax = ymax - (r * cell_h)
                        c_ymin = c_ymax - cell_h
                        
                        active_cells.append(box(c_xmin, c_ymin, c_xmax, c_ymax))

            if active_cells:
                tight_poly = unary_union(active_cells)
                return mapping(tight_poly)

        if HAS_SHAPELY:
            from shapely.geometry import box, mapping
            return mapping(box(xmin, ymin, xmax, ymax))
        else:
            return {
                "type": "Polygon",
                "coordinates": [[
                    [xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]
                ]]
            }
