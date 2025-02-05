#!/usr/bin/env python3

import argparse, csv, re

from _csv_formats import read_fundinfo_csv, safe_get_column, column_matching, \
    _REGEXP_SHARE_CLASS_REF, _REGEXP_TO_DATE
from _logging import configure_logger


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Find "sibling" funds in same families as reporting ETFs')
    parser.add_argument('-v', '--verbose', action='count',
                        help='Increase logging amount')
    parser.add_argument('-q', '--quiet', action='count',
                        help='Decrease logging amount')
    parser.add_argument('-L', '--log-file', metavar='LOG_FILE', type=str,
                        help='Log to FILE and not to stdout')
    parser.add_argument('-i', '--input', metavar='INPUT_FILE', required=True,
                        type=argparse.FileType('r', encoding='UTF-8'),
                        help='CSV of raw HMRC spreadsheet data')
    parser.add_argument('-o', '--output', metavar='OUTPUT_FILE', required=True,
                        type=argparse.FileType('w', encoding='UTF-8'),
                        help='File to which to write siblings report as CSV')
    parser.add_argument('results', metavar='REPORTING_FUNDS_FILE', nargs='+',
                        type=argparse.FileType('r', encoding='UTF-8'),
                        help='CSV of reporting funds')
    result = parser.parse_args()
    return result


__REGEXP_AFTER_DASH = re.compile(r'-.*$')
__REGEXP_DATE = re.compile(r'^\d\d\/\d\d\/\d{4}$')


if __name__ == '__main__':
    args = parse_arguments()
    configure_logger(args.quiet, args.verbose, args.log_file)

    share_class_refs = set()
    for r in args.results:
        share_class_refs |= set(map(lambda f: f.share_class_ref, read_fundinfo_csv(r)))
    families = set(map(lambda x: __REGEXP_AFTER_DASH.sub('', x), share_class_refs))
    families_regexp = re.compile(r'^(?:'+r'|'.join(map(re.escape, families))+r')-')

    csv_in = csv.reader(args.input)
    csv_out = csv.writer(args.output)
    share_class_ref_col = ceased_col = None
    for row in csv_in:
        if share_class_ref_col is None:
            share_class_ref_col = column_matching(row, _REGEXP_SHARE_CLASS_REF)
            ceased_col = column_matching(row, _REGEXP_TO_DATE)
        else:
            share_class_ref = safe_get_column(share_class_ref_col, row)
            ceased = safe_get_column(ceased_col, row)
            if not share_class_ref \
                    or __REGEXP_DATE.match(ceased) \
                    or share_class_ref in share_class_refs \
                    or not families_regexp.match(share_class_ref):
                continue
        if share_class_ref_col is not None:
            csv_out.writerow(row)

