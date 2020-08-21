from argparse import Namespace
from re import search
from urllib.parse import quote
from genefab3.coldstorage.json import download_cold_json as dl_json
from genefab3.exceptions import GeneLabJSONException, GeneLabDatabaseException
from memoized_property import memoized_property
from genefab3.config import GENELAB_ROOT, ISA_ZIP_REGEX
from genefab3.utils import extract_file_timestamp
from genefab3.coldstorage.isa import IsaZip
from genefab3.coldstorage.assay import ColdStorageAssay


class ColdStorageDataset():
    """Contains GLDS metadata associated with an accession number"""
    json = Namespace()
    isa = None
 
    def __init__(self, accession, json=Namespace(), init_assays=True):
        """Request ISA and store fields"""
        jga = lambda name: getattr(json, name, None)
        # validate JSON and initialize identifiers"
        self.json.glds = jga("glds") or dl_json(accession, "glds")
        if not self.json.glds:
            raise GeneLabJSONException("{}: no dataset found".format(accession))
        try:
            assert len(self.json.glds) == 1
            self._id = self.json.glds[0]["_id"]
        except (AssertionError, IndexError, KeyError):
            error = "{}: malformed GLDS JSON".format(accession)
            raise GeneLabJSONException(error)
        else:
            j = self.json.glds[0]
            if accession in {j.get("accession"), j.get("legacy_accession")}:
                self.accession = accession
            else:
                error = "{}: initializing with wrong JSON".format(accession)
                raise GeneLabJSONException(error)
        # populate file information:
        self.json.fileurls = jga("fileurls") or dl_json(accession, "fileurls")
        self.json.filedates = jga("fileurls") or dl_json(self._id, "filedates")
        # initialize assays via ISA ZIP:
        if init_assays:
            self.init_assays()
 
    @memoized_property
    def fileurls(self):
        """Parse file URLs JSON reported by cold storage"""
        try:
            return {
                fd["file_name"]: GENELAB_ROOT + quote(fd["remote_url"])
                for fd in self.json.fileurls
            }
        except KeyError:
            error = "{}: malformed 'files' JSON".format(self.accession)
            raise GeneLabJSONException(error)
 
    @memoized_property
    def filedates(self):
        """Parse file dates JSON reported by cold storage"""
        try:
            return {
                fd["file_name"]: extract_file_timestamp(fd)
                for fd in self.json.filedates
            }
        except KeyError:
            error = "{}: malformed 'filelistings' JSON".format(self.accession)
            raise GeneLabJSONException(error)
 
    def resolve_filename(self, mask):
        """Given mask, find filenames, urls, and datestamps"""
        return {
            filename: Namespace(
                filename=filename, url=self.fileurls.get(filename, None),
                timestamp=int(timestamp) if str(timestamp).isdigit() else -1,
            )
            for filename, timestamp in self.filedates.items()
            if search(mask, filename)
        }

    def init_assays(self):
        """Initialize assays via ISA ZIP"""
        isa_zip_descriptors = self.resolve_filename(ISA_ZIP_REGEX)
        if len(isa_zip_descriptors) == 0:
            error = "{}: ISA ZIP not found".format(self.accession)
            raise GeneLabDatabaseException(error)
        elif len(isa_zip_descriptors) == 1:
            self.isa = IsaZip(next(iter(isa_zip_descriptors.values())).url)
        else:
            print(isa_zip_descriptors)
            error = "{}: multiple ambiguous ISA ZIPs".format(self.accession)
            raise GeneLabDatabaseException(error)
        #try:
        #    self.assays = {a: None for a in self.isa.assays} # placeholders
        #    self.assays = ColdStorageAssayDispatcher(self) # actual assays
        #except (KeyError, TypeError):
        #    raise GeneLabJSONException("Invalid JSON (field 'assays')")


class ColdStorageAssayDispatcher(dict):
    """Contains a dataset's assay objects, indexable by name or by attributes"""
 
    def __init__(self, dataset):
        """Populate dictionary of assay_name -> Assay()"""
        for assay_name in dataset.isa.assays:
            sample_key = infer_sample_key(assay_name, dataset.isa.samples)
            super().__setitem__(
                assay_name, ColdStorageAssay(dataset, assay_name, sample_key)
            )
 
    def __getitem__(self, assay_name):
        """Get assay by name or alias"""
        if (assay_name == "assay") and (len(self) == 1):
            return dict.__getitem__(self, next(iter(self)))
        else:
            return dict.__getitem__(self, assay_name)
