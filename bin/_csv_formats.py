import csv, dataclasses, re

from _logging import _LOGGER_


def column_matching(row, regexp):
    '''
    Given a header row from a spreadsheet, return the index
    of the column whose value matches the given regex pattern
    (or None if no such value is found).
    '''
    return next((i for i, x in enumerate(row) if x is not None and regexp.search(x)), None)


def safe_get_column(column, row):
    if column is not None and len(row) > column and row[column] not in ('\u2014', 'no data'):
        return row[column]
    else:
        return None


@dataclasses.dataclass
class TickerInfo:
    ticker: str
    cusip: str
    fund_name: str = None
    figi: str = None
    exchange: str = None


_HEADER_CUSIP           = 'CUSIP'
_HEADER_TICKER          = 'Ticker'
_HEADER_NAME            = 'Name'
_HEADER_FIGI            = 'FIGI'
_HEADER_EXCHANGE        = 'Exchange'

_REGEXP_CUSIP           = re.compile(r'\bCUSIP\b')
# more permissive to allow DTCC data to be used for TickerInfo instead of OpenFIGI
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

        cusip = safe_get_column(cusip_column, row)
        if not cusip:
            continue
        yield TickerInfo(
            cusip=cusip,
            ticker=safe_get_column(ticker_column, row),
            fund_name=safe_get_column(name_column, row),
            figi=safe_get_column(figi_column, row),
            exchange=safe_get_column(exchange_column, row))
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


@dataclasses.dataclass
class FundInfo:
    share_class_ref: str
    family: str
    fund_name: str
    isin: str
    cusip: str
    from_date: str
    to_date: str
    ticker: str = None
    category: str = None
    figi: str = None


_HEADER_SHARE_CLASS_REF = 'Share Class Ref'
_HEADER_FAMILY          = 'Parent Fund'
_HEADER_FUND_NAME       = 'Sub-Fund'
_HEADER_ISIN            = 'ISIN'
_HEADER_FROM_DATE       = 'With Effect From'
_HEADER_TO_DATE         = 'Ceased'
_HEADER_CATEGORY        = 'Category'

_REGEXP_SHARE_CLASS_REF = re.compile(r'\bshare\s+class\s+ref', re.IGNORECASE)
_REGEXP_FAMILY          = re.compile(r'\bparent\s+fund\b', re.IGNORECASE)
_REGEXP_FUND_NAME       = re.compile(r'\bsub\W+fund\b', re.IGNORECASE)
_REGEXP_ISIN            = re.compile(r'\bISIN\b')
_REGEXP_FROM_DATE       = re.compile(r'\bwith\s+effect\s+from\b', re.IGNORECASE)
_REGEXP_TO_DATE         = re.compile(r'\bceased\b', re.IGNORECASE)
_REGEXP_CATEGORY        = re.compile(r'\bcategory\b', re.IGNORECASE)


def read_fundinfo_csv(filelike, need_all_columns=True):
    result_count = 0
    ref_column = parent_column = sub_column = isin_column = \
        cusip_column = from_column = to_column = \
        ticker_column = category_column = figi_column = None

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
            ticker_column = column_matching(row, _REGEXP_TICKER)
            category_column = column_matching(row, _REGEXP_CATEGORY)
            figi_column = column_matching(row, _REGEXP_FIGI)
            continue
        if need_all_columns and (
                parent_column is None or sub_column is None or
                isin_column is None or cusip_column is None or
                from_column is None or to_column is None):
            raise Exception('input file missing one or more data columns: ' + filelike.name)

        share_class_ref = safe_get_column(ref_column, row)
        if not share_class_ref:
            continue
        yield FundInfo(
            share_class_ref=share_class_ref,
            family=safe_get_column(parent_column, row),
            fund_name=safe_get_column(sub_column, row),
            isin=safe_get_column(isin_column, row),
            cusip=safe_get_column(cusip_column, row),
            from_date=safe_get_column(from_column, row),
            to_date=safe_get_column(to_column, row),
            ticker=safe_get_column(ticker_column, row),
            category=safe_get_column(category_column, row),
            figi=safe_get_column(figi_column, row))
        result_count += 1

    if ref_column is None:
        raise Exception('no "share class ref" column in input file: ' + filelike.name)
    _LOGGER_.info('input rows read: %d, filename: %s' % (result_count, filelike.name))


def fundinfo_to_csv_row(fundinfo, include_enhanced_columns=False):
    row = (fundinfo.share_class_ref,
           fundinfo.family,
           fundinfo.fund_name,
           fundinfo.isin,
           fundinfo.cusip,
           fundinfo.from_date,
           fundinfo.to_date)
    if include_enhanced_columns:
        row += (fundinfo.ticker, fundinfo.category, fundinfo.figi)
    return row


def write_fundinfo_csv(filelike, fundinfos, include_enhanced_columns=False):
    csv_out = csv.writer(filelike)
    header = (_HEADER_SHARE_CLASS_REF,
        _HEADER_FAMILY,
        _HEADER_FUND_NAME,
        _HEADER_ISIN,
        _HEADER_CUSIP,
        _HEADER_FROM_DATE,
        _HEADER_TO_DATE)
    if include_enhanced_columns:
        header += (_HEADER_TICKER, _HEADER_CATEGORY, _HEADER_FIGI)
    csv_out.writerow(header)
    csv_out.writerows(map(lambda f: fundinfo_to_csv_row(f, include_enhanced_columns), fundinfos))

