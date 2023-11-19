#!/usr/bin/env python3


'''
Script to automate generation of the Bogleheads US Reporting ETFs list
from the HMRC UK reporting funds spreadsheet.

https://github.com/bhbarongreenback/uk-reporting-etfs
'''



#### imports ####

# standard packages
import argparse, contextlib, csv, dataclasses, datetime, io, \
		itertools, json, logging, os, re, sys, time, urllib

# apt-get install python3-mechanize || pip3 install mechanize
import mechanize



#### globals ####

_LOGGER_ = logging.getLogger(__name__)
'''Python logging facade used by functions in this script.'''

# configurable default values follow...

HMRC_PAGE_URL = 'https://www.gov.uk/government/publications/offshore-funds-list-of-reporting-funds'
'''
Default URL of the page which should be read to find the link to the latest
UK Reporting Funds spreadsheet.
'''

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

DEFAULT_ERRATA_FILE_NAME = 'errata.csv'
'''Default name of the errata file used to correct errors in HMRC data.'''

DEFAULT_FAMILY_FILE_NAME = 'fund-families.txt'
'''Default name of the file containing fund family names.'''

DEFAULT_CATEGORY_FILE_NAME = 'fund-categories.csv'
'''Default name of the file containing fund family names.'''



#### classes/functions ####

def path_in_same_dir_as_script(filename):
	return os.path.join(os.path.dirname(__file__), filename)


def verify_file_exists(filename):
	if not os.path.isfile(filename):
		raise Exception('file does not exist: ' + filename)
	return filename


def parse_arguments():
	parser = argparse.ArgumentParser(
		description='Fetches the list of HMRC UK Reporting Funds, ' +
			'corroborates it with other data sources, and outputs ' + 
			'a list of UK-reporting US ETFs')
	parser.add_argument('-p', '--hmrc-page',
		metavar='URL', type=str, default=HMRC_PAGE_URL,
		help='HMRC page is located at URL (default: %s)' % HMRC_PAGE_URL)
	parser.add_argument('-s', '--hmrc-sheet',
		metavar='FILE', type=str,
		help='Local cache copy of HMRC spreadsheet to reside at FILE')
	parser.add_argument('-S', '--no-download-hmrc-sheet',
		action='store_true',
		help='Always use the local copy of the HMRC spreadsheet ' +
			'instead of attempting to download it (requires -s)')
	parser.add_argument('-e', '--errata',
		metavar='FILE', type=verify_file_exists,
		default=path_in_same_dir_as_script(DEFAULT_ERRATA_FILE_NAME),
		help='Override HMRC spreadsheet contents with errata file at FILE ' +
			'(default: use %s in same directory as script if it exists)' %
			DEFAULT_ERRATA_FILE_NAME)
	parser.add_argument('-E', '--no-errata-file',
		action='store_true',
		help='Don\'t use an errata file')
	parser.add_argument('-k', '--openfigi-cache',
		metavar='FILE', type=str,
		help='Cache OpenFIGI results in FILE')
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
	parser.add_argument('-K', '--no-call-openfigi',
		action='store_true',
		help='Use the OpenFIGI cache file only and don\'t attempt ' +
			'to call the OpenFIGI API (requires -k)')
	parser.add_argument('-f', '--families',
		metavar='FILE', type=verify_file_exists,
		default=path_in_same_dir_as_script(DEFAULT_FAMILY_FILE_NAME),
		help='Fund family mapping data resides in FILE ' +
			'(default: use %s in same directory as script if it exists)' %
			DEFAULT_FAMILY_FILE_NAME)
	parser.add_argument('-c', '--categories',
		metavar='FILE', type=verify_file_exists,
		default=path_in_same_dir_as_script(DEFAULT_CATEGORY_FILE_NAME),
		help='Fund category data resides in FILE ' +
			'(default: use %s in same directory as script if it exists)' %
			DEFAULT_CATEGORY_FILE_NAME)
	parser.add_argument('-C', '--csv-output',
		metavar='FILE', type=str,
		help='Write CSV output to FILE')
	parser.add_argument('-w', '--wiki-output',
		metavar='FILE', type=str,
		help='Write MediaWiki output to FILE')
	parser.add_argument('-N', '--no-die-on-uncategorized-funds',
		action='store_true',
		help='Don\'t exit with an error message if any ETFs are found ' +
			'which haven\'t yet been categorized')
	parser.add_argument('-v', '--verbose', action='count',
		help='Increase logging amount (repeat for even more logging)')
	parser.add_argument('-q', '--quiet', action='count',
		help='Decrease logging amount (repeat for even less logging)')
	parser.add_argument('-L', '--log-file', metavar='FILE', type=str,
		help='Log to FILE and not to stdout')
	result = parser.parse_args()
	if result.no_download_hmrc_sheet and not result.hmrc_sheet:
		raise Exception('cannot specify -S option without also specifying -s')
	if result.no_call_openfigi and not result.openfigi_cache:
		raise Exception('cannot specify -K option without also specifying -k')
	# TODO: more validations?
	return result


def configure_logger(quiet, verbose, log_file):
	log_level = logging.WARNING + 10 * ((quiet or 0) - (verbose or 0))
	logging.basicConfig(filename=log_file, level=log_level,
		format='%(asctime)s %(message)s')


def column_matching(row, pattern, flags=re.IGNORECASE):
	'''
	Given a header row from a spreadsheet, return the index
	of the column whose value matches the given regex pattern
	(or None if no such value is found).
	'''
	return next((i for i, x in enumerate(row) if x is not None and re.search(pattern, x, flags)), None)


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


def read_errata_file(errata_filename, dont_read_errata_file):
	result = dict()
	if dont_read_errata_file:
		_LOGGER_.info('not reading errata file')
	elif not os.path.isfile(errata_filename):
		_LOGGER_.warning('errata file %s not present' % errata_filename)
	else:
		_LOGGER_.info('reading errata from %s' % errata_filename)
		with open(errata_filename,'r') as f:
			csv_in = csv.reader(f)
			header_row = next(csv_in)
			ref_column = column_matching(header_row, r'\bshare\s+class\s+ref')
			if ref_column is None:
				raise Exception('errata file needs a "Share Class Ref" column')
			parent_column = column_matching(header_row, r'\bparent\s+fund\b')
			sub_column = column_matching(header_row, r'\bsub\W+fund\b')
			isin_column = column_matching(header_row, r'\bISIN\b')
			cusip_column = column_matching(header_row, r'\bCUSIP\b')
			from_column = column_matching(header_row, r'\bwith\s+effect\s+from\b')
			to_column = column_matching(header_row, r'\bceased\b')
			_LOGGER_.debug(('errata file columns: ref=%r, parent=%r, sub=%r, ' + 
				'isin=%r, cusip=%r, from_date=%r, to_date=%r)') % 
				(ref_column, parent_column, sub_column, isin_column,
					cusip_column, from_column, to_column))
			for row in csv_in:
				share_class_ref = row[ref_column] if (ref_column is not None) else None
				if not share_class_ref:
					continue
				result[share_class_ref] = FundInfo(
					family = row[parent_column] if (parent_column is not None) else None,
					fund_name = row[sub_column] if (sub_column is not None) else None,
					isin = row[isin_column] if (isin_column is not None) else None,
					cusip = row[cusip_column] if (cusip_column is not None) else None,
					from_date = row[from_column] if (from_column is not None) else None,
					to_date = row[to_column] if (to_column is not None) else None)
			_LOGGER_.info('errata rows read: %d' % len(result))
	return result


def get_hmrc_spreadsheet_url(hmrc_page_url):
	'''
	Load and parse a page from the HMRC website to get the URL of the
	current spreadsheet of UK reporting funds.  (This is presumed to be
	the first link on the page with a URL having an .xlsm, .xlsx or .ods
	extension.)
	'''
	with contextlib.closing(mechanize.Browser()) as br:
		br.open(hmrc_page_url)
		return br.find_link(url_regex=re.compile('''\.(?:xls[mx]|ods)$''')).url


def is_blank(x):
	return x is None or not x.strip()


def read_hmrc_sheet(hmrc_sheet, no_download_hmrc_sheet, hmrc_page):
	'''
	Read in the HMRC UK Reporting Funds spreadsheet - either by reading
	a local or cached copy from disk, or by downloading it from the
	HMRC website (after parsing a web page to get its URL).
	'''
	if no_download_hmrc_sheet:
		_LOGGER_.info('reading HMRC spreadsheet from file %s' % hmrc_sheet)
		with open(hmrc_sheet,'rb') as f:
			return (None, hmrc_sheet)
	else:
		_LOGGER_.info('reading HMRC webpage from %s' % hmrc_page)
		hmrc_sheet_url = get_hmrc_spreadsheet_url(hmrc_page)
		headers = dict()
		if hmrc_sheet and os.path.exists(hmrc_sheet):
			headers['If-Modified-Since'] = time.strftime(
				'%a, %d %b %Y %H:%M:%S GMT', 
				time.gmtime(os.path.getmtime(hmrc_sheet)))
		_LOGGER_.info('downloading HMRC spreadsheet from %s' % hmrc_sheet_url)
		try:
			with contextlib.closing(urllib.request.urlopen(
					urllib.request.Request(hmrc_sheet_url, headers=headers))) as response:
				hmrc_sheet_raw = response.read()
				if hmrc_sheet:
					_LOGGER_.info('saving cached spreadsheet to %s' % hmrc_sheet)
					with open(hmrc_sheet,'wb') as f:
						f.write(hmrc_sheet_raw)
					return (None, hmrc_sheet)
				else:
					# TODO: broken for ODS - bug in odfpy?
					return (io.BytesIO(hmrc_sheet_raw), hmrc_sheet_url)
		except urllib.error.HTTPError as e:
			if e.code == 304 and hmrc_sheet:
				_LOGGER_.info('using cached spreadsheet at %s' % hmrc_sheet)
				with open(hmrc_sheet,'rb') as f:
					return (None, hmrc_sheet)
			raise e


def cusip_char_value(c, is_odd):
	# https://en.wikipedia.org/wiki/CUSIP#Check_digit_lookup_table
	if c == '0':
		return 0
	elif c in ('J', 'S'):
		return 0 if is_odd else 1
	elif c in ('1', 'A'):
		return 1 if is_odd else 2
	elif c == 'T':
		return 1 if is_odd else 3
	elif c in ('2', 'B', 'K'):
		return 2 if is_odd else 4
	elif c in ('3', 'C', 'L', 'U'):
		return 3 if is_odd else 6
	elif c in ('4', 'D', 'M', 'V'):
		return 4 if is_odd else 8
	elif c in ('E', 'N', 'W'):
		return 5 if is_odd else 0
	elif c == '5':
		return 5 if is_odd else 1
	elif c in ('O', 'X'):
		return 6 if is_odd else 2
	elif c in ('6', 'F'):
		return 6 if is_odd else 3
	elif c == 'Y':
		return 7 if is_odd else 4
	elif c in ('7', 'G', 'P'):
		return 7 if is_odd else 5
	elif c in ('8', 'H', 'Q', 'Z'):
		return 8 if is_odd else 7
	elif c in ('9', 'I', 'R'):
		return 9
	raise Exception('unknown character: ' + c)


def cusip_check_digit(s):
	'''
	Given the first eight characters of a CUSIP, calculate
	the check digit we'd expect to see as the ninth character.
	'''
	x = sum(cusip_char_value(c, i%2==0) for i, c in enumerate(s))
	return str((10 - (x % 10)) % 10)


def isin_check_digit(s):
	'''
	Given the first eleven characters of an ISIN, calculate
	the check digit we'd expect to see as the twelfth character.
	'''
	s = re.sub('[A-Z]', lambda m: str(ord(m.group(0))-55), s)
	odds  = ''.join(c for i,c in enumerate(s) if i%2==0)
	evens = ''.join(c for i,c in enumerate(s) if i%2==1)
	if len(evens) == len(odds):
		evens = re.sub('\d', lambda m: str(int(m.group(0))*2), evens)
	else:
		odds = re.sub('\d', lambda m: str(int(m.group(0))*2), odds)
	x = sum(int(c) for c in (evens + odds))
	return str((10 - (x % 10)) % 10)


def sheet_to_fund_info(hmrc_sheet, errata):
	'''
	Given rows from the HMRC worksheet, return a FundInfo object
	for each "interesting-looking" row in the sheet (i.e. those having
	a valid CUSIP and/or US ISIN), applying any corrections from the
	errata before performing any processing.
	'''
	_LOGGER_.info('start processsing HMRC spreadsheet contents')
	parent_column = sub_column = isin_column = cusip_column = from_column = to_column = ref_column = None
	fund_count = 0
	for row in hmrc_sheet:
		# If we haven't encountered the header row yet, try to match it -
		# in the process figuring out which column each of the data items is in
		if parent_column is None or sub_column is None \
				or isin_column is None or cusip_column is None \
				or from_column is None or to_column is None \
				or ref_column is None:
			parent_column = column_matching(row, r'\bparent\s+fund\b')
			sub_column = column_matching(row, r'\bsub\W+fund\b')
			isin_column = column_matching(row, r'\bISIN\b')
			cusip_column = column_matching(row, r'\bCUSIP\b')
			from_column = column_matching(row, r'\bwith\s+effect\s+from\b')
			to_column = column_matching(row, r'\bceased\b')
			ref_column = column_matching(row, r'\bshare\s+class\s+ref')
			continue

		# Get data values from the various columns
		family = row[parent_column] if len(row) > parent_column else None
		fund_name = row[sub_column] if len(row) > sub_column else None
		isin = row[isin_column] if len(row) > isin_column else None
		cusip = row[cusip_column] if len(row) > cusip_column else None
		from_date = row[from_column] if len(row) > from_column else None
		to_date = row[to_column] if len(row) > to_column else None
		share_class_ref = row[ref_column] if len(row) > ref_column else None
		# If the fund is mentioned in the errata file, override data in
		# the HMRC sheet with any non-blank values from the errata file
		if share_class_ref in errata:
			erratum = errata[share_class_ref]
			family = erratum.family if erratum.family else family
			fund_name = erratum.fund_name if erratum.fund_name else fund_name
			isin = erratum.isin if erratum.isin else isin
			cusip = erratum.cusip if erratum.cusip else cusip
			from_date = erratum.from_date if erratum.from_date else from_date
			to_date = erratum.to_date if erratum.to_date else to_date
		# Parse data into a FundInfo object...
		fund = FundInfo(
				family = family,
				fund_name = fund_name,
				isin = isin,
				cusip = cusip,
				from_date = from_date,
				to_date = to_date,
				share_class_ref = share_class_ref,
				ticker = None
			)
		# ...then perform various data checks/cleanups:
		if fund.cusip is not None:
			fund.cusip = re.sub(r'[^0-9A-Z]+', '', fund.cusip.strip().upper())
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
			fund.isin = re.sub(r'[^0-9A-Z]+', '', fund.isin.strip().upper())
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
		if fund.to_date:
			# fund has a date where it ceased to be a UK reporting fund - row doesn't interest us then
			continue
		yield fund
		fund_count += 1
	_LOGGER_.info('finish processsing HMRC spreadsheet contents (%d candidates found)' % fund_count)


def odfpy_cell_to_text(cell):
	# thanks, https://github.com/marcoconti83/read-ods-with-odfpy/blob/master/ODSReader.py#L63
	import odf.text
	ps = cell.getElementsByType(odf.text.P)
	text_content = ""
	for p in ps:
		for n in p.childNodes:
			if (n.nodeType == 1 and ((n.tagName == "text:span") or (n.tagName == "text:a"))):
				for c in n.childNodes:
					if (c.nodeType == 3):
						text_content = u'{}{}'.format(text_content, c.data)
			if (n.nodeType == 3):
				text_content = u'{}{}'.format(text_content, n.data)
	return text_content.strip() if re.search(r'\w', text_content) else ''


def parse_hmrc_sheet(hmrc_sheet_raw, filename):
	'''
	Given a file-like object from which we can read the HMRC data file,
	generate a series of rows from the first sheet in the workbook.
	'''
	if re.match(r'^(?:.*/)?[^/]+\.xls[mx](?:\b[^/]+)?$', filename):
		# apt-get install python3-openpyxl || pip3 install openpyxl
		import openpyxl
		_LOGGER_.info('start parsing HMRC spreadsheet (using openpyxl)')
		with contextlib.closing(openpyxl.load_workbook(filename=(filename or hmrc_sheet_raw), read_only=True)) as wb:
			_LOGGER_.info('finish parsing HMRC spreadsheet')
			for row in wb.worksheets[0]:
				yield list(map(lambda x: x.value, row))
	elif re.match(r'^(?:.*/)?[^/]+\.ods(?:\b[^/]+)?$', filename):
		# apt-get install python3-odf || pip3 install odfpy
		import odf.opendocument, odf.table
		_LOGGER_.info('start parsing HMRC spreadsheet (using odfpy)')
		doc = odf.opendocument.load(filename)
		_LOGGER_.info('finish parsing HMRC spreadsheet')
		tbl = doc.spreadsheet.getElementsByType(odf.table.Table)[0]
		for row in tbl.getElementsByType(odf.table.TableRow):
			yield list(map(odfpy_cell_to_text, row.getElementsByType(odf.table.TableCell)))
	else:
		raise Exception('cannot determine file format from filename: ' + filename)


def make_isin_from_cusip(cusip):
	'''
	Given a CUSIP, return the corresponding ISIN (which is just the
	CUSIP with "US" prepended to the front and a check digit appended
	at the end).
	'''
	return 'US' + cusip + isin_check_digit('US' + cusip)


def isins_for_funds(funds, cache):
	'''
	Generator function which, given a series of FundInfo objects,
	iterates over the unique ISINs we'll want to query from OpenFIGI.
	'''
	seen = set(cache.keys())
	for fund in funds:
		if fund.isin and fund.isin not in seen:
			seen.add(fund.isin)
			yield fund.isin
		if fund.cusip:
			isin_from_cusip = make_isin_from_cusip(fund.cusip)
			if isin_from_cusip != fund.isin and isin_from_cusip not in seen:
				seen.add(isin_from_cusip)
				yield isin_from_cusip


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
def call_openfigi(jobs, openfigi_url, openfigi_api_key):
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
		raise Exception('Bad response code {}'.format(str(response.status_code)))
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


def get_openfigi_results(funds,
		openfigi_cache,
		openfigi_calls_per_minute,
		openfigi_jobs_per_call,
		openfigi_url,
		openfigi_api_key,
		no_call_openfigi):
	'''
	Given a list of FundInfo objects, return a dictionary of ISINs to
	OpenFIGI results representing everything we can find out from the
	OpenFIGI API and/or the local OpenFIGI cache about any ETFs related
	to those FundInfo objects.
	'''
	if openfigi_cache and os.path.exists(openfigi_cache):
		_LOGGER_.info('loading OpenFIGI cache from %s' % openfigi_cache)
		with open(openfigi_cache,'r') as f:
			cache = json.load(f)
		if no_call_openfigi:
			_LOGGER_.debug('not calling OpenFIGI API as per options')
			return cache
	else:
		cache = dict()
	jobs_per_call = openfigi_jobs_per_call or \
		(OPENFIGI_JOBS_PER_CALL_WITH_KEY if openfigi_api_key
			else OPENFIGI_JOBS_PER_CALL_WITHOUT_KEY)
	calls_per_minute = openfigi_calls_per_minute or \
		(OPENFIGI_CALLS_PER_MINUTE_WITH_KEY if openfigi_api_key
			else OPENFIGI_CALLS_PER_MINUTE_WITHOUT_KEY)
	openfigi_url = openfigi_url or OPENFIGI_ENDPOINT_URL
	isins_to_query = tuple(isins_for_funds(funds, cache))
	if not isins_to_query:
		_LOGGER_.info('not querying OpenFIGI (no ISINs we need to query)')
		return cache
	_LOGGER_.info('start querying OpenFIGI (%d ISINs to query)' % 
			len(isins_to_query))
	isins_to_query_with_progress = progress_reporting_iterator(
			isins_to_query, max(50, jobs_per_call),
			'%d ISINs queried')
	openfigi_jobs_grouped = group_into_sublists(
			map(isin_to_openfigi_job, isins_to_query_with_progress),
			jobs_per_call)
	openfigi_results_grouped = map(
			lambda x: call_openfigi(x, openfigi_url, openfigi_api_key), 
			rate_limit(openfigi_jobs_grouped, calls_per_minute*0.95))
	openfigi_results = map(get_best_openfigi_result,
			itertools.chain.from_iterable(openfigi_results_grouped))
	isin_to_openfigi_result = dict(zip(isins_to_query, openfigi_results))
	_LOGGER_.info('finished querying OpenFIGI (%d results returned)' % 
			len(isin_to_openfigi_result))
	cache |= isin_to_openfigi_result
	if openfigi_cache:
		_LOGGER_.info('writing OpenFIGI cache to %s' % openfigi_cache)
		with open(openfigi_cache,'w') as f:
			json.dump(cache, f, indent=4)
	return cache


def read_families_file(families_filename):
	'''
	Read in the fund families file (which currently is just a plain text
	file consisting of one fund family name per line.)  Returns a tuple
	containing all family names.
	'''
	_LOGGER_.info('reading fund families from %s' % families_filename)
	result = list()
	with open(families_filename,'r') as f:
		for line in f:
			line = line.strip()
			if line:
				result.append(line)
	_LOGGER_.info('%d fund familes read' % len(result))
	return tuple(result)


def read_categories_file(categories_filename):
	'''
	Read in the fund categories file (a CSV file consisting of a header
	row telling which is the CUSIP column and which is the category column,
	followed by data rows).  Returns a dictionary of CUSIPs to categories.
	'''
	_LOGGER_.info('reading fund categories from %s' % categories_filename)
	result = dict()
	with open(categories_filename,'r') as f:
		csv_in = csv.reader(f)
		header_row = next(csv_in)
		cusip_column = column_matching(header_row, r'\bCUSIP\b')
		category_column = column_matching(header_row, r'\bcategory\b')
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


def result_for_fundinfo(fund, isin_to_openfigi_result):
	'''
	Given a FundInfo object and a dictionary of ISINs to OpenFIGI
	result objects, return the relevant OpenFIGI result object
	based on either the ISIN or the CUSIP (or None if no relevant
	result exists).
	'''
	if fund.isin and isin_to_openfigi_result.get(fund.isin, None) is not None:
		return (fund.isin, isin_to_openfigi_result[fund.isin])
	elif fund.cusip:
		cusip_isin = make_isin_from_cusip(fund.cusip)
		if isin_to_openfigi_result.get(cusip_isin, None) is not None:
			return (cusip_isin, isin_to_openfigi_result[cusip_isin])
	return (None, None)


def enhance_fund_data(funds, isin_to_openfigi_result, fund_families, 
		fund_categories, no_die_on_uncategorized_funds):
	'''
	Take the FundInfo objects derived from the HMRC sheet and match them
	with ticker data from OpenFIGI and fund categories from the categories
	file; clean up the family and fund names with help from the fund familes
	list; and return a list containing only those funds with known tickers
	and categories.
	'''
	result = list()
	seen_isins = set()
	uncategorized_funds = list()
	family_regex = re.compile(r'^('+'|'.join(map(re.escape, fund_families))+r')\b', re.I)
	trailing_rubbish_regex = re.compile(
		r'\b(\s+-\s*|\s*-\s+)\b(?=.*\b(shares?|class)\b)([^-]+)$', re.I)
	_LOGGER_.info('start enhancing fund data')
	for fund in funds:
		# Determine ticker for the fund...
		(isin, openfigi) = result_for_fundinfo(fund, isin_to_openfigi_result)
		if not openfigi or 'ticker' not in openfigi or isin in seen_isins:
			# ...ignoring the fund if there's no ETF ticker, or it's a
			# duplicate ISIN (sometimes seen in the HMRC data?!)
			continue
		seen_isins.add(isin)
		fund.ticker = openfigi['ticker']
		# ...and ensure the fund has a correct ISIN set, 
		# so we can include it as part of the output
		fund.isin = isin
		# Determine the fund family name from the HMRC "parent fund" data
		# (if parent fund starts with one of the family names from the 
		# fund families file, use the shorter family name instead)
		m = family_regex.match(fund.family)
		if m:
			fund.family = m.group(1)
		# Look up the category of the fund using the CUSIP
		if fund.isin[2:11] not in fund_categories:
			# If the CUSIP doesn't appear in the categories file, add the
			# fund to the list of uncategorized funds, and ignore it
			uncategorized_funds.append(fund)
			continue
		elif not fund_categories[fund.isin[2:11]]:
			# Ignore the fund if CUSIP is in the file but category is blank
			continue
		else:
			fund.category = fund_categories[fund.isin[2:11]]
		# Finally, clean up the fund name following a few rules...
		# Strip the fund family name from the start of the fund name
		fund.fund_name = re.sub('^'+re.escape(fund.family)+r'\s+','',fund.fund_name, re.I)
		# If the fund name ends in a dash with a space immediately before
		# or after it, followed by some words including 'share', 'shares' 
		# or 'class', strip anything after the dash
		fund.fund_name = trailing_rubbish_regex.sub('', fund.fund_name)
		result.append(fund)
	_LOGGER_.info('finished enhancing fund data (%d funds enhanced)' % len(result))
	if uncategorized_funds:
		_LOGGER_.error('%d uncategorzed fund(s) detected: %s' % (
				len(uncategorized_funds),
				', '.join(map(lambda x: "%s (%s)" % (x.ticker, x.isin[2:11]), uncategorized_funds))))
		_LOGGER_.debug('uncategorized fund detail: %r' % uncategorized_funds)
		if not no_die_on_uncategorized_funds:
			sys.exit(1)
	# Sort the funds nicely - by family, then fund name
	result.sort(key=lambda f: f.family.upper() + '    ' + f.fund_name.upper())
	return result


def write_csv_output(funds, csv_filename):
	_LOGGER_.info('writing CSV output to %s' % csv_filename)
	with open(csv_filename,'w') as f:
		csv_out = csv.writer(f)
		csv_out.writerow(['Ticker', 'Family', 'Name', 'ISIN', 
				'Reporting Since', 'Category'])
		for fund in funds:
			csv_out.writerow([
				fund.ticker,
				fund.family,
				fund.fund_name,
				fund.isin,
				fund.from_date,
				fund.category
			])


def write_wiki_output(funds, wiki_filename):
	if wiki_filename:
		_LOGGER_.info('writing MediaWiki output to %s' % wiki_filename)
		with open(wiki_filename,'w') as f:
			write_wiki_output_to_filehandle(funds, f)
	else:
		_LOGGER_.info('writing MediaWiki output to stdout')
		write_wiki_output_to_filehandle(funds, sys.stdout)


def mediawiki_escape(s):
	return re.sub(r'[&<>{}\[\]\\\u007f-\uffff]', lambda m:'&#%d;'%ord(m.group(0)), s)


def reformat_date_from_ddmmyyyy_to_ddmmmyyyy(date_string):
	try:
		return datetime.datetime.strptime(date_string, '%d/%m/%Y').strftime('%d %b %Y')
	except:
		_LOGGER_.debug('couldn\'t reformat date: %s' % date_string)
		return date_string

def write_wiki_output_to_filehandle(funds, f):
	is_first_table = True
	for category in sorted(set(map(lambda f: f.category, funds)), key=str.lower):
		f.write('=== %s ===\n' % mediawiki_escape(category))
		if is_first_table:
			f.write('{{mw-datatable}}\n')
			is_first_table = False
		f.write('{| class="wikitable sortable mw-datatable"\n')
		f.write('! Ticker || Fund Family || Fund Name || CUSIP || HMRC Reporting Since\n')
		for fund in funds:
			if fund.category == category:
				f.write('|-\n| ' + ' || '.join([
					'[https://etf.com/%s %s]' % (fund.ticker, fund.ticker),
					mediawiki_escape(fund.family),
					mediawiki_escape(fund.fund_name),
					'<span title="ISIN: %s">%s</span>' % (fund.isin, fund.isin[2:11]),
					reformat_date_from_ddmmyyyy_to_ddmmmyyyy(fund.from_date)
				]) + '\n')
		f.write('|}\n\n')



#### main ####

if __name__ == '__main__':
	args = parse_arguments()
	configure_logger(args.quiet, args.verbose, args.log_file)
	errata = read_errata_file(args.errata, args.no_errata_file)

	(hmrc_sheet_io, hmrc_sheet_filename) = read_hmrc_sheet(args.hmrc_sheet, 
			args.no_download_hmrc_sheet,
			args.hmrc_page)
	sheet_rows = parse_hmrc_sheet(hmrc_sheet_io, hmrc_sheet_filename)
	fund_info = list(sheet_to_fund_info(sheet_rows, errata))

	isin_to_openfigi_result = get_openfigi_results(fund_info,
			args.openfigi_cache,
			args.openfigi_calls_per_minute,
			args.openfigi_jobs_per_call,
			args.openfigi_endpoint_url,
			args.openfigi_api_key,
			args.no_call_openfigi)
	fund_families = read_families_file(args.families)
	fund_categories = read_categories_file(args.categories)

	result = enhance_fund_data(fund_info, isin_to_openfigi_result, 
			fund_families, fund_categories,
			args.no_die_on_uncategorized_funds)

	if args.csv_output:
		write_csv_output(result, args.csv_output)
	if args.wiki_output or not args.csv_output:
		write_wiki_output(result, args.wiki_output)

