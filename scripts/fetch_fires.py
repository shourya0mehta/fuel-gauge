"""California wildfire ignition points from the NIFC WFIGS incident service (public ArcGIS REST).

    DATA=data python scripts/fetch_fires.py
Writes $DATA/fires/ca_wildfire_incidents.parquet (one row per incident: name, discovery date, size, cause, lat/lon)
"""
import json
import os
import time
import urllib.parse
import urllib.request

import pandas as pd

DATA = os.environ.get('DATA', 'data')
URL = 'https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations/FeatureServer/0/query'
FIELDS = ['UniqueFireIdentifier', 'IncidentName', 'FireDiscoveryDateTime', 'IncidentSize', 'DiscoveryAcres', 'FireCauseGeneral',
          'FireCause', 'POOLandownerKind', 'POOCounty', 'InitialLatitude', 'InitialLongitude']


def get(params):
    q = urllib.parse.urlencode(params)
    for a in range(4):
        try:
            return json.loads(urllib.request.urlopen(f'{URL}?{q}', timeout=120).read())
        except Exception:  # noqa: BLE001
            time.sleep(3 * (a + 1))
    raise RuntimeError('query failed')


def main():
    os.makedirs(os.path.join(DATA, 'fires'), exist_ok=True)
    rows, off = [], 0
    while True:
        d = get(dict(where="POOState='US-CA' AND IncidentTypeCategory='WF'", outFields=','.join(FIELDS), returnGeometry='true',
                     outSR=4326, resultOffset=off, resultRecordCount=2000, orderByFields='OBJECTID', f='json'))
        feats = d.get('features', [])
        for f in feats:
            a = f['attributes']; g = f.get('geometry') or {}
            a['lon'] = g.get('x', a.get('InitialLongitude')); a['lat'] = g.get('y', a.get('InitialLatitude'))
            rows.append(a)
        off += len(feats)
        print(off, flush=True)
        if not feats or not d.get('exceededTransferLimit'):
            break
    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df.FireDiscoveryDateTime, unit='ms', errors='coerce')
    df = df.dropna(subset=['lat', 'lon', 'date'])
    df.to_parquet(os.path.join(DATA, 'fires', 'ca_wildfire_incidents.parquet'))
    print(len(df), 'incidents', df.date.min(), df.date.max())


if __name__ == '__main__':
    main()
