#!/usr/bin/env python3


import argparse, re, sys

from _cusip_isin import cusip_check_digit, isin_check_digit
from _logging import _LOGGER_, configure_logger
from _csv_formats import read_fundinfo_csv, write_fundinfo_csv


_REGEXP_NOT_ALNUM = re.compile(r'[^0-9A-Z]+')
_REGEXP_DATE_DDMMYYYY = re.compile(r'(?:0[1-9]|[12]\d|3[01])/(?:0[1-9]|1[0-2])/\d{4}')


def sheet_to_fund_info(hmrc_sheet_filelike, errata):
    """
    Given rows from the HMRC worksheet, return a FundInfo object
    for each "interesting-looking" row in the sheet (i.e. those having
    a valid CUSIP and/or US ISIN), applying any corrections from the
    errata before performing any processing.
    """
    _LOGGER_.info('start processsing HMRC spreadsheet contents')

    fund_count = 0
    for fund in read_fundinfo_csv(hmrc_sheet_filelike, True):
        # If the fund is mentioned in the errata file, override data in
        # the HMRC sheet with any non-blank values from the errata file
        if fund.share_class_ref in errata:
            erratum = errata[fund.share_class_ref]
            merge_fundinfos(fund, erratum)
        # ...then perform various data checks/cleanups:
        if fund.cusip is not None:
            fund.cusip = _REGEXP_NOT_ALNUM.sub('', fund.cusip.strip().upper())
            if fund.cusip:
                if len(fund.cusip) == 8:
                    # sometimes CUSIPs are missing their check digit
                    fund.cusip += cusip_check_digit(fund.cusip)
                elif len(fund.cusip) != 9:
                    # entirely wrong-length CUSIP - ignore (non-CUSIP national identifiers tend to get shoved in this column)
                    fund.cusip = None
                elif cusip_check_digit(fund.cusip[0:8]) != fund.cusip[8:9]:
                    # check digit doesn't check out, so CUSIP got garbled somewhere (or isn't really a CUSIP) - ignore
                    fund.cusip = None
        if fund.isin is not None:
            fund.isin = _REGEXP_NOT_ALNUM.sub('', fund.isin.strip().upper())
            if fund.isin:
                if not fund.isin.startswith('US'):
                    # non-US ISIN, therefore non-US domiciled fund - row doesn't interest us then
                    continue
                elif len(fund.isin) == 11:
                    # assume ISIN is missing its check digit
                    fund.isin += isin_check_digit(fund.isin)
                elif len(fund.isin) != 12:
                    # wrong-length ISIN - ignore
                    fund.isin = None
                elif isin_check_digit(fund.isin[0:11]) != fund.isin[11:12]:
                    # check digit doesn't check out, so ISIN got garbled somewhere (or isn't really an ISIN) - ignore
                    fund.isin = None
        if not fund.isin and not fund.cusip:
            # ignore rows having neither an ISIN nor a CUSIP
            continue
        if fund.from_date is not None and not _REGEXP_DATE_DDMMYYYY.match(fund.from_date.strip()):
            fund.from_date = None
        if fund.to_date is not None and not _REGEXP_DATE_DDMMYYYY.match(fund.to_date.strip()):
            fund.to_date = None
        if fund.to_date:
            # fund has a date where it ceased to be a UK reporting fund - row doesn't interest us then
            continue
        yield fund
        fund_count += 1
    _LOGGER_.info('finish processsing HMRC spreadsheet contents (%d candidates found)' % fund_count)


def merge_fundinfos(dest, src):
    if src.family:
        dest.family = src.family
    if src.fund_name:
        dest.fund_name = src.fund_name
    if src.isin:
        dest.isin = src.isin
    if src.cusip:
        dest.cusip = src.cusip
    if src.from_date:
        dest.from_date = src.from_date
    if src.to_date:
        dest.to_date = src.to_date


def merge_errata(*errata_filelikes):
    _LOGGER_.info('start reading errata')
    result = dict()
    for errata_filelike in errata_filelikes:
        for fundinfo in read_fundinfo_csv(errata_filelike, False):
            if fundinfo.share_class_ref not in result:
                result[fundinfo.share_class_ref] = fundinfo
            else:
                merge_fundinfos(result[fundinfo.share_class_ref], fundinfo)
    _LOGGER_.info('finish reading errata (%d records read)' % len(result))
    return result


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Apply errata to the input spreadsheet, filtering out irrelevant rows')
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
    parser.add_argument('input', metavar='INPUT_FILE',
                        type=argparse.FileType('r', encoding='UTF-8'),
                        help='CSV version of raw HMRC spreadsheet')
    parser.add_argument('errata', nargs='*', metavar='ERRATA_FILE',
                        type=argparse.FileType('r', encoding='UTF-8'),
                        help='CSV file containing errata to be applied to HMRC sheet')
    result = parser.parse_args()
    return result


if __name__ == '__main__':
    args = parse_arguments()
    configure_logger(args.log_file, args.verbose, args.quiet)
    errata = merge_errata(*args.errata)
    fundinfos = sheet_to_fund_info(args.input, errata)
    write_fundinfo_csv(args.output, fundinfos)

