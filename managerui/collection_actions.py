from pathlib import Path
from typing import Dict, List, Optional

from platformdirs import user_config_dir

from common.table_catalog import get_cached_table_rows
from common.table_catalog import sync_catalog_collections
from common.vpxcollections import VPXCollections


CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
COLLECTIONS_PATH = CONFIG_DIR / "collections.ini"


def get_collections_manager() -> VPXCollections:
    """Get a fresh VPXCollections instance."""
    return VPXCollections(str(COLLECTIONS_PATH))


def get_vpsid_collections() -> List[str]:
    """Get list of all vpsid-type collection names."""
    result = []
    try:
        collections = get_collections_manager()
        for collection_name in collections.get_collections_name():
            if not collections.is_filter_based(collection_name):
                result.append(collection_name)
    except Exception:
        pass
    return result


def add_table_to_collection(vpsid: str, collection_name: str) -> bool:
    """Add a table (by VPS ID) to a collection and refresh cached memberships."""
    try:
        collections = get_collections_manager()
        collections.add_vpsid(collection_name, vpsid)
        collections.save()

        tables_cache: Optional[List[Dict]] = get_cached_table_rows()
        if tables_cache is not None:
            for row in tables_cache:
                if row.get('id') == vpsid:
                    if 'collections' not in row:
                        row['collections'] = []
                    if collection_name not in row['collections']:
                        row['collections'].append(collection_name)
                    break
            else:
                sync_catalog_collections(str(COLLECTIONS_PATH))

        return True
    except Exception:
        return False