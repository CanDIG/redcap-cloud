#!/usr/bin/env bash

# This script will pull data from REDCap cloud, and output a CanDIG ingestible json file
#
# Usage:
#  $ ./rcc_candig.sh <province> <token> 
# * province: provincial alpha code of site requesting data
# * token: issued REDCap Cloud access token
#
if [ ${#@} == 2 ]; then
	if [ ! -d rcc_venv/ ]; then
		echo "No environment detected, initialising..."
		python3 -m venv rcc_venv/
		source rcc_venv/bin/activate
		pip install --upgrade pip
		pip install -U setuptools
		pip install -r requirements.txt
	fi
	source rcc_venv/bin/activate
	python rcc_candig.py $1 $2 && \
	python load_tiers.py clinical output/profyle_metadata.json input/project_tiers.xlsx output/profyle_metadata_tiers.json && \
	# clear intermediate output
	rm output/profyle_metadata.json
	deactivate
else
	echo "Usage: $0 province token"
	echo "* province: provincial alpha code of site requesting data"
    echo "* token: issued REDCap Cloud access token"
fi
