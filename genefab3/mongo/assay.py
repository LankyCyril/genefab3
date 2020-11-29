from genefab3.exceptions import GeneLabDatabaseException, GeneLabParserException
from re import split, escape
from genefab3.utils import UniversalSet


class CachedAssay():
    """Exposes individual assay information and metadata"""
 
    def __init__(self, dataset, assay_name):
        self.dataset = dataset
        self.name = assay_name
        self.db = dataset.db
 
    def _iterate_filenames_from_projection(self, projection):
        """Match filenames from end leaves of query in metadata"""
        find_args = [
            {".accession": self.dataset.accession, ".assay": self.name},
            {"_id": False, **projection},
        ]
        for entry in self.db.metadata.find(*find_args):
            while isinstance(entry, dict):
                if len(entry) == 1:
                    entry = next(iter(entry.values()))
                elif len(entry) > 1:
                    raise GeneLabDatabaseException(
                        "Single-field lookup encountered multiple children",
                    )
            if isinstance(entry, str):
                yield from split(r'\s*,\s*', entry)
 
    def get_file_descriptors(self, name=None, regex=None, glob=None, projection=None):
        """Given mask and/or target field, find filenames, urls, and datestamps"""
        if projection:
            metadata_candidates = set(
                self._iterate_filenames_from_projection(projection),
            )
        else:
            metadata_candidates = UniversalSet()
        if name or regex or glob:
            dataset_candidates = set(
                self.dataset.get_file_descriptors(name, regex, glob),
            )
        else:
            dataset_candidates = UniversalSet()
        candidate_filenames = metadata_candidates & dataset_candidates
        if isinstance(candidate_filenames, UniversalSet):
            raise GeneLabParserException("No search criteria specified")
        elif candidate_filenames:
            return self.dataset.get_file_descriptors(
                regex=r'^({})$'.format(
                    r'|'.join(map(escape, candidate_filenames)),
                ),
            )
        else:
            return {}