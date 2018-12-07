"""
Usage:
	rcc_candig.py <access_token>

Options:
	-h --help 		Show this screen
	-v --version 	Version
	<access_token>	Your issued RedCapCloud api token  
"""

import requests
import json
from docopt import docopt
import candig_tables as ct

site_list = [1482, 1490, 1485, 1481, 1483]  # BC, Alberta, Sask, Manitoba
# site_list = [1478, 1496, 1489, 1476, 1497, 1477, 1491, 1479, 1484] # Ontario, PEI, NL
# site_list = [1480, 1487, 1486, 1488] # Quebec

def main():
	args = docopt(__doc__, version='0.1')
	access_token = args['<access_token>']

	export_uri = 'https://ucalgary.calogin.redcapcloud.com/rest/v2/export/records/{}'
	singleton_tables = [{"Patient":parse_patient}, {"Enrollment":parse_enrollment}, {"Consent":parse_consent}, 
				  {"Outcome":parse_outcome}, {"Complication": parse_complication}]
	repeating_tables = [{"Tumourboard": parse_tumourboard}, {"Diagnosis":parse_diagnosis}, {"Treatment": parse_treatment}]

	with open('input/rcc_candig_mapping.json') as json_data:
   		template = json.load(json_data)

   	results = {"metadata": []}

	headers = {
		 "accept": "application/json",
		 "token": access_token
	}

	if validate_connection(headers):
		print('>>> Connection to REDCap accepted')
		for site_id in site_list:

			response = requests.Session().get(
				export_uri.format(site_id),	
				headers=headers
			)

			print('Handling response for site {}'.format(site_id))

			if response.status_code == 200:
				print("# Records: "+str(len(response.json())))

				# response process
				sort_response = {}
				for record in response.json():
					patient_id = record.get("participantId")
					if patient_id == "":
						continue
					if patient_id in sort_response:
						sort_response[patient_id].append(record)
					else:
						sort_response[patient_id] = [record]

				for patient_id in sort_response:
					patient_records = sort_response[patient_id]
					patient_obj = {}

					# singleton tables entered as group objects
					for table in singleton_tables:
						parsed_record = table.values()[0](patient_records, template, patient_id)
						if parsed_record:
							patient_obj[table.keys()[0]] = parsed_record
					results["metadata"].append(patient_obj)

					# repeating tables entered as individual objects
					for table in repeating_tables:
						index = 1
						parsed_record = table.values()[0](patient_records, template, patient_id, index)
						while(parsed_record):
							individual_obj = {}
							individual_obj[table.keys()[0]] = parsed_record
							results["metadata"].append(individual_obj)
							index = index + 1
							parsed_record = table.values()[0](patient_records, template, patient_id, index)
			else:
				print_error(response)

		output = 'output/profyle_metadata.json'
		with open(output, 'w') as outfile:
			json.dump(results, outfile)
		print('>>> Output to: {}'.format(output))

	else:
		raise requests.exceptions.ConnectionError


def parse_patient(patient_records, template, patient_id):
	patient_table = ct.patients.copy()
	patient_table["patientId"] = patient_id

	for record in patient_records:
		if record.get("eventName") == "Enrollment":
			return redcap_transform(record, template, patient_table, "patient")
	# at minimum, an empty patient table with id must be returned
	return patient_table

def parse_enrollment(patient_records, template, patient_id):
	enrollment_table = ct.enrollments.copy()
	enrollment_table["patientId"] = patient_id

	for record in patient_records:
		# note, scr has no event name associated when exporting
		if "eventName" not in record:
			return redcap_transform(record, template, enrollment_table, "enrollment")

def parse_consent(patient_records, template, patient_id):
	consent_table = ct.consents.copy()
	consent_table["patientId"] = patient_id

	for record in patient_records:
		if record.get("eventName") == "Enrollment":
			return redcap_transform(record, template, consent_table, "consent")

def parse_diagnosis(patient_records, template, patient_id, index):
	diagnosis_table = ct.diagnoses.copy()
	diagnosis_table["patientId"] = patient_id

	for record in patient_records:
		# Repeating CRF event
		if record.get("eventName") == "Diagnostic Information({})".format(index):
			return redcap_transform(record, template, diagnosis_table, "diagnosis")

def parse_treatment(patient_records, template, patient_id, index):
    treatment_table = ct.treatments.copy()
    treatment_table["patientId"] = patient_id

    for record in patient_records:
    	# Repeating CRF event
		if record.get("eventName") == "Treatment Plan({})".format(index):
			return redcap_transform(record, template, treatment_table, "treatment")

def parse_outcome(patient_records, template, patient_id):
	outcome_table = ct.outcomes.copy()
	outcome_table["patientId"] = patient_id

	for record in patient_records:
		if record.get("eventName") == "Vital Status and Clinical Follow-Up":
			return redcap_transform(record, template, outcome_table, "outcome")

def parse_complication(patient_records, template, patient_id):
	complication_table = ct.complications.copy()
	complication_table["patientId"] = patient_id

	for record in patient_records:
		if record.get("eventName") == "Vital Status and Clinical Follow-Up":
			return redcap_transform(record, template, complication_table, "complication")

def parse_tumourboard(patient_records, template, patient_id, index):
	tumourboard_table = ct.tumourboards.copy()
	tumourboard_table["patientId"] = patient_id

	for record in patient_records:
		# Repeating CRF	event
		if record.get("eventName") == "Molecular Tumour Board({})".format(index):
			return redcap_transform(record, template, tumourboard_table, "tumourboard")


def redcap_transform(record, template, table_dict, table_str):
	for field in template.get(table_str, []):
		table_dict[template[table_str][field]] = record.get(field)
	record_items = record.get("items")

	for record_item in record_items:
		item_value = record_item["itemValue"]
		if item_value == "{null}":
			continue
			
		item_name = record_item["itemName"]
		if "___" in item_name:
			# handles checkboxes in CRF
			item_name = item_name.split("___")[0]

		elif all(x in item_name for x in "()"):
			# handles repeating fields in CRF
			item_name = item_name.split("(")[0]

		elif item_name.startswith("id_") and "id_relat" not in item_name:
			# groups id fields together
			item_name = "id_*"

		if item_name in template[table_str+"_items"]:
			mapped_field = template[table_str+"_items"][item_name]
			if "responseSet" not in record_item:
				table_dict[mapped_field] = item_value
			else:
				response_set = record_item["responseSet"]
				mapped_item_value = [d["optionsText"] for d in response_set["responseSetValues"] if d["value"] == item_value]
				if len(mapped_item_value) > 0:
					if table_dict[mapped_field] == "":
						table_dict[mapped_field] = mapped_item_value[0]
					else:
						if mapped_item_value[0] not in table_dict[mapped_field]:
							table_dict[mapped_field] = table_dict[mapped_field] + ", " + mapped_item_value[0]
	return table_dict

def validate_connection(headers):
	connected = False
	response = requests.Session().get(
		"https://ucalgary.calogin.redcapcloud.com/rest/v2/system/current-study",
		headers=headers
	)
	if response.status_code == 200:
		connected = True
	else:
		print_error(response)
	return connected

def print_error(response):
	print('>>> {0}: {1}\n'.format(response.status_code, response.content))


def get_sites(headers):
	"""
	Returns list of all site ID's that a given token has access to
	"""
	sites_response = requests.Session().get(
		"https://ucalgary.calogin.redcapcloud.com/rest/v2/study/sites",
		headers=headers
	)
	sites_list = []
	if sites_response.status_code == 200:
		for record in sites_response.json():
			if record["enabled"]:
				sites_list.append(record["id"])
	return sites_list

if __name__ == "__main__":
	main()
