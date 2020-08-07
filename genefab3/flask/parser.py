from genefab3.exceptions import GeneLabException
from re import sub, escape
from argparse import Namespace
from genefab3.config import ASSAY_METADATALIKES


def assay_selection_to_query(selection):
    """Convert 'select' dictionary into MongoDB query"""
    if selection:
        query = {"$or": []}
        for accession, assay_name in selection.items():
            if assay_name:
                query["$or"].append({
                    "accession": accession, "assay name": assay_name,
                })
            else:
                query["$or"].append({"accession": accession})
        return query
    else:
        return {}


def parse_assay_selection(rargs_select_list):
    """Parse 'select' request argument"""
    if len(rargs_select_list) == 0:
        return None
    elif len(rargs_select_list) == 1:
        context_select = {}
        for query in rargs_select_list[0].split("|"):
            query_components = query.split(":", 1)
            if len(query_components) == 1:
                context_select[query] = None
            else:
                context_select[query_components[0]] = query_components[1]
        return context_select
    else:
        raise GeneLabException("'select' can be used no more than once")


def parse_meta_queries(key, expressions):
    """Process queries like e.g. 'factors=age' and 'factors:age=1|2'"""
    query_cc = key.split(":")
    if (len(query_cc) == 2) and (query_cc[0] in ASSAY_METADATALIKES):
        meta, queried_field = query_cc # e.g. "factors" and "age"
    else:
        meta, queried_field = key, None # e.g. "factors"
    meta_queries = []
    if meta in ASSAY_METADATALIKES:
        for expression in expressions:
            if queried_field: # e.g. {"age": {"$in": [1, 2]}}
                query = {queried_field: {"$in": expression.split("|")}}
                expression = queried_field
            else: # lookup just by meta name:
                query = {}
            meta_queries.append((expression, query))
        return meta, meta_queries
    else:
        return None, None


def parse_request(request):
    """Parse request components"""
    url_root = escape(request.url_root.strip("/"))
    base_url = request.base_url.strip("/")
    context = Namespace(
        view="/"+sub(url_root, "", base_url).strip("/")+"/",
        select=parse_assay_selection(request.args.getlist("select")),
        args=request.args,
        queries=Namespace(),
    )
    context.queries.select = assay_selection_to_query(context.select)
    for key in request.args:
        meta, meta_queries = parse_meta_queries(
            key, set(request.args.getlist(key)),
        )
        if meta:
            if getattr(context.queries, meta, None):
                getattr(context.queries, meta).extend(meta_queries)
            else:
                setattr(context.queries, meta, meta_queries)
    for meta in ASSAY_METADATALIKES:
        if getattr(context.queries, meta, None):
            setattr(
                context.queries, meta,
                sorted(getattr(context.queries, meta), reverse=True),
            )
    return context