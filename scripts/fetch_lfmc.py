"""Download Globe-LFMC 2.0 (Yebra et al. 2024) and keep the US samples: $DATA/globe/globe_usa.parquet."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from fuelgauge.sources import lfmc  # noqa: E402

DATA = os.environ.get('DATA', 'data')
df = lfmc.load(cache_dir=os.path.join(DATA, 'globe'), country='USA')
df.to_parquet(os.path.join(DATA, 'globe', 'globe_usa.parquet'))
print(len(df), 'US samples at', df['Site name'].nunique(), 'sites')
