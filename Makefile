
HMRC_SHEET_URL = https://www.gov.uk/government/publications/offshore-funds-list-of-reporting-funds

SED            ?= sed
WGET           ?= wget
DIFF           ?= diff
DIFF_OPTS      ?= -abi
PYTHON3        ?= python3
SSCONVERT      ?= ssconvert

HAVE_SSCONVERT := $(shell command -v $(SSCONVERT) 2>/dev/null)
HAVE_DIFF      := $(shell command -v $(DIFF) 2>/dev/null)

SHEET_EXT      = $(shell $(SED) -e 's/^.*\.//' < build/hmrc-data-url.txt)


all: build/wiki-main.txt build/wiki-secondary.txt diff

build:
	mkdir -p build

build/hmrc-data-page.html: build
	###
	### fetching HMRC data page
	###
	$(WGET) -O $@ "$(HMRC_SHEET_URL)"

build/hmrc-data-url.txt: build/hmrc-data-page.html
	###
	### parsing HMRC data page to get download URL for HMRC data spreadsheet
	###
	$(SED) -nre 's/^.*<a [^<]*href=(["'"'"'])(.*\.(xlsx?|ods))\1.*$$/\2/p' < $< | head -n 1 > $@
	[ -s $@ ] || ( rm $@ ; false )

build/hmrc-raw-data.bin: build/hmrc-data-url.txt
	###
	### downloading latest HMRC data spreadsheet
	###
	$(WGET) -O $@ $(file <build/hmrc-data-url.txt)
	( cd build ; ln -fs hmrc-raw-data.bin hmrc-raw-data.$(SHEET_EXT) )

build/hmrc-raw-data.csv: build/hmrc-raw-data.bin build/hmrc-data-url.txt bin/convert-sheet.py
	###
	### converting HMRC data spreadsheet to CSV
	###
ifdef HAVE_SSCONVERT
	$(SSCONVERT) build/hmrc-raw-data.$(SHEET_EXT) $@
else
	$(PYTHON3) bin/convert-sheet.py -v build/hmrc-raw-data.$(SHEET_EXT) $@
endif

build/hmrc-data.csv: build/hmrc-raw-data.csv data/errata.csv bin/filter-hmrc-sheet.py
	###
	### filtering HMRC sheet and applying errata
	###
	$(PYTHON3) bin/filter-hmrc-sheet.py -v -o $@ build/hmrc-raw-data.csv data/errata.csv

build/openfigi-data.json: build/hmrc-data.csv bin/call-openfigi.py
	###
	### getting data from OpenFIGI for all ISINs in HMRC sheet
	###
	$(PYTHON3) bin/call-openfigi.py -v -c -o $@ build/hmrc-data.csv

build/uncategorized-funds.csv: data/fund-categories.csv build
	###
	### generating "uncategorized funds" list
	###
	$(SED) -r '/.........,/{s/,$$/,,/;s/,[^,]+$$/,/;s/,,$$/,Excluded funds/}' < $< > $@
	[ -s $@ ] || ( rm $@ ; false )

build/wiki-main.txt: build/hmrc-data.csv build/openfigi-data.json data/fund-categories.csv data/fund-families.txt bin/generate-wikitext.py
	###
	### generating wikitext for main-list article
	###
	$(PYTHON3) bin/generate-wikitext.py -v -o $@ -i build/hmrc-data.csv -g build/openfigi-data.json -c data/fund-categories.csv -f data/fund-families.txt

build/wiki-secondary.txt: build/hmrc-data.csv build/openfigi-data.json build/uncategorized-funds.csv data/fund-families.txt bin/generate-wikitext.py
	###
	### generating wikitext for secondary-list article
	###
	$(PYTHON3) bin/generate-wikitext.py -v -o $@ -i build/hmrc-data.csv -g build/openfigi-data.json -c build/uncategorized-funds.csv -f data/fund-families.txt

OLD_MAIN      = $(shell ls -t build/wiki-main.txt.OLD-* 2>/dev/null | head -n 1)
OLD_SECONDARY = $(shell ls -t build/wiki-secondary.txt.OLD-* 2>/dev/null | head -n 1)
diff: build/wiki-main.txt build/wiki-secondary.txt
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


