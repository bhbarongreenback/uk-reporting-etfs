#!/usr/bin/env python3

import argparse, datetime, re

from _csv_formats import read_fundinfo_csv
from _logging import _LOGGER_, configure_logger


_REGEXP_WIKI_UNSAFE_CHARS = re.compile(r'[&<>{}\[\]\\\u007f-\uffff]')


def mediawiki_escape(s):
    return _REGEXP_WIKI_UNSAFE_CHARS.sub(lambda m: '&#%d;' % ord(m.group(0)), s)


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
        description='Convert CSV results file to wikitext markup')
    parser.add_argument('-v', '--verbose', action='count',
                        help='Increase logging amount')
    parser.add_argument('-q', '--quiet', action='count',
                        help='Decrease logging amount')
    parser.add_argument('-L', '--log-file', metavar='LOG_FILE', type=str,
                        help='Log to FILE and not to stdout')
    parser.add_argument('-o', '--output', metavar='OUTPUT_FILE',
                        type=argparse.FileType('w', encoding='UTF-8'),
                        help='File to which to write wikitext')
    parser.add_argument('input', metavar='INPUT_FILE',
                        type=argparse.FileType('r', encoding='UTF-8'),
                        help='CSV of funds to appear in wikitext')
    result = parser.parse_args()
    return result


if __name__ == '__main__':
    args = parse_arguments()
    configure_logger(args.quiet, args.verbose, args.log_file)

    enhanced_fund_info = tuple(read_fundinfo_csv(args.input))
    write_wiki_output(enhanced_fund_info, args.output)
