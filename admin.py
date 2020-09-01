#!/usr/bin/env python
from logging import getLogger, INFO
from sys import argv
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId
from datetime import datetime
from genefab3.config import MONGO_DB_NAME
from genefab3.mongo.meta import CachedDataset
from genefab3.coldstorage.dataset import ColdStorageDataset
from json import dumps


TIME_FMT = "%Y-%m-%d %H:%M:%S"
TYPE_OPTS = {True: "Exception", False: "LogMessage", None: "Unknown"}

logger = getLogger("genefab3")
logger.setLevel(INFO)


def format_timestamp(timestamp):
    return datetime.utcfromtimestamp(timestamp).strftime(TIME_FMT)


def confirm(prompt):
    mask = "Are you sure? Type '{}' without quotes to confirm:\n"
    if input(mask.format(prompt)) != prompt:
        raise ValueError


def drop(db, what):
    confirm("Yes, drop " + what)
    if what == "ALLMETA":
        confirm("Yes, I am really sure I want to drop ALLMETA")
        collection_names = {
            "dataset_timestamps", "json_cache", "annotations", "metadata",
        }
        for cn in collection_names:
            getattr(db, cn).delete_many({})
    elif what == "log":
        getattr(db, "log").delete_many({})
    else:
        CachedDataset.drop_cache(db=db, accession=what)


def recache(db, what):
    if what.startswith("ALL"):
        raise NotImplementedError
    else:
        confirm("Yes, recache " + what)
        CachedDataset.drop_cache(db=db, accession=what)
        CachedDataset(db, what, logger=logger)


def showlog_brief_lines(db, query, max_i):
    sort = [("timestamp", DESCENDING), ("_id", DESCENDING)]
    for i, entry in enumerate(db.log.find(query, sort=sort)):
        fields = [
            entry["_id"],
            format_timestamp(entry["timestamp"]),
            TYPE_OPTS[entry.get("is_exception")][0],
            "type={}".format(entry.get("type")),
            entry.get("value", "(no message)"),
            "from={}".format(entry.get("remote_addr")),
            "has_stack_info" if entry.get("stack") else "no_stack_info",
        ]
        print(*fields[:3], sep="; ", end=" ")
        print(*fields[3:], sep="\t")
        if i > max_i:
            break


def showlog_single_entry(db, _id):
    entry = db.log.find_one({"_id": _id})
    fields = [
        "_id  = {}".format(entry["_id"]),
        "time = {}".format(format_timestamp(entry["timestamp"])),
        "what = {}".format(TYPE_OPTS[entry.get("is_exception")]),
        "type = {}".format(entry.get("type")),
        "from = {}".format(entry.get("remote_addr")),
        "path = {}".format(entry.get("full_path")),
        "mess = {}".format(entry.get("value")),
        "---",
        entry.get("stack", ""),
    ]
    print(*fields, sep="\n")


def showlog(db, how):
    if how.isdigit() or ((not how.startswith("_id")) and ("=" in how)):
        if how.isdigit():
            query = {}
            max_i = int(how) - 1
        else:
            k, v = how.split("=", 1)
            if v == "True":
                v = True
            elif v == "False":
                v = False
            query = {k: v}
            max_i = float("inf")
        showlog_brief_lines(db, query, max_i)
    elif how.startswith("_id="):
        showlog_single_entry(db, _id=ObjectId(how.lstrip("_id=")))
    else:
        raise NotImplementedError


def test_isa(db, accession, assay_name, attribute):
    if db.dataset_timestamps.find_one({"accession": accession}):
        glds = CachedDataset(db, accession, logger=logger)
    else:
        glds = ColdStorageDataset(accession)
    assay = glds.assays[assay_name]
    data = getattr(assay, attribute)
    print(dumps(data, indent=4, sort_keys=True))


if len(argv) > 1:
    mongo = MongoClient()
    db = getattr(mongo, MONGO_DB_NAME)
    if argv[1] == "drop":
        drop(db, argv[2])
    elif argv[1] == "recache":
        recache(db, argv[2])
    elif argv[1] == "log":
        if len(argv) > 2:
            showlog(db, argv[2])
        else:
            showlog_brief_lines(db, {}, float("inf"))
    elif argv[1] == "test-isa":
        test_isa(db, argv[2], argv[3], argv[4])
    else:
        raise NotImplementedError
else:
    raise NotImplementedError
