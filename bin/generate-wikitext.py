#!/usr/bin/env python3

import argparse, csv, datetime, json, re, sys

from _cusip_isin import make_isin_from_cusip
from _csv_formats import read_fundinfo_csv, column_matching, read_tickerinfo_csv
from _logging import _LOGGER_, configure_logger


def read_families_file(families_filelike):
    '''
    Read in the fund families file (which currently is just a plain text
    file consisting of one fund family name per line.)  Returns a tuple
    containing all family names.
    '''
    _LOGGER_.info('reading fund families from %s' % families_filelike.name)
    result = list()
    for line in families_filelike:
        line = line.strip()
        if line:
            result.append(line)
    _LOGGER_.info('%d fund familes read' % len(result))
    return tuple(result)


_REGEXP_CUSIP = re.compile(r'\bCUSIP\b', re.IGNORECASE)
_REGEXP_CATEGORY = re.compile(r'\bcategory\b', re.IGNORECASE)


def read_categories_file(categories_filelike):
    '''
    Read in the fund categories file (a CSV file consisting of a header
    row telling which is the CUSIP column and which is the category column,
    followed by data rows).  Returns a dictionary of CUSIPs to categories.
    '''
    _LOGGER_.info('reading fund categories from %s' % categories_filelike.name)
    result = dict()
    csv_in = csv.reader(categories_filelike)
    header_row = next(csv_in)
    cusip_column = column_matching(header_row, _REGEXP_CUSIP)
    category_column = column_matching(header_row, _REGEXP_CATEGORY)
    if cusip_column is None or category_column is None:
        raise Exception('categories file needs a "CUSIP" column and a "Category" column')
    for row in csv_in:
        cusip = row[cusip_column]
        if not cusip:
            continue
        category = row[category_column]
        result[cusip] = category
    _LOGGER_.info('category data for %d funds read' % len(result))
    return result


def result_for_fundinfo(fund, cusip_to_tickerinfo):
    '''
    Given a FundInfo object and a dictionary of CUSIPs to
    TickerInfo objects, return the relevant TickerInto object
    based on either the ISIN or the CUSIP (or None if no relevant
    result exists).
    '''
    if fund.isin and fund.isin[2:11] in cusip_to_tickerinfo and cusip_to_tickerinfo[fund.isin[2:11]].ticker:
        return (fund.isin[2:11], cusip_to_tickerinfo[fund.isin[2:11]])
    elif fund.cusip and fund.cusip in cusip_to_tickerinfo and cusip_to_tickerinfo[fund.cusip].ticker:
        return (fund.cusip, cusip_to_tickerinfo[fund.cusip])
    return (None, None)


_REGEXP_TRAILING_RUBBISH = re.compile(r'\b(\s+-\s*|\s*-\s+)\b(?=.*\b(shares?|class)\b)([^-]+)$', re.I)


def enhance_fund_data(funds, cusip_to_tickerinfo, fund_families,
                      fund_categories):
    '''
    Take the FundInfo objects derived from the HMRC sheet and match them
    with ticker data from OpenFIGI and fund categories from the categories
    file; clean up the family and fund names with help from the fund familes
    list; and return a list containing only those funds with known tickers
    and categories.
    '''
    result = list()
    seen_cusips = set()
    uncategorized_funds = list()
    family_regex = re.compile(r'^('+'|'.join(map(re.escape, fund_families))+r')\b', re.I)
    _LOGGER_.info('start enhancing fund data')
    for fund in funds:
        # Determine ticker for the fund...
        (cusip, tickerinfo) = result_for_fundinfo(fund, cusip_to_tickerinfo)
        if not tickerinfo or cusip in seen_cusips:
            # ...ignoring the fund if there's no ETF ticker, or it's a
            # duplicate ISIN (sometimes seen in the HMRC data?!)
            continue
        seen_cusips.add(cusip)
        fund.ticker = tickerinfo.ticker
        # ...and ensure the fund has a correct ISIN set,
        # so we can include it as part of the output
        fund.cusip = cusip
        fund.isin = make_isin_from_cusip(fund.cusip)
        # Determine the fund family name from the HMRC "parent fund" data
        # (if parent fund starts with one of the family names from the
        # fund families file, use the shorter family name instead)
        m = family_regex.match(fund.family)
        if m:
            fund.family = m.group(1)
        # Look up the category of the fund using the CUSIP
        if fund.cusip not in fund_categories:
            # If the CUSIP doesn't appear in the categories file, add the
            # fund to the list of uncategorized funds, and ignore it
            uncategorized_funds.append(fund)
            continue
        elif not fund_categories[fund.cusip]:
            # Ignore the fund if CUSIP is in the file but category is blank
            continue
        else:
            fund.category = fund_categories[fund.cusip]
        # Finally, clean up the fund name following a few rules...
        # Strip the fund family name from the start of the fund name
        fund.fund_name = re.sub('^'+re.escape(fund.family)+r'\s+','',fund.fund_name, re.I)
        # If the fund name ends in a dash with a space immediately before
        # or after it, followed by some words including 'share', 'shares'
        # or 'class', strip anything after the dash
        fund.fund_name = _REGEXP_TRAILING_RUBBISH.sub('', fund.fund_name)
        result.append(fund)
    _LOGGER_.info('finished enhancing fund data (%d funds enhanced)' % len(result))
    if uncategorized_funds:
        _LOGGER_.error('%d uncategorized fund(s) detected: %s' % (
            len(uncategorized_funds),
            ', '.join(map(lambda x: "%s (%s)" % (x.ticker, x.isin[2:11]), uncategorized_funds))))
        _LOGGER_.debug('uncategorized fund detail: %r' % uncategorized_funds)
        sys.exit(1)
    # Sort the funds nicely - by family, then fund name
    result.sort(key=lambda f: f.family.upper() + '    ' + f.fund_name.upper())
    return result


_REGEXP_NOT_USASCII = re.compile(r'[&<>{}\[\]\\\u007f-\uffff]')


def mediawiki_escape(s):
    return _REGEXP_NOT_USASCII.sub(lambda m:'&#%d;'%ord(m.group(0)), s)


def reformat_date_from_ddmmyyyy_to_ddmmmyyyy(date_string):
    try:
        return datetime.datetime.strptime(date_string, '%d/%m/%Y').strftime('%d %b %Y')
    except:
        _LOGGER_.debug('couldn\'t reformat date: %s' % date_string)
        return date_string


def write_wiki_output(funds, output):
    is_first_table = True
    for category in sorted(set(map(lambda f: f.category, funds)), key=str.lower):
        output.write('=== %s ===\n' % mediawiki_escape(category))
        if is_first_table:
            output.write('{{mw-datatable}}\n')
            is_first_table = False
        output.write('{| class="wikitable sortable mw-datatable"\n')
        output.write('! Ticker || Fund Family || Fund Name || CUSIP || HMRC Reporting Since\n')
        for fund in funds:
            if fund.category == category:
                output.write('|-\n| ' + ' || '.join([
                    '[https://etf.com/%s %s]' % (fund.ticker, fund.ticker),
                    mediawiki_escape(fund.family),
                    mediawiki_escape(fund.fund_name),
                    '<span title="ISIN: %s">%s</span>' % (fund.isin, fund.isin[2:11]),
                    reformat_date_from_ddmmyyyy_to_ddmmmyyyy(fund.from_date)
                ]) + '\n')
        output.write('|}\n\n')


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Generate wikitext tables containing ETF data')
    parser.add_argument('-v', '--verbose', action='count',
                        help='Increase logging amount')
    parser.add_argument('-q', '--quiet', action='count',
                        help='Decrease logging amount')
    parser.add_argument('-L', '--log-file', metavar='LOG_FILE', type=str,
                        help='Log to FILE and not to stdout')
    parser.add_argument('-o', '--output', metavar='OUTPUT_FILE',
                        default=sys.stdout,
                        type=argparse.FileType('w', encoding='UTF-8'),
                        help='CSV output')
    parser.add_argument('-i', '--hmrc-data', metavar='HMRC_DATA_FILE',
                        required=True,
                        type=argparse.FileType('r', encoding='UTF-8'),
                        help='CSV input of filtered data from HMRC spreadsheet')
    parser.add_argument('-g', '--openfigi-data', metavar='OPENFIGI_DATA_FILE',
                        required=True,
                        type=argparse.FileType('r', encoding='UTF-8'),
                        help='JSON input of OpenFIGI query results')
    parser.add_argument('-c', '--categories', metavar='CATEGORY_DATA_FILE',
                        required=True,
                        type=argparse.FileType('r', encoding='UTF-8'),
                        help='CSV input of fund category data')
    parser.add_argument('-f', '--families', metavar='FUND_FAMILIES_FILE',
                        required=True,
                        type=argparse.FileType('r', encoding='UTF-8'),
                        help='text file containing fund family names')
    result = parser.parse_args()
    return result


if __name__ == '__main__':
    args = parse_arguments()
    configure_logger(args.quiet, args.verbose, args.log_file)

    fund_info = read_fundinfo_csv(args.hmrc_data)
    tickerinfos = tuple(read_tickerinfo_csv(args.openfigi_data))
    cusip_to_tickerinfo = dict(zip(map(lambda t: t.cusip, tickerinfos), tickerinfos))
    fund_families = read_families_file(args.families)
    fund_categories = read_categories_file(args.categories)
    result = enhance_fund_data(fund_info, cusip_to_tickerinfo,
                               fund_families, fund_categories)
    write_wiki_output(result, args.output)

