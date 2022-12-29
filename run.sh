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

# move out of the way any old output files,
# and cache files if older than 60 minutes
echo '#### moving old files out of the way'
for i in wiki{,-misc}.txt $(find ${HMRC_SHEET_CACHE} ${OPENFIGI_CACHE} -mmin +60 2>/dev/null)
do
	if [[ -e ${i} ]]
	then
		mv -v ${i} ${i}.$(stat -c %y ${i} | sed -e 's/:[0-9][0-9]\..*$//;s/[^0-9]//g')
	fi
done
echo

# generate the main list of funds, saving the HMRC sheet and
# OpenFIGI query results to local cache files
echo '#### generating main fund list'
./generate-etfs-list.py \
	--verbose \
	--hmrc-sheet=${HMRC_SHEET_CACHE} \
	--openfigi-cache=${OPENFIGI_CACHE} \
	-w wiki.txt
echo

# generate an "inverse categories file" containing only
# the funds excluded from the main list
TMP_CATEGORIES=/tmp/fund-categories-$$.csv
rm -f ${TMP_CATEGORIES}
perl -pe 's/^([^,]+),?(\s*?)$/\1,Miscellaneous\2/;s/,(?!Misc)(?!Category).*?(\s*$)/,\1/' \
	< fund-categories.csv > ${TMP_CATEGORIES}

# generate the "spillover list" of funds not in the main list,
# using the cache files to avoid repeating major HTTP calls 
echo '#### generating spillover fund list'
./generate-etfs-list.py \
	--verbose \
	--hmrc-sheet=${HMRC_SHEET_CACHE} \
	--openfigi-cache=${OPENFIGI_CACHE} \
	-c ${TMP_CATEGORIES} \
	-w wiki-misc.txt
echo

rm -f ${TMP_CATEGORIES}

# print out differences with previous version of output
OLD_MAIN_LIST="$(ls -t wiki.txt.* 2>/dev/null | head -n 1)" 
if [[ -e "${OLD_MAIN_LIST}" ]]
then
	echo '#### main fund list - difference with previous version'
	diff -abi "${OLD_MAIN_LIST}" wiki.txt || true
	echo
fi
OLD_SPILLOVER_LIST="$(ls -t wiki-misc.txt.* 2>/dev/null | head -n 1)"
if [[ -e "${OLD_SPILLOVER_LIST}" ]]
then
	echo '#### spillover fund list - difference with previous version'
	diff -abi "${OLD_SPILLOVER_LIST}" wiki-misc.txt || true
	echo
fi
