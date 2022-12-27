#!/usr/bin/env bash

#
#  Script I use to generate not only the "main" list of ETFs,
#  but also the "spillover list" of ETFs not in the main list:
#
#  https://www.bogleheads.org/wiki/User:Baron_greenback/UK-reporting_US_ETFs_not_included_in_the_main_listing
#

set -e

HMRC_SHEET_CACHE=hmrc_sheet.xlsm
OPENFIGI_CACHE=openfigi.json

# only delete cache files if older than 60 minutes
find ${HMRC_SHEET_CACHE} ${OPENFIGI_CACHE} -mmin +60 -delete

# generate the main list of funds, saving the HMRC sheet and
# OpenFIGI query results to local cache files
./generate-etfs-list.py \
	--verbose \
	--hmrc-sheet=${HMRC_SHEET_CACHE} \
	--openfigi-cache=${OPENFIGI_CACHE} \
	-w wiki.txt

# generate an "inverse categories file" containing only
# the funds excluded from the main list
TMP_CATEGORIES=/tmp/fund-categories-$$.csv
rm -f ${TMP_CATEGORIES}
perl -pe 's/^([^,]+),?(\s*?)$/\1,Miscellaneous\2/;s/,(?!Misc)(?!Category).*?(\s*$)/,\1/' \
	< fund-categories.csv > ${TMP_FUND_CATEGORIES}

# generate the "spillover list" of funds not in the main list,
# using the cache files to avoid repeating major HTTP calls 
./generate-etfs-list.py \
	--verbose \
	--hmrc-sheet=${HMRC_SHEET_CACHE} \
	--openfigi-cache=${OPENFIGI_CACHE} \
	-c ${TMP_CATEGORIES} \
	-w wiki-misc.txt

rm -f ${TMP_CATEGORIES}
