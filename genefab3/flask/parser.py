from re import search, sub, escape
from argparse import Namespace
from genefab3.config import ANNOTATION_CATEGORIES
from genefab3.utils import UniversalSet
from collections import OrderedDict
from werkzeug.datastructures import MultiDict


def any_pair_to_query(key, value):
    """Interpret single key-value pair for dataset / assay constraint"""
    if value.count(".") == 0:
        return {".accession": value}, None
    else:
        accession, assay_name = value.split(".", 1)
        return {".accession": accession, ".assay": assay_name}, None


def pair_to_query(isa_category, fields, value, constrain_to=UniversalSet(), dot_postfix=False):
    """Interpret single key-value pair if it gives rise to database query"""
    if fields[0] in constrain_to:
        if (len(fields) == 2) and (dot_postfix == "auto"):
            lookup_key = ".".join([isa_category] + fields) + "."
        else:
            lookup_key = ".".join([isa_category] + fields)
        if value: # metadata field must equal value or one of values
            yield {lookup_key: {"$in": value.split("|")}}, {lookup_key}
        else: # metadata field or one of metadata fields must exist
            block_match = search(r'\.[^\.]+\.$', lookup_key)
            if (not block_match) or (block_match.group().count("|") == 0):
                # single field must exist (no OR condition):
                yield {lookup_key: {"$exists": True}}, {lookup_key}
            else: # either of the fields must exist (OR condition)
                head = lookup_key[:block_match.start()]
                targets = block_match.group().strip(".").split("|")
                lookup_keys = {f"{head}.{target}." for target in targets}
                query = {"$or": [
                    {key: {"$exists": True}} for key in lookup_keys
                ]}
                yield query, lookup_keys


def request_pairs_to_queries(rargs, key):
    """Interpret key-value pairs under same key if they give rise to database queries"""
    if key == "any":
        lookup_keys = None
        query = {"$or": [
            any_pair_to_query(key, value)[0]
            for value in rargs.getlist(key)
            if "$" not in value
        ]}
        yield query, lookup_keys
    elif "$" not in key:
        isa_category, *fields = key.split(".")
        if fields:
            for value in rargs.getlist(key):
                if "$" not in value:
                    if isa_category == "investigation":
                        yield from pair_to_query(
                            isa_category, fields, value,
                            constrain_to=UniversalSet(), dot_postfix=False,
                        )
                    elif isa_category in {"study", "assay"}:
                        yield from pair_to_query(
                            isa_category, fields, value,
                            constrain_to=ANNOTATION_CATEGORIES,
                            dot_postfix="auto",
                        )


def INPLACE_update_context_queries(context, rargs):
    """Interpret all key-value pairs that give rise to database queries"""
    shown = set()
    for key in rargs:
        for query, lookup_keys in request_pairs_to_queries(rargs, key):
            context.query["$and"].append(query)
            if lookup_keys:
                shown.update(lookup_keys)
            if key in context.kwargs:
                context.kwargs.pop(key)
    return shown


def INPLACE_update_context_projection(context, shown):
    """Infer query projection using values in `shown`"""
    ordered_shown = OrderedDict((e, True) for e in sorted(shown))
    for target, usable in ordered_shown.items():
        if usable:
            if target[-1] == ".":
                context.projection[target + "."] = True
            else:
                context.projection[target] = True
            for potential_child in ordered_shown:
                if potential_child.startswith(target):
                    ordered_shown[potential_child] = False


def parse_request(request):
    """Parse request components"""
    url_root = escape(request.url_root.strip("/"))
    base_url = request.base_url.strip("/")
    context = Namespace(
        view="/"+sub(url_root, "", base_url).strip("/")+"/",
        complete_args=request.args,
        query={"$and": []}, projection={},
        kwargs=MultiDict(request.args),
    )
    shown = INPLACE_update_context_queries(context, request.args)
    INPLACE_update_context_projection(context, shown)
    return context
