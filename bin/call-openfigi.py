#!/usr/bin/env python3

import argparse, itertools, json, os, time, urllib.request
from _cusip_isin import make_isin_from_cusip
from _csv_formats import read_fundinfo_csv, TickerInfo, read_tickerinfo_csv, write_tickerinfo_csv
from _logging import _LOGGER_, configure_logger


OPENFIGI_ENDPOINT_URL = 'https://api.openfigi.com/v3/mapping'
'''Default URL of the OpenFIGI mapping endpoint.'''

OPENFIGI_CALLS_PER_MINUTE_WITHOUT_KEY = 25
'''Default OpenFIGI call rate limit when an API key is not used.'''

OPENFIGI_CALLS_PER_MINUTE_WITH_KEY = 250
'''Default OpenFIGI call rate limit when an API key is used.'''

OPENFIGI_JOBS_PER_CALL_WITHOUT_KEY = 10
'''Default OpenFIGI call size limit when an API key is not used.'''

OPENFIGI_JOBS_PER_CALL_WITH_KEY = 100
'''Default OpenFIGI call size limit when an API key is used.'''


def isins_from_sheet_for_funds(funds, cache, queried_isin_cusips):
    '''
    Generator function which, given a series of FundInfo objects,
    iterates over the unique ISINs we'll want to query from OpenFIGI.
    '''
    for fund in funds:
        if fund.isin:
            isin_cusip = fund.isin[2:11]
            if (isin_cusip not in cache or not cache[isin_cusip].ticker) and isin_cusip not in queried_isin_cusips:
                queried_isin_cusips.add(isin_cusip)
                yield fund.isin


def cusips_from_sheet_for_funds(funds, cache, queried_cusips):
    '''
    Generator function which, given a series of FundInfo objects,
    iterates over the unique CUSIPs we'll want to query from OpenFIGI.
    '''
    for fund in funds:
        if fund.cusip and (fund.cusip not in cache or not cache[fund.cusip].ticker) and fund.cusip not in queried_cusips:
            queried_cusips.add(fund.cusip)
            yield fund.cusip


def cusips_from_isins_for_funds(funds, cache, queried_cusips):
    '''
    Generator function which, given a series of FundInfo objects,
    iterates over the unique CUSIPs derived from ISINs we'll want to query from OpenFIGI.
    '''
    for fund in funds:
        if fund.isin:
            isin_cusip = fund.isin[2:11]
            if (isin_cusip not in cache or not cache[isin_cusip].ticker) and isin_cusip not in queried_cusips:
                queried_cusips.add(isin_cusip)
                yield isin_cusip


def isins_from_cusips_for_funds(funds, cache, queried_isin_cusips):
    '''
    Generator function which, given a series of FundInfo objects,
    iterates over the unique ISINs derived from CUSIPs we'll want to query from OpenFIGI.
    '''
    for fund in funds:
        if fund.cusip and (fund.cusip not in cache or not cache[fund.cusip].ticker) and fund.cusip not in queried_isin_cusips:
            queried_isin_cusips.add(fund.cusip)
            yield make_isin_from_cusip(fund.cusip)


def group_into_sublists(it, n):
    '''
    Return the items from the given iterable grouped into a series of
    non-overlapping sub-lists (tuples, actually) of at most n items.
    '''
    it = iter(it)
    result = []
    try:
        while True:
            for unused in range(n):
                result.append(next(it))
            yield tuple(result)
            result = []
    except StopIteration:
        pass
    if result:
        yield tuple(result)


def isin_to_openfigi_job(isin):
    '''
    Given an ISIN, return a JSON object which can be passed as part of
    a query to OpenFIGI to get any records for an ETF with the given ISIN.
    '''
    return {"idType":"ID_ISIN","idValue":isin,"securityType":"ETP"}


def cusip_to_openfigi_job(cusip):
    '''
    Given a CUSIP, return a JSON object which can be passed as part of
    a query to OpenFIGI to get any records for an ETF with the given CUSIP.
    '''
    return {"idType":"ID_CUSIP","idValue":cusip,"securityType":"ETP"}


def rate_limit(it, items_per_minute):
    '''
    Generator function which limits the speed at which we can iterate over
    an iterable, yielding at most items_per_minute items from that iterable
    per minute.
    '''
    seconds_per_item = (60.0/items_per_minute)
    last_time = None
    for item in it:
        if last_time:
            to_sleep = last_time + seconds_per_item - time.time()
            if to_sleep > 0:
                time.sleep(to_sleep)
        last_time = time.time()
        yield item


def progress_reporting_iterator(it, step, message_fmt):
    '''
    Generator function which iterates over an iterable, logging a progress
    message every "step" items.
    '''
    for index, item in enumerate(it):
        yield item
        count = index + 1
        if count % step == 0:
            _LOGGER_.info(message_fmt % count)


# from https://github.com/OpenFIGI/api-examples/blob/master/python/example-python3.py
def call_openfigi(jobs, openfigi_url, openfigi_api_key=None):
    '''
    Send an collection of mapping jobs to the API in order to obtain the
    associated FIGI(s).
    Parameters
    ----------
    jobs : list(dict)
        A list of dicts that conform to the OpenFIGI API request structure. See
        https://www.openfigi.com/api#request-format for more information. Note
        rate-limiting requirements when considering length of `jobs`.
    Returns
    -------
    list(dict)
        One dict per item in `jobs` list that conform to the OpenFIGI API
        response structure.  See https://www.openfigi.com/api#response-fomats
        for more information.
    '''
    handler = urllib.request.HTTPHandler()
    opener = urllib.request.build_opener(handler)
    request = urllib.request.Request(openfigi_url, data=bytes(json.dumps(jobs), encoding='utf-8'))
    request.add_header('Content-Type', 'application/json')
    if openfigi_api_key:
        request.add_header('X-OPENFIGI-APIKEY', openfigi_api_key)
    request.get_method = lambda: 'POST'
    _LOGGER_.debug('calling OpenFIGI endpoint at %s' % openfigi_url)
    connection = opener.open(request)
    _LOGGER_.debug('response status %d received from OpenFIGI' % connection.code)
    if connection.code != 200:
        raise Exception('Bad response code %d' % connection.code)
    return json.loads(connection.read().decode('utf-8'))


def get_best_openfigi_result(job_response):
    '''
    Given a response to an OpenFIGI job, return the single "most interesting"
    result - either that having exchange code "US" (a "generic US ticker"),
    or failing that having an exchange code from "UA" (American Stock
    Exchange), "UN" (NYSE), "UR" (broadest tier of NASDAQ) or "UP" (ARCA).
    '''
    all_results = job_response.get('data',[])
    best_result = None
    for result in all_results:
        exch_code = result.get('exchCode',None)
        if exch_code == 'US':
            return result
        elif best_result is None and exch_code in ('UA','UN','UP','UR'):
            best_result = result
    return best_result


def openfigi_result_as_tickerinfo(cusip, openfigi_result):
    return TickerInfo(cusip=cusip,
                      ticker=openfigi_result.get('ticker', None) if openfigi_result else None,
                      fund_name=openfigi_result.get('name', None) if openfigi_result else None,
                      figi=openfigi_result.get('figi', None) if openfigi_result else None,
                      exchange=openfigi_result.get('exchCode', None) if openfigi_result else None)


def call_openfigi_stage(ids_to_query, id_type_plural, id_to_cusip,
                        calls_per_minute, jobs_per_call, call_openfigi_lambda,
                        id_to_job_fn):
    if not ids_to_query:
        _LOGGER_.info('not querying OpenFIGI for %s (none we need to query)' % id_type_plural)
        return dict()
    _LOGGER_.info('start querying OpenFIGI for %s (%d to query)' %
                  (id_type_plural, len(ids_to_query)))
    ids_to_query_with_progress = progress_reporting_iterator(
        ids_to_query, jobs_per_call,
        '%%d of %d %s queried' % (len(ids_to_query), id_type_plural))
    openfigi_jobs_grouped = group_into_sublists(
        map(id_to_job_fn, ids_to_query_with_progress),
        jobs_per_call)
    openfigi_results_grouped = map(
        call_openfigi_lambda,
        rate_limit(openfigi_jobs_grouped, calls_per_minute * 0.95))
    openfigi_results = map(get_best_openfigi_result,
                           itertools.chain.from_iterable(
                               openfigi_results_grouped))
    cusips = tuple(map(id_to_cusip, ids_to_query))
    tickerinfos = map(lambda t: openfigi_result_as_tickerinfo(t[0],t[1]), zip(cusips, openfigi_results))
    cusips_to_tickerinfos = dict(zip(cusips, tickerinfos))
    _LOGGER_.info('finished querying OpenFIGI for %s (%d results returned)' %
                  (id_type_plural, len(cusips_to_tickerinfos)))
    return cusips_to_tickerinfos


def get_openfigi_results(funds,
                         openfigi_cache,
                         openfigi_calls_per_minute,
                         openfigi_jobs_per_call,
                         openfigi_url,
                         openfigi_api_key):
    '''
    Given a list of FundInfo objects, return a dictionary of CUSIPs to
    OpenFIGI results representing everything we can find out from the
    OpenFIGI API and/or the local OpenFIGI cache about any ETFs related
    to those FundInfo objects.
    '''
    if openfigi_cache and os.path.exists(openfigi_cache):
        _LOGGER_.info('loading OpenFIGI cache from %s' % openfigi_cache)
        with open(openfigi_cache, 'r', encoding='UTF-8') as f:
            tickerinfos = tuple(read_tickerinfo_csv(f))
            cache = dict(zip(map(lambda t: t.cusip, tickerinfos), tickerinfos))
    else:
        cache = dict()
    jobs_per_call = openfigi_jobs_per_call or \
                    (OPENFIGI_JOBS_PER_CALL_WITH_KEY if openfigi_api_key
                     else OPENFIGI_JOBS_PER_CALL_WITHOUT_KEY)
    calls_per_minute = openfigi_calls_per_minute or \
                       (OPENFIGI_CALLS_PER_MINUTE_WITH_KEY if openfigi_api_key
                        else OPENFIGI_CALLS_PER_MINUTE_WITHOUT_KEY)
    openfigi_url = openfigi_url or OPENFIGI_ENDPOINT_URL
    call_openfigi_lambda = lambda x: call_openfigi(x, openfigi_url, openfigi_api_key)

    queried_isin_cusips = set(cache.keys())
    queried_cusips = set(cache.keys())

    cache |= call_openfigi_stage(
        tuple(isins_from_sheet_for_funds(funds, cache, queried_isin_cusips)),
        'ISINs',
        lambda x: x[2:11],
        calls_per_minute,
        jobs_per_call,
        call_openfigi_lambda,
        isin_to_openfigi_job)
    cache |= call_openfigi_stage(
        tuple(cusips_from_sheet_for_funds(funds, cache, queried_cusips)),
        'CUSIPs',
        lambda x: x,
        calls_per_minute,
        jobs_per_call,
        call_openfigi_lambda,
        cusip_to_openfigi_job)
    cache |= call_openfigi_stage(
        tuple(isins_from_cusips_for_funds(funds, cache, queried_isin_cusips)),
        'CUSIP-derived ISINs',
        lambda x: x[2:11],
        calls_per_minute,
        jobs_per_call,
        call_openfigi_lambda,
        isin_to_openfigi_job)
    cache |= call_openfigi_stage(
        tuple(cusips_from_isins_for_funds(funds, cache, queried_cusips)),
        'ISIN-derived CUSIPs',
        lambda x: x,
        calls_per_minute,
        jobs_per_call,
        call_openfigi_lambda,
        cusip_to_openfigi_job)

    return cache


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Query the OpenFIGI API for ETF ticker info for all ISINs/CUSIPs in the input spreadsheet')
    parser.add_argument('-v', '--verbose', action='count',
                        help='Increase logging amount')
    parser.add_argument('-q', '--quiet', action='count',
                        help='Decrease logging amount')
    parser.add_argument('-L', '--log-file', metavar='LOG_FILE', type=str,
                        help='Log to FILE and not to stdout')
    parser.add_argument('-c', '--cache', action='store_true',
                        help='Only query OpenFIGI for records not already in output file')
    parser.add_argument('--openfigi-api-key',
                        metavar='KEY', type=str,
                        help='Authentication key for the OpenFIGI API')
    parser.add_argument('--openfigi-jobs-per-call',
                        metavar='LIMIT', type=int,
                        help='Submit no more than LIMIT mapping jobs per OpenFIGI call')
    parser.add_argument('--openfigi-calls-per-minute',
                        metavar='LIMIT', type=float,
                        help='Call OpenFIGI API no more than LIMIT times per minute')
    parser.add_argument('--openfigi-endpoint-url',
                        metavar='URL', type=str,
                        help='OpenFIGI endpoint is at URL (default: %s)' %
                             OPENFIGI_ENDPOINT_URL)
    parser.add_argument('-o', '--output', metavar='OUTPUT_FILE', default=str,
                        help='File to which to write OpenFIGI results as JSON')
    parser.add_argument('input', metavar='INPUT_FILE',
                        type=argparse.FileType('r', encoding='UTF-8'),
                        help='CSV of ETF candidated from HMRC spreadsheet')
    result = parser.parse_args()
    return result


if __name__ == '__main__':
    args = parse_arguments()
    configure_logger(args.log_file, args.verbose, args.quiet)
    funds = tuple(read_fundinfo_csv(args.input))
    tickerinfos = get_openfigi_results(funds,
                                       args.output if args.cache else None,
                                       args.openfigi_calls_per_minute,
                                       args.openfigi_jobs_per_call,
                                       args.openfigi_endpoint_url,
                                       args.openfigi_api_key)
    with open(args.output, 'w', encoding='UTF-8') as f:
        write_tickerinfo_csv(f, sorted(tickerinfos.values(), key=lambda t: t.cusip))

