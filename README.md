# What's this repository about?

The scripts in this repository download the current list of
[approved offshore reporting funds](https://www.gov.uk/government/publications/offshore-funds-list-of-reporting-funds)
from the HMRC website, enhance it with data from Bloomberg's [OpenFIGI API](https://www.openfigi.com/api), and output
a list of UK-reporting US ETFs, with options to filter the list and group it into categories.

This is a topic of specialist interest to some DIY investors on
the [Bogleheads&reg; Non-US Investing forum](https://www.bogleheads.org/forum/viewforum.php?f=22), particularly 
[US taxpayers residing in the UK](https://www.bogleheads.org/wiki/Investing_from_the_UK_for_US_citizens_and_US_permanent_residents).


# Requirements

- Python 3 (developed/tested with Python 3.9)
- Something to convert the HMRC data spreadsheet to CSV
    - Recommended: [`ssconvert`](https://manpages.debian.org/bookworm/gnumeric/ssconvert.1.en.html), a command-line
      utility which comes with [Gnumeric](http://www.gnumeric.org/)
    - Also recommended: [LibreOffice](https://www.libreoffice.org/) - if available, the script will attempt to use
      LibreOffice's command-line interface to convert the spreadsheet
    - If you don't have ssconvert or LibreOffice, the scripts will try to convert the sheet to CSV using the
      Python [`odfpy`](https://github.com/eea/odfpy) or [`openpyxl`](https://openpyxl.readthedocs.io/en/stable/)
      modules.  Do note that this will require roughly 10x more time and memory.
- GNU Make
- `sed` and `wget` (the cut-down versions in [busybox](https://www.busybox.net/) ought to work)
- `diff` (optional - to print the changes relative to the previous version at the end of the process)

Developed/tested on Debian Linux. Probably works on Mac OS, but might fail because their shell commands differ slightly
from those found on Linux (in which case please file a bug). You'll probably need WSL2 or something to run this on
Windows.


# Running the scripts

`make clean && make` should work most of the time.  Wikitext output will be in `build/wiki-main.txt` for the
[main list](https://www.bogleheads.org/wiki/US_domiciled_ETFs_that_are_UK_HMRC_reporting_funds)
and `build/wiki-secondary.txt` for the
[secondary list](https://www.bogleheads.org/wiki/UK-reporting_US_ETFs_not_included_in_the_main_listing).

If new ETFs have come along since the last time [`data/fund-categories.csv`](data/fund-categories.csv) was updated,
the process will fail with an error message telling which CUSIPs (with corresponding tickers) need to be added to
the fund categories file.  Go look up the new ETFs, add appropriate entries to the categories file, then restart
the process by running `make` - this will restart the scripts from the failed step, rather than from the beginning.

# The data files

These files are expected to be maintained by a human and committed to this repository. In descending order of
how often you'll need to interact with them:

- [`data/fund-categories.csv`](data/fund-categories.csv) - A mapping of fund CUSIPs to the desired category in
  the main output. Funds to be excluded from the main output have a blank category.
- [`data/fund-families.txt`](data/fund-families.txt) - A list of short fund family names, one per line.
  If the "parent fund name" in the HMRC sheet begins with one of the fund family names from this file,
  use this shorter name instead, rather than the longer legal entity name from the HMRC sheet.
- [`data/errata.csv`](data/errata.csv) - The HMRC data sheet is known to contain erroneous data.
  The "Share Class Ref" column is used as the key to match against rows in the original sheet; non-blank columns
  in the errata file override the values in the corresponding columns of the HMRC sheet.


# Intermediate result files and scripts

The process is broken up into steps, each run by a different script/command, and each of which produces an intermediate
result file.  Those files, in the order they are produced: 

- `build/hmrc-data-page.html` - Latest copy of the 
  [approved offshore reporting funds](https://www.gov.uk/government/publications/offshore-funds-list-of-reporting-funds)
  page.  Downloaded using `wget`.
- `build/hmrc-data-url.txt` - URL where the latest HMRC data spreadsheet can be downloaded. Parsed from the above web
  page using a `sed` one-liner.
- `build/hmrc-raw-data.bin` - The HMRC spreadsheet itself, downloaded using `wget`.
    - `build/hmrc-raw-data.ods` or `build/hmrc-raw-data.xlsx` - Symbolic link to the HMRC spreadsheet data file, with a
      file extension that lets the spreadsheet-conversion tools used in the next step know its format.
- `build/hmrc-raw-data.csv` - The above file converted to CSV, which is easier for the Python scripts to read. The
  conversion is done by `ssconvert` (if present) or by [`bin/convert-sheet.py`](bin/convert-sheet.py) (if not).
- `build/hmrc-data.csv` - The above file with corrections applied from the errata file, then filtered down to just
  those rows with valid CUSIPs or US ISINs and empty cease dates. This is produced by
  [`bin/filter-hmrc-sheet.py`](bin/filter-hmrc-sheet.py).
- `build/openfigi-data.csv` - Query results from the [OpenFIGI API](https://www.openfigi.com/api) for each
  "interesting" ISIN/CUSIP in the HMRC sheet. The queries are conducted by
  [`bin/call-openfigi.py`](bin/call-openfigi.py).  Do note that absent an OpenFIGI API key, this will be one of
  the slower steps in the process, owing to rate limits imposed on non-authenticated users by OpenFIGI.
- `build/uncategorized-funds.csv` - An "inverse" version of the fund categories list in
  [`data/fund-categories.csv`](data/fund-categories.csv), with uncategorized funds assigned to the
  "Excluded funds" category, and categorized funds stripped of their category. Used to produce the
  [secondary list](https://www.bogleheads.org/wiki/UK-reporting_US_ETFs_not_included_in_the_main_listing)
  of "non-Bogleheady" ETFs. Generated using a `sed` one-liner.
- `build/results-main.csv` - Information about the ETFs which appear in the tables in the
  [main list](https://www.bogleheads.org/wiki/US_domiciled_ETFs_that_are_UK_HMRC_reporting_funds). Generated from the
  above files by [`bin/generate-results.py`](bin/generate-results.py).
- `build/results-secondary.csv` - Information about the ETFs which appear in the tables in the
  [secondary list](https://www.bogleheads.org/wiki/UK-reporting_US_ETFs_not_included_in_the_main_listing). Generated
  from the above files by [`bin/generate-results.py`](bin/generate-results.py).
- `build/wiki-main.txt` - MediaWiki-style wikitext source for the ETF tables in the main list. Generated from
  `build/results-main.csv` by [`bin/results-to-wikitext.py`](bin/results-to-wikitext.py).
  - `build/wiki-main.txt.OLD-YYYYMMDDHHMM` - Output from previous runs of this process, used to generate the diff
    printed to the console at the end. Moved from `build/wiki-main.txt` to this location when you run `make clean`.
- `build/wiki-secondary.txt` - MediaWiki-style wikitext source for the ETF tables in the secondary list. Generated
  from `build/results-secondary.csv` by [`bin/results-to-wikitext.py`](bin/results-to-wikitext.py).
  - `build/wiki-secondary.txt.OLD-YYYYMMDDHHMM` - Output from previous runs of this process, used to generate the diff
    printed to the console at the end. Moved from `build/wiki-secondary.txt` to this location when you run `make clean`.
- `build/siblings.csv` - Rows from the raw HMRC spreadsheet (`build/hmrc-raw-data.csv`) which correspond to funds from
  the same fund families as those in the main and secondary lists, but which haven't been included in those lists for
  some reason.  This may be due to some unusual circumstance with the fund (such as a reorganization or liquidation),
  or it may be due to erroneous data in the HMRC sheet.  Generated by [`bin/find-siblings.py`](bin/find-siblings.py).
  - `build/siblings.csv.OLD-YYYYMMDDHHMM` - Output from previous runs of this process, used to generate the diff
    printed to the console at the end. Moved from `build/siblings.csv` to this location when you run `make clean`.


# More info

A [discussion thread](https://www.bogleheads.org/forum/viewtopic.php?t=393286) about this script has been created in the
Bogleheads [Non-US Investing forum](https://www.bogleheads.org/forum/viewforum.php?f=22).

