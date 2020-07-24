from urllib.request import urlopen
from genefab3.config import COLD_API_ROOT, TIMESTAMP_FMT
from json import loads
from re import search, sub
from genefab3.exceptions import GeneLabException, GeneLabJSONException
from datetime import datetime
from numpy import zeros
from functools import lru_cache


def download_cold_json(identifier, kind="other"):
    """Request and pre-parse cold storage JSONs for datasets, file listings, file dates"""
    if kind == "glds":
        url = "{}/data/study/data/{}/".format(COLD_API_ROOT, identifier)
        with urlopen(url) as response:
            return loads(response.read().decode())
    elif kind == "fileurls":
        accession_number_match = search(r'\d+$', identifier)
        if accession_number_match:
            accession_number = accession_number_match.group()
        else:
            raise GeneLabException("Malformed accession number")
        url = "{}/data/glds/files/{}".format(COLD_API_ROOT, accession_number)
        with urlopen(url) as response:
            raw_json = loads(response.read().decode())
            try:
                return raw_json["studies"][identifier]["study_files"]
            except KeyError:
                raise GeneLabJSONException("Malformed 'files' JSON")
    elif kind == "filedates":
        url = "{}/data/study/filelistings/{}".format(COLD_API_ROOT, identifier)
        with urlopen(url) as response:
            return loads(response.read().decode())
    elif kind == "other":
        url = identifier
        with urlopen(url) as response:
            return loads(response.read().decode())
    else:
        raise GeneLabException("Unknown JSON request: kind='{}'".format(kind))


def extract_file_timestamp(fd, key="date_modified", fallback_key="date_created", fallback_value=-1, fmt=TIMESTAMP_FMT):
    """Convert date like 'Fri Oct 11 22:02:48 EDT 2019' to timestamp"""
    strdate = fd.get(key)
    if strdate is None:
        strdate = fd.get(fallback_key)
    if strdate is None:
        return fallback_value
    else:
        try:
            dt = datetime.strptime(strdate, fmt)
        except ValueError:
            return fallback_value
        else:
            return int(dt.timestamp())


@lru_cache(maxsize=None)
def force_default_name_delimiter(string):
    """Replace variable delimiters (._-) with '-' (default)"""
    return sub(r'[._-]', "-", string)


@lru_cache(maxsize=None)
def levenshtein_distance(v, w):
    """Calculate levenshtein distance between two sequences"""
    m, n = len(v), len(w)
    dp = zeros((m+1, n+1), dtype=int)
    for i in range(m+1):
        for j in range(n+1):
            if i == 0:
                dp[i, j] = j
            elif j == 0:
                dp[i, j] = i
            elif v[i-1] == w[j-1]:
                dp[i, j] = dp[i-1, j-1]
            else:
                dp[i, j] = 1 + min(dp[i, j-1], dp[i-1, j], dp[i-1, j-1])
    return dp[m, n]
