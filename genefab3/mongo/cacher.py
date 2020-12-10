from genefab3.config import COLD_SEARCH_MASK, MAX_JSON_AGE
from genefab3.config import COLLECTION_NAMES, MONGO_DB_LOCALE
from genefab3.mongo.json import get_fresh_json
from datetime import datetime
from pandas import Series
from copy import deepcopy
from genefab3.mongo.utils import run_mongo_transaction
from logging import getLogger, DEBUG
from threading import Thread
from pymongo import ASCENDING
from genefab3.config import CACHER_THREAD_CHECK_INTERVAL
from genefab3.config import CACHER_THREAD_RECHECK_DELAY
from genefab3.mongo.dataset import CachedDataset
from genefab3.config import UNITS_FORMAT
from time import sleep


INDEX_TEMPLATE = {
    "investigation": {
        "study": "true",
        "study assays": "true",
        "investigation": "true",
    },
    "study": {
        "characteristics": "true",
        "factor value": "true",
        "parameter value": "true",
    },
    "assay": {
        "characteristics": "true",
        "factor value": "true",
        "parameter value": "true",
    },
}

FINAL_INDEX_KEY_BLACKLIST = {"comment"}


def list_available_accessions(mongo_db):
    """List datasets in cold storage"""
    url_n = COLD_SEARCH_MASK.format(0)
    n_datasets = get_fresh_json(mongo_db, url_n)["hits"]["total"]
    url_all = COLD_SEARCH_MASK.format(n_datasets)
    raw_datasets_json = get_fresh_json(mongo_db, url_all)["hits"]["hits"]
    return {raw_json["_id"] for raw_json in raw_datasets_json}


def list_fresh_and_stale_accessions(mongo_db, max_age=MAX_JSON_AGE, cname=COLLECTION_NAMES.DATASET_TIMESTAMPS):
    """Find accessions in no need / need of update in database"""
    refresh_dates = Series({
        entry["accession"]: entry["last_refreshed"]
        for entry in getattr(mongo_db, cname).find()
    })
    current_timestamp = int(datetime.now().timestamp())
    indexer = ((current_timestamp - refresh_dates) <= max_age)
    return set(refresh_dates[indexer].index), set(refresh_dates[~indexer].index)


def INPLACE_update_metadata_index_keys(mongo_db, index, final_key_blacklist=FINAL_INDEX_KEY_BLACKLIST, cname=COLLECTION_NAMES.METADATA):
    """Populate JSON with all possible metadata keys, also for documentation section 'meta-existence'"""
    for isa_category in index:
        for subkey in index[isa_category]:
            raw_next_level_keyset = set.union(*(
                set(entry[isa_category][subkey].keys()) for entry in
                getattr(mongo_db, cname).find(
                    {isa_category+"."+subkey: {"$exists": True}},
                    {isa_category+"."+subkey: True},
                )
            ))
            index[isa_category][subkey] = {
                next_level_key: True for next_level_key in
                sorted(raw_next_level_keyset - final_key_blacklist)
            }


def INPLACE_update_metadata_index_values(mongo_db, index, cname=COLLECTION_NAMES.METADATA):
    """Generate JSON with all possible metadata values, also for documentation section 'meta-equals'"""
    metadata_collection = getattr(mongo_db, cname)
    for isa_category in index:
        for subkey in index[isa_category]:
            for next_level_key in index[isa_category][subkey]:
                values = sorted(map(str, metadata_collection.distinct(
                    f"{isa_category}.{subkey}.{next_level_key}.",
                )))
                if not values:
                    values = sorted(map(str, metadata_collection.distinct(
                        f"{isa_category}.{subkey}.{next_level_key}",
                    )))
                index[isa_category][subkey][next_level_key] = values


def ensure_info_index(mongo_db, category="info", keys=["accession", "assay", "sample name"], cname=COLLECTION_NAMES.METADATA):
    """Index `info.*` for sorting"""
    if category not in getattr(mongo_db, cname).index_information():
        getattr(mongo_db, cname).create_index(
            name=category,
            keys=[(f"{category}.{key}", ASCENDING) for key in keys],
            collation={"locale": MONGO_DB_LOCALE, "numericOrdering": True},
        )


def update_metadata_index(mongo_db, logger, template=INDEX_TEMPLATE, cname=COLLECTION_NAMES.METADATA_INDEX):
    """Collect existing keys and values for lookups"""
    logger.info("CacherThread: reindexing metadata")
    index = deepcopy(template)
    INPLACE_update_metadata_index_keys(mongo_db, index)
    INPLACE_update_metadata_index_values(mongo_db, index)
    for isa_category in index:
        for subkey in index[isa_category]:
            run_mongo_transaction(
                action="replace",
                collection=getattr(mongo_db, cname),
                query={"isa_category": isa_category, "subkey": subkey},
                data={"content": index[isa_category][subkey]},
            )


class CacherThread(Thread):
    """Lives in background and keeps local metadata cache and index up to date"""
 
    def __init__(self, mongo_db, check_interval=CACHER_THREAD_CHECK_INTERVAL, recheck_delay=CACHER_THREAD_RECHECK_DELAY):
        """Prepare background thread that iteratively watches for changes to datasets"""
        self.mongo_db, self.check_interval = mongo_db, check_interval
        self.recheck_delay = recheck_delay
        self.logger = getLogger("genefab3")
        self.logger.setLevel(DEBUG)
        super().__init__()
 
    def _log_info(self, message):
        """Simple wrapper for self.logger.info with parent name (CacherThread) prepended"""
        self.logger.info(f"CacherThread: {message}")

    def _log_freshness(self, glds):
        """Wrapper for self.logger.info with parent name (CacherThread), accession, change status"""
        if any(glds.changed.__dict__.values()):
            chg = "changed"
        else:
            chg = "up to date"
        self.logger.info(f"CacherThread: {chg}, accession={glds.accession}")
 
    def _log_error(self, e, **kwargs):
        """Wrapper for self.logger.error with parent name (CacherThread), arbitrary arguments"""
        message = f"CacherThread: {repr(e)}"
        for k, v in kwargs.items():
            message = message + f", {k}='{v}'"
        self.logger.error(message, stack_info=True)
 
    def run(self):
        """Detect changes to datasets based on cold storage JSON and re-cache modified ones"""
        while True:
            ensure_info_index(self.mongo_db)
            self._log_info("Checking cache")
            try:
                accessions = list_available_accessions(self.mongo_db)
                fresh, stale = list_fresh_and_stale_accessions(self.mongo_db)
            except Exception as e:
                self._log_error(e)
                delay = self.recheck_delay
            else:
                for accession in accessions - fresh:
                    try:
                        glds = CachedDataset(
                            self.mongo_db, accession, self.logger,
                            init_assays=True, units_format=UNITS_FORMAT,
                        )
                    except Exception as e:
                        self._log_error(e, accession=accession)
                    else:
                        self._log_freshness(glds)
                for accession in (fresh | stale) - accessions:
                    CachedDataset.drop_cache(
                        mongo_db=self.mongo_db, accession=accession,
                    )
                self._log_info(f"{len(fresh)} were fresh, {len(stale)} updated")
                delay = self.check_interval
            finally:
                update_metadata_index(self.mongo_db, self.logger)
                self._log_info(f"Sleeping for {delay} seconds")
                sleep(delay)
