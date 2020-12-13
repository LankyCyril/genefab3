from genefab3.config import COLLECTION_NAMES
from collections import defaultdict
from json import dumps
from os import path
from genefab3.common.utils import walk_up
from natsort import natsorted
from genefab3.common.utils import map_replace
from genefab3.frontend.utils import is_debug


def get_metadata_equals_json(mongo_db, cname=COLLECTION_NAMES.METADATA_VALUE_LOOKUP):
    """Generate JSON for documentation section 'meta-equals'"""
    equals_json = defaultdict(dict)
    for entry in getattr(mongo_db, cname).find():
        equals_json[entry["isa_category"]][entry["subkey"]] = {
            key: {value: True for value in values}
            for key, values in entry["content"].items()
        }
    return dict(equals_json)


def get_metadata_existence_json(equals_json):
    """Generate JSON for documentation section 'meta-existence'"""
    existence_json = defaultdict(dict)
    for isa_category in equals_json:
        for subkey in equals_json[isa_category]:
            existence_json[isa_category][subkey] = {
                key: True for key in equals_json[isa_category][subkey]
            }
    return dict(existence_json)


def get_metadata_wildcards(existence_json):
    """Generate JSON for documentation section 'meta-wildcard'"""
    wildcards = defaultdict(dict)
    for isa_category in existence_json:
        for subkey in existence_json[isa_category]:
            wildcards[isa_category][subkey] = True
    return dict(wildcards)


def get_metadata_assays(mongo_db, cname=COLLECTION_NAMES.METADATA):
    """Generate JSON for documentation section 'meta-assay'"""
    metadata_assays = defaultdict(set)
    for entry in getattr(mongo_db, cname).distinct("info"):
        metadata_assays[entry["accession"]].add(entry["assay"])
    return {
        k: {**{v: True for v in natsorted(metadata_assays[k])}, "": True}
        for k in natsorted(metadata_assays)
    }


def interactive_doc(mongo_db, html_path=None, document="docs.html", url_root="/"):
    """Serve an interactive documentation page""" # TODO in prod: make HTML template static / preload on app start
    if html_path is None:
        html_path = path.join(
            walk_up(path.abspath(__file__), 4), "html", document,
        )
    try:
        with open(html_path, mode="rt") as handle:
            template = handle.read()
        documentation_exists = True
    except (FileNotFoundError, OSError, IOError):
        template = "Hello, Space! (No documentation at %URL_ROOT%)"
        documentation_exists = False
    if documentation_exists:
        equals_json = get_metadata_equals_json(mongo_db)
        existence_json = get_metadata_existence_json(equals_json)
        wildcards = get_metadata_wildcards(existence_json)
        metadata_assays = get_metadata_assays(mongo_db)
        return map_replace(
            template, {
                "%URL_ROOT%": url_root,
                "/* METADATA_WILDCARDS */": dumps(wildcards),
                "/* METADATA_EXISTENCE */": dumps(existence_json),
                "/* METADATA_EQUALS */": dumps(equals_json),
                "/* METADATA_ASSAYS */": dumps(metadata_assays),
                "<!--DEBUG ": "" if is_debug() else "<!--",
                " DEBUG-->": "" if is_debug() else "-->",
            },
        )
    else:
        return map_replace(template, {"%URL_ROOT%": url_root})