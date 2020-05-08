# REDCap Cloud to CanDIG

This repo contains a collection of scripts and mappings used to create .json output ready to be ingested by CanDIG scripts. The script connects to UCalgary RedCapCloud instance and pulls Profyle patient-related metadata. A Profyle study access token is required.

Requirements: Python3+

Usage:
1) Clone this repo
2) Executing the shellscript by passing your province/token should install the necessary python virtual environment and pull the data to the output directory.
```bash
  ./rcc_candig.sh province_code your_token
```
Example:
```bash
  ./rcc_candig.sh BC abc123
```
