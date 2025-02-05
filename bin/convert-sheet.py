#!/usr/bin/env python3


import argparse, contextlib, csv, re, sys
from _logging import _LOGGER_, configure_logger


def odfpy_cell_to_text(cell):
    # thanks, https://github.com/marcoconti83/read-ods-with-odfpy/blob/master/ODSReader.py#L63
    import odf.text
    ps = cell.getElementsByType(odf.text.P)
    text_content = ""
    for p in ps:
        for n in p.childNodes:
            if (n.nodeType == 1 and (
                    (n.tagName == "text:span") or (n.tagName == "text:a"))):
                for c in n.childNodes:
                    if (c.nodeType == 3):
                        text_content = u'{}{}'.format(text_content, c.data)
            if (n.nodeType == 3):
                text_content = u'{}{}'.format(text_content, n.data)
    return text_content.strip() if re.search(r'\w', text_content) else None


def parse_sheet(filename):
    """
    Given a filename from which we can read the spreadsheet,
    generate a series of rows from the first sheet in the workbook.
    """
    if re.match(r'^(?:.*/)?[^/]+\.xls[mx](?:\b[^/]+)?$', filename):
        # apt-get install python3-openpyxl || pip3 install openpyxl
        import openpyxl
        _LOGGER_.info('start parsing spreadsheet (using openpyxl)')
        with contextlib.closing(openpyxl.load_workbook(filename=filename,
                                                       read_only=True)) as wb:
            _LOGGER_.info('finish parsing spreadsheet')
            for row in wb.worksheets[0]:
                yield list(map(lambda x: x.value, row))
    elif re.match(r'^(?:.*/)?[^/]+\.ods(?:\b[^/]+)?$', filename):
        # apt-get install python3-odf || pip3 install odfpy
        import odf.opendocument, odf.table
        _LOGGER_.info('start parsing spreadsheet (using odfpy)')
        doc = odf.opendocument.load(filename)
        _LOGGER_.info('finish parsing spreadsheet')
        tbl = doc.spreadsheet.getElementsByType(odf.table.Table)[0]
        for row in tbl.getElementsByType(odf.table.TableRow):
            yield list(map(odfpy_cell_to_text,
                           row.getElementsByType(odf.table.TableCell)))
    else:
        raise Exception(
            'cannot determine file format from filename: ' + filename)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='convert a spreadsheet to CSV')
    parser.add_argument('-v', '--verbose', action='count',
                        help='Increase logging amount')
    parser.add_argument('-L', '--log-file', metavar='FILE', type=str,
                        help='Log to FILE and not to stdout')
    parser.add_argument('input', metavar='INPUT', type=str,
                        help='Spreadsheet file to be read')
    parser.add_argument('output', nargs='?', metavar='OUTPUT',
                        type=argparse.FileType('w', encoding='UTF-8'),
                        default=sys.stdout,
                        help='CSV file to be written')
    result = parser.parse_args()
    return result


if __name__ == '__main__':
    args = parse_arguments()
    configure_logger(args.log_file, args.verbose)
    _LOGGER_.info('start writing spreadsheet')
    csv.writer(args.output).writerows(parse_sheet(args.input))
    _LOGGER_.info('finish writing spreadsheet')
