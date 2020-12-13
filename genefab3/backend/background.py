from threading import Thread
from genefab3.config import CACHER_THREAD_CHECK_INTERVAL
from genefab3.config import CACHER_THREAD_RECHECK_DELAY
from logging import getLogger, DEBUG
from genefab3.backend.mongo.writers.metadata import ensure_info_index
from genefab3.backend.mongo.writers.metadata import recache_metadata
from genefab3.backend.mongo.writers.metadata import update_metadata_value_lookup
from genefab3.backend.sql.writers.cache import drop_response_lru_cache
from time import sleep


class CacherThread(Thread):
    """Lives in background and keeps local metadata cache, metadata index, and response cache up to date"""
 
    def __init__(self, mongo_db, response_cache, check_interval=CACHER_THREAD_CHECK_INTERVAL, recheck_delay=CACHER_THREAD_RECHECK_DELAY):
        """Prepare background thread that iteratively watches for changes to datasets"""
        self.mongo_db, self.response_cache = mongo_db, response_cache
        self.check_interval, self.recheck_delay = check_interval, recheck_delay
        self.logger = getLogger("genefab3")
        self.logger.setLevel(DEBUG)
        super().__init__()
 
    def run(self):
        """Continuously run MongoDB and SQLite3 cachers"""
        while True:
            ensure_info_index(
                mongo_db=self.mongo_db, logger=self.logger,
            )
            accessions, success = recache_metadata(
                mongo_db=self.mongo_db, logger=self.logger,
            )
            if success:
                if accessions.updated | accessions.removed | accessions.failed:
                # TODO: drop only the cached responses involving these datasets
                    drop_response_lru_cache(
                        response_cache=self.response_cache,
                        logger=self.logger,
                    )
                delay = self.check_interval
            else:
                delay = self.recheck_delay
            update_metadata_value_lookup(self.mongo_db, self.logger)
            # TODO: shrink response cache to predefined max size
            self.logger.info(f"CacherThread: Sleeping for {delay} seconds")
            sleep(delay)