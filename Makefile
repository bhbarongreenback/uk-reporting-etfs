
HMRC_SHEET_URL = https://www.gov.uk/government/publications/offshore-funds-list-of-reporting-funds

SED            ?= sed
WGET           ?= wget
DIFF           ?= diff
PYTHON3        ?= python3
SSCONVERT      ?= ssconvert

DIFF_OPTS      ?= -abi
VERBOSITY      ?= -v
OPENFIGI_OPTS  ?= 

HAVE_SSCONVERT := $(shell command -v $(SSCONVERT) 2>/dev/null)
HAVE_DIFF      := $(shell command -v $(DIFF) 2>/dev/null)

SHEET_EXT      = $(shell $(SED) -e 's/^.*\.//' < build/hmrc-data-url.txt)


all: build/wiki-main.txt build/wiki-secondary.txt diff

build:
	mkdir -p build

build/hmrc-data-page.html: build
	@echo
	###
	### fetching HMRC data page
	###
	$(WGET) -O $@ "$(HMRC_SHEET_URL)"

build/hmrc-data-url.txt: build/hmrc-data-page.html
	@echo
	###
	### parsing HMRC data page to get download URL for HMRC data spreadsheet
	###
	$(SED) -nre 's/^.*<a [^<]*href=(["'"'"'])(.*\.(xlsx?|ods))\1.*$$/\2/p' < $< | head -n 1 > $@
	[ -s $@ ] || ( rm $@ ; false )

build/hmrc-raw-data.bin: build/hmrc-data-url.txt
	@echo
	###
	### downloading latest HMRC data spreadsheet
	###
	$(WGET) -O $@ $(file <build/hmrc-data-url.txt)
	( cd build ; ln -fs hmrc-raw-data.bin hmrc-raw-data.$(SHEET_EXT) )

build/hmrc-raw-data.csv: build/hmrc-raw-data.bin build/hmrc-data-url.txt bin/convert-sheet.py
	@echo
	###
	### converting HMRC data spreadsheet to CSV
	###
ifdef HAVE_SSCONVERT
	$(SSCONVERT) build/hmrc-raw-data.$(SHEET_EXT) $@
else
	$(PYTHON3) bin/convert-sheet.py $(VERBOSITY) build/hmrc-raw-data.$(SHEET_EXT) $@
endif

build/hmrc-data.csv: build/hmrc-raw-data.csv data/errata.csv bin/filter-hmrc-sheet.py
	@echo
	###
	### filtering HMRC sheet and applying errata
	###
	$(PYTHON3) bin/filter-hmrc-sheet.py $(VERBOSITY) -o $@ build/hmrc-raw-data.csv data/errata.csv

build/openfigi-data.csv: build/hmrc-data.csv bin/call-openfigi.py
	@echo
	###
	### getting data from OpenFIGI for all ISINs in HMRC sheet
	###
	$(PYTHON3) bin/call-openfigi.py $(VERBOSITY) $(OPENFIGI_OPTS) -c -o $@ build/hmrc-data.csv

build/uncategorized-funds.csv: data/fund-categories.csv build
	@echo
	###
	### generating "uncategorized funds" list
	###
	$(SED) -r '/.........,/{s/,$$/,,/;s/,[^,]+$$/,/;s/,,$$/,Excluded funds/}' < $< > $@
	[ -s $@ ] || ( rm $@ ; false )

build/results-main.csv: build/hmrc-data.csv build/openfigi-data.csv data/fund-categories.csv data/fund-families.txt bin/generate-results.py
	@echo
	###
	### generating results CSV for main list
	###
	$(PYTHON3) bin/generate-results.py $(VERBOSITY) -o $@ -i build/hmrc-data.csv -g build/openfigi-data.csv -c data/fund-categories.csv -f data/fund-families.txt

build/results-secondary.csv: build/hmrc-data.csv build/openfigi-data.csv build/uncategorized-funds.csv data/fund-families.txt bin/generate-results.py
	@echo
	###
	### generating results CSV for secondary list
	###
	$(PYTHON3) bin/generate-results.py $(VERBOSITY) -o $@ -i build/hmrc-data.csv -g build/openfigi-data.csv -c build/uncategorized-funds.csv -f data/fund-families.txt

build/wiki-main.txt: build/results-main.csv bin/results-to-wikitext.py
	@echo
	###
	### generating wikitext for main-list article
	###
	$(PYTHON3) bin/results-to-wikitext.py $(VERBOSITY) -o $@ $<

build/wiki-secondary.txt: build/results-secondary.csv bin/results-to-wikitext.py
	@echo
	###
	### generating wikitext for secondary-list article
	###
	$(PYTHON3) bin/results-to-wikitext.py $(VERBOSITY) -o $@ $<

OLD_MAIN      = $(shell ls -t build/wiki-main.txt.OLD-* 2>/dev/null | head -n 1)
OLD_SECONDARY = $(shell ls -t build/wiki-secondary.txt.OLD-* 2>/dev/null | head -n 1)
diff: build/wiki-main.txt build/wiki-secondary.txt
	@echo
ifdef HAVE_DIFF
	@ if [ x != "x$(OLD_MAIN)" ] ; then \
		printf '###\n### main wikitext - difference with old version\n###\n' ; \
		$(DIFF) $(DIFF_OPTS) $(OLD_MAIN) build/wiki-main.txt ; \
		echo; \
	fi
	@ if [ x != "x$(OLD_SECONDARY)" ] ; then \
		printf '###\n### secondary wikitext - difference with old version\n###\n' ; \
		$(DIFF) $(DIFF_OPTS) $(OLD_SECONDARY) build/wiki-secondary.txt ; \
		echo; \
	fi
else
	@ true
endif

clean:
	# removing old intermediate files
	rm -vf build/hmrc-* build/openfigi-* build/uncategorized-*
	# moving old output files out of the way
	for FILE in build/wiki-main.txt build/wiki-secondary.txt ; do \
		if [ -e $$FILE ] ; then \
			mv -v $$FILE $$FILE.OLD-$$(stat -c %y $$FILE | $(SED) -e 's/:[0-9][0-9]\..*$$//;s/[^0-9]//g') ; \
		fi ; \
	done
distclean:
	rm -vf build/*


.PHONY: all diff clean distclean


