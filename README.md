# What's this repository about?

This script downloads the current list of [approved offshore reporting funds](https://www.gov.uk/government/publications/offshore-funds-list-of-reporting-funds) from the HMRC website, enhances it with data from Bloomberg's [OpenFIGI API](https://www.openfigi.com/api), and outputs a list of UK-reporting US ETFs, with options to filter the list and group it into categories.

This is a topic of specialist interest to some DIY investors on the [Bogleheads&reg; Non-US Investing forum](https://www.bogleheads.org/forum/viewforum.php?f=22), particularly [US taxpayers residing in the UK](https://www.bogleheads.org/wiki/Investing_from_the_UK_for_US_citizens_and_US_permanent_residents).


# Requirements

(This script is run from the command prompt.  If you're not knowledgeable about running tools from the command prompt, you'll struggle with what follows.)

You'll need Python 3 installed.  (To check if you do: open a command prompt and type "python3 --version"; you should then see a brief message giving a version number starting with a 3, and not an earlier verison number or an error complaining that the command was not found.)  If you don't have Python 3 installed, go download it from [the official Python site](https://www.python.org/downloads/).  This script was developed under Python 3.10, but any recent version ought to suffice.

You'll also need some extra Python modules installed. The [`requirements.txt`](requirements.txt) file in the same directory as the script lists these modules, and can be used to help install them - from a command prompt in the same directory as the script, type: `pip3 install -r requirements.txt`  (If you're on Linux or MacOS, you may need to type `sudo pip3 install -r requirements.txt` instead.)


# Running the script

The script understands many command line options - run the script with the `--help` flag for a list.  All of them are optional.  (Assuming no new UK-reporting US ETFs have come along since the last update of the script's accompanying data files, simply running the script without any options should work.)

The script can output a CSV file using the `-C`/`--csv-output` option, and/or a MediaWiki-format file using the `-w`/`--wiki-output` option.  If neither of these options are given, the script will simply dump MediaWiki-format output to stdout.

The script takes input from four sources, in order:

  * The HMRC reporting funds list
    * The script downloads from the HMRC website, and uses [openpyxl](https://openpyxl.readthedocs.io/en/stable/) to parse, a large Microsoft Excel spreadsheet listing all UK-reporting funds in the world, paying attention only to those rows with valid/plausible [CUSIP](https://en.wikipedia.org/wiki/CUSIP)s or US [ISIN](https://en.wikipedia.org/wiki/International_Securities_Identification_Number)s.
    * As the file name/URL of this spreadsheet changes on a monthly basis, the script first uses [mechanize](https://mechanize.readthedocs.io/en/latest/) to load and parse the web page on which the download link to this spreadsheet is found - the address of this page is stable over time and is hard-coded in the script (but can be overridden using the `-p`/`--hmrc-page` option).
    * The script will locally save the HMRC spreadsheet to a file if you specify the `-s`/`--hmrc-sheet` option, and avoid downloading the spreadsheet again if the local file exists and is newer than the one on the website.  Using the `-S`/`--no-download-hmrc-sheet` option, you can also suppress any attempt to download the spreadsheet again and just use the local version instead.
    * The HMRC sheet is known to contain erroneous data.  This can be overridden using an errata file:
      * By default the errata file is the file [`errata.csv`](errata.csv) in the same directory as the script - the version in the repository contains records to patch all erroneous data currently known to affect US ETFs.  Alternately you can specify a different location using the `-e`/`--errata` option, or avoid using any errata file using the `-E`/`--no-errata-file` option.
      * The errata file is in CSV format, consisting of a header row with header names as in the HMRC spreadsheet, followed by data rows.  (The errata sheet does not need to contain all the columns from the original sheet.) 
      * The "Share Class Ref" column is used as the key to match against rows in the original sheet.
      * Non-blank columns in the errata file override the values in the columns of the original sheet.
    * Note that the HMRC spreadsheet was 7.3 megabytes as of the time of writing, and so may take time to download on your connection; additionally, parsing the sheet and going through each row to find records related to US funds takes several seconds on a modern developer-class machine.  Please be patient when running this.
  * OpenFIGI
    * Every record in the HMRC sheet we're interested in contains an ISIN, and/or a CUSIP (which is easily convertible to an ISIN).  For all the ISINs we have to hand, the script calls Bloomberg's publicly accessible [OpenFIGI API](https://www.openfigi.com/api) to see if there exists a US ETF corresponding to that ISIN, and if so what its ticker symbol is.
    * As of this writing the script needs to perform lookups for just over 500 ISINs.  Given the [rate and batch size limits](https://www.openfigi.com/api#rate-limit) which apply to public users of the OpenFIGI API, this takes dozens of separate HTTP calls spread out over a span of just over two minutes.  Again, please be patient (and possibly use the `-v`/`--verbose` option for more progress messages should this be an issue).
    * OpenFIGI call results can be cached to a local JSON file using the `-k`/`--openfigi-cache` option, with online lookups performed only for ISINs not in the cache.  Please don't use this to cache data over the long term, though - fund tickers can and do change, and funds listed in the HMRC sheet may stop trading (and therefore get removed from OpenFIGI), so getting fresh data from OpenFIGI for each new preparation of the list is essential.
  * A list of fund categories
    * In the wiki output, this script groups funds into categories.  These are specified using a CSV file with a header row and two data columns: one for a fund's ISIN and one for the category the fund belongs in.  (You can also use this file to suppress funds from appearing in the wiki output, by giving them a blank category.)
    * By default the categories file used is the file [`fund-categories.csv`](fund-categories.csv) in the same directory as the script; the version of this file in the repository contains an entry for every UK-reporting US ETF known as of this writing, with funds assigned to broad categories by asset class and US/non-US geography, and "non-Bogleheady" funds such as sector funds, active funds, etc. excluded.
    * If the script encounters any ETFs not listed in the categories file, it will exit with an error, unless the `-N`/`--no-die-on-uncategorized-funds` flag is given.  (This ensures that all new funds are manually reviewed to determine whether they should appear in the desired output and if so what category they should have - as far as I know ETF category data is not freely avaliable without resorting to web scraping techniques of questionable ethics/legality.)
  * A list of fund families
    * The HMRC data file contains a column called "Parent Fund Name", which contains something like the fund family name, and another column called "Sub Fund Name", which contains something like the individual ETF name.  Problem is, the parenet fund name is generally the name of a legal entity (like "Vanguard Charlotte Funds"), of which there may be several per fund company, rather than simply a fund brand name most people would recognize (for example, "Vanguard").  Additionally, the sub fund name may have additional rubbish at the beginning (repeating the fund family name) or the end (the name of a share class).
    * To aid in cleaning up this data, we use a list of fund family names - these are read from a text file, one per line.  If a parent fund name begins with one of the fund family names from this file, we use the corresponding entry from the fund family names file as the fund family name, rather than the (usually longer) legal entity name from the HMRC sheet.  This is then helps to drive the rules which clean up the individual fund name (if the fund name begins with the fund family name, it is removed).
    * By default the fund families list used is [`fund-families.txt`](fund-families.txt) in the same directory as the script; the version of this file in the repository contains an entry for all US ETF fund families which as of this writing have UK-reporting ETFs. 


# More info

A discussion thread about this script will be created shortly in the [Bogleheads Non-US Investing forum](https://www.bogleheads.org/forum/viewforum.php?f=22).

