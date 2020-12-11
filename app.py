#!/usr/bin/env python
from flask import Flask, request
from genefab3.config import COMPRESSIBLE_MIMETYPES
from flask_compress import Compress
from pymongo import MongoClient
from genefab3.config import MONGO_CLIENT_PARAMETERS, MONGO_DB_NAME
from genefab3.config import RESPONSE_CACHE, SQLITE_DB
from pymongo.errors import ServerSelectionTimeoutError
from genefab3.common.exceptions import GeneLabDatabaseException
from genefab3.frontend.utils import is_flask_reloaded, is_debug
from genefab3.backend.background import CacherThread
from genefab3.common.exceptions import traceback_printer, exception_catcher
from genefab3.common.exceptions import DBLogger
from functools import partial
from logging import getLogger
from genefab3.frontend.renderer import render
from collections import namedtuple


# Backend initialization:

app = Flask("genefab3")
COMPRESS_MIMETYPES = COMPRESSIBLE_MIMETYPES
Compress(app)

mongo_client = MongoClient(**MONGO_CLIENT_PARAMETERS)
try:
    mongo_client.server_info()
except ServerSelectionTimeoutError:
    raise GeneLabDatabaseException("Could not connect (sensitive info hidden)")
else:
    mongo_db = getattr(mongo_client, MONGO_DB_NAME)

if not is_flask_reloaded():
    CacherThread(mongo_db=mongo_db, response_cache=RESPONSE_CACHE).start()

if is_debug():
    traceback_printer = app.errorhandler(Exception)(
        partial(traceback_printer, mongo_db=mongo_db),
    )
else:
    exception_catcher = app.errorhandler(Exception)(
        partial(exception_catcher, mongo_db=mongo_db),
    )
getLogger("genefab3").addHandler(DBLogger(mongo_db))


# App routes:

@app.route("/", methods=["GET"])
def root(**kwargs):
    from genefab3.frontend.renderers.docs import interactive_doc
    return interactive_doc(mongo_db, url_root=request.url_root.rstrip("/"))

@app.route("/assays/", methods=["GET"])
def assays(**kwargs):
    from genefab3.frontend.getters.metadata import get_assays as getter
    return render(mongo_db, getter, kwargs, request)

@app.route("/samples/", methods=["GET"])
def samples(**kwargs):
    from genefab3.frontend.getters.metadata import get_samples as getter
    return render(mongo_db, getter, kwargs, request)

@app.route("/files/", methods=["GET"])
def files(**kwargs):
    from genefab3.frontend.getters.metadata import get_files as getter
    return render(mongo_db, getter, kwargs, request)

@app.route("/file/", methods=["GET"])
def file(**kwargs):
    from genefab3.frontend.getters.file import get_file as getter
    return render(mongo_db, getter, kwargs, request)

@app.route("/data/", methods=["GET"])
def data(**kwargs):
    from genefab3.frontend.getters.data import get_data as getter
    dbs = namedtuple("dbs", "mongo_db, sqlite_db")(mongo_db, SQLITE_DB)
    return render(dbs, getter, kwargs, request)

@app.route("/status/", methods=["GET"])
def status(**kwargs):
    from genefab3.frontend.getters.status import get_status as getter
    return render(mongo_db, getter, kwargs, request)

@app.route("/favicon.<imgtype>")
def favicon(**kwargs):
    return ""
