import csv, dataclasses, re

from _logging import _LOGGER_


@dataclasses.dataclass
class FundInfo:
    family: str
    fund_name: str
    isin: str
    cusip: str
    from_date: str
    to_date: str
    share_class_ref: str = None
    ticker: str = None
    category: str = None


_HEADER_SHARE_CLASS_REF = 'Share Class Ref'
_HEADER_FAMILY          = 'Parent Fund'
_HEADER_FUND_NAME       = 'Sub-Fund'
_HEADER_ISIN            = 'ISIN'
_HEADER_CUSIP           = 'CUSIP'
_HEADER_FROM_DATE       = 'With Effect From'
_HEADER_TO_DATE         = 'Ceased'

_REGEXP_SHARE_CLASS_REF = re.compile(r'\bshare\s+class\s+ref', re.IGNORECASE)
_REGEXP_FAMILY          = re.compile(r'\bparent\s+fund\b', re.IGNORECASE)
_REGEXP_FUND_NAME       = re.compile(r'\bsub\W+fund\b', re.IGNORECASE)
_REGEXP_ISIN            = re.compile(r'\bISIN\b')
_REGEXP_CUSIP           = re.compile(r'\bCUSIP\b')
_REGEXP_FROM_DATE       = re.compile(r'\bwith\s+effect\s+from\b', re.IGNORECASE)
_REGEXP_TO_DATE         = re.compile(r'\bceased\b', re.IGNORECASE)


def column_matching(row, regexp):
    '''
    Given a header row from a spreadsheet, return the index
    of the column whose value matches the given regex pattern
    (or None if no such value is found).
    '''
    return next((i for i, x in enumerate(row) if x is not None and regexp.search(x)), None)


def read_fundinfo_csv(filelike, need_all_columns=True):
    result_count = 0
    ref_column = parent_column = sub_column = isin_column = \
        cusip_column = from_column = to_column = None

    csv_in = csv.reader(filelike)
    for row in csv_in:
        # If we haven't encountered the header row yet, try to match it -
        # in the process figuring out which column each of the data items is in
        if ref_column is None:
            ref_column = column_matching(row, _REGEXP_SHARE_CLASS_REF)
            parent_column = column_matching(row, _REGEXP_FAMILY)
            sub_column = column_matching(row, _REGEXP_FUND_NAME)
            isin_column = column_matching(row, _REGEXP_ISIN)
            cusip_column = column_matching(row, _REGEXP_CUSIP)
            from_column = column_matching(row, _REGEXP_FROM_DATE)
            to_column = column_matching(row, _REGEXP_TO_DATE)
            continue
        if need_all_columns and (
                parent_column is None or sub_column is None or
                isin_column is None or cusip_column is None or
                from_column is None or to_column is None):
            raise Exception('input file missing one or more data columns: ' + filelike.name)

        share_class_ref = row[ref_column] if (ref_column is not None and len(row) > ref_column) else None
        if not share_class_ref:
            continue
        yield FundInfo(
            share_class_ref = share_class_ref,
            family = row[parent_column] if (parent_column is not None and len(row) > parent_column) else None,
            fund_name = row[sub_column] if (sub_column is not None and len(row) > sub_column) else None,
            isin = row[isin_column] if (isin_column is not None and len(row) > isin_column) else None,
            cusip = row[cusip_column] if (cusip_column is not None and len(row) > cusip_column) else None,
            from_date = row[from_column] if (from_column is not None and len(row) > from_column) else None,
            to_date = row[to_column] if (to_column is not None and len(row) > to_column) else None)
        result_count += 1

    if ref_column is None:
        raise Exception('no "share class ref" column in input file: ' + filelike.name)
    _LOGGER_.info('input rows read: %d, filename: %s' % (result_count, filelike.name))


def write_fundinfo_csv(filelike, fundinfos):
    csv_out = csv.writer(filelike)
    csv_out.writerow((
        _HEADER_SHARE_CLASS_REF,
        _HEADER_FAMILY,
        _HEADER_FUND_NAME,
        _HEADER_ISIN,
        _HEADER_CUSIP,
        _HEADER_FROM_DATE,
        _HEADER_TO_DATE))
    csv_out.writerows(map(lambda f: (
        f.share_class_ref,
        f.family,
        f.fund_name,
        f.isin,
        f.cusip,
        f.from_date,
        f.to_date), fundinfos))


@dataclasses.dataclass
class TickerInfo:
    ticker: str
    cusip: str
    fund_name: str = None
    figi: str = None
    exchange: str = None


#_HEADER_CUSIP           = 'CUSIP'
_HEADER_TICKER          = 'Ticker'
_HEADER_NAME            = 'Name'
_HEADER_FIGI            = 'FIGI'
_HEADER_EXCHANGE        = 'Exchange'

#_REGEXP_CUSIP           = re.compile(r'\bCUSIP\b')
# more permissive to allow DTCC data to be used instead of OpenFIGI
_REGEXP_TICKER          = re.compile(r'\b(?:ticker|symbol)\b', re.IGNORECASE)
_REGEXP_NAME            = re.compile(r'\b(?:name|description)\b', re.IGNORECASE)
_REGEXP_FIGI            = re.compile(r'\bFIGI\b')
_REGEXP_EXCHANGE        = re.compile(r'\bexchange\b', re.IGNORECASE)


def read_tickerinfo_csv(filelike):
    result_count = 0

    ticker_column = cusip_column = name_column = \
        figi_column = exchange_column = None

    csv_in = csv.reader(filelike)
    for row in csv_in:
        # If we haven't encountered the header row yet, try to match it -
        # in the process figuring out which column each of the data items is in
        if cusip_column is None:
            ticker_column = column_matching(row, _REGEXP_TICKER)
            cusip_column = column_matching(row, _REGEXP_CUSIP)
            name_column = column_matching(row, _REGEXP_NAME)
            figi_column = column_matching(row, _REGEXP_FIGI)
            exchange_column = column_matching(row, _REGEXP_EXCHANGE)
            continue

        cusip = row[cusip_column] if (cusip_column is not None and len(row) > cusip_column) else None
        if not cusip:
            continue
        yield TickerInfo(
            cusip = cusip,
            ticker = row[ticker_column] if (ticker_column is not None and len(row) > ticker_column) else None,
            fund_name = row[name_column] if (name_column is not None and len(row) > name_column) else None,
            figi = row[figi_column] if (figi_column is not None and len(row) > figi_column) else None,
            exchange = row[exchange_column] if (exchange_column is not None and len(row) > exchange_column) else None)
        result_count += 1

    if cusip_column is None:
        raise Exception('no CUSIP column in input file: ' + filelike.name)
    _LOGGER_.info('input rows read: %d, filename: %s' % (result_count, filelike.name))


def write_tickerinfo_csv(filelike, tickerinfos):
    csv_out = csv.writer(filelike)
    csv_out.writerow((
        _HEADER_CUSIP,
        _HEADER_TICKER,
        _HEADER_NAME,
        _HEADER_FIGI,
        _HEADER_EXCHANGE))
    csv_out.writerows(map(lambda f: (
        f.cusip,
        f.ticker,
        f.fund_name,
        f.figi,
        f.exchange), tickerinfos))
