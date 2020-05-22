"""
Usage:
    rcc_candig.py <alpha_code> <access_token>

Options:
    -h --help         Show this screen
    -v --version     Version
    <alpha_code>    Internationally approved alpha code (e.g. BC)
    <access_token>    Your issued RedCapCloud api token  
"""

import requests
try:
    import exceptions
except ImportError:
    import builtins as exceptions
import json
from docopt import docopt

with open('input/rcc_candig_mapping.json') as json_data:
    template = json.load(json_data)

def main():
    args = docopt(__doc__, version='0.1')
    alpha_code = args['<alpha_code>']
    access_token = args['<access_token>']

    export_uri = 'https://ucalgary.calogin.redcapcloud.com/rest/v2/export/records/{}'
    singleton_tables = [{"Patient": parse_patient}, {"Enrollment": parse_enrollment}, {"Consent": parse_consent}, 
                  {"Outcome": parse_outcome}, {"Complication": parse_complication}]
    repeating_tables = [{"Tumourboard": parse_tumourboard}, {"Diagnosis": parse_diagnosis}, {"Treatment": parse_treatment}]

    results = {"metadata": []}

    headers = {
         "accept": "application/json",
         "token": access_token
    }

    if validate_connection(headers):
        print('>>> Connection to REDCap accepted')
        site_list = get_sites_for_prov(alpha_code)

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
                    if not patient_id:
                        continue
                    if patient_id in sort_response:
                        sort_response[patient_id].append(record)
                    else:
                        sort_response[patient_id] = [record]

                for patient_id in sort_response:
                    patient_records = sort_response[patient_id]
                    patient_obj = {}

                    # check if the records associated with current patient_id is has the correct consent

                    consent_bool = get_consent(patient_records, patient_id)

                    if consent_bool is False:
                        print(patient_id, "does not have acceptable consents, skipping...")
                        continue
                    else:
                        print(patient_id, "contains valid consents")

                    # singleton tables entered as group objects
                    for table in singleton_tables:
                        parsed_record, sub_tables = list(table.values())[0](patient_records, patient_id)
                        if parsed_record:
                            patient_obj[list(table.keys())[0]] = parsed_record
                    results["metadata"].append(patient_obj)

                    # repeating tables entered as individual objects
                    for table in repeating_tables:
                        index = 1
                        parsed_record, sub_tables = list(table.values())[0](patient_records, patient_id, index)
                        while(parsed_record):
                            results["metadata"].append({list(table.keys())[0]: parsed_record})
                            # attach treatment sub tables
                            if list(table.keys())[0] == "Treatment":
                                for table_name in sub_tables:
                                    for k in sub_tables[table_name]:
                                        results["metadata"].append({table_name: sub_tables[table_name][k]})
                            index = index + 1
                            parsed_record, sub_tables = list(table.values())[0](patient_records, patient_id, index)
            else:
                print_error(response)

        if site_list:
            output = 'output/profyle_metadata.json'
            with open(output, 'w') as outfile:
                json.dump(results, outfile)
            print('>>> Output to: {}'.format(output))
        else:
            raise exceptions.RuntimeError("No sites found. Please check the given provincial alpha code")
    else:
        raise requests.exceptions.ConnectionError


def parse_patient(patient_records, patient_id):
    patient_table = {}
    patient_table["patientId"] = patient_id

    for record in patient_records:
        if record.get("eventName") == "Enrollment":
            return redcap_transform(record, patient_table, "patient")
    # at minimum, an empty patient table with id must be returned
    return patient_table, {}

def parse_enrollment(patient_records, patient_id):
    enrollment_table = {}
    enrollment_table["patientId"] = patient_id

    for record in patient_records:
        # note, scr has no event name associated when exporting
        if "eventName" not in record:
            return redcap_transform(record, enrollment_table, "enrollment")
    return {}, {}

def get_consent(patient_records, patient_id):
    """
    @param patient_records: A list of patient records.
    @param patient_id: The requested patient_id.

    Return True if the records associated with patient_id has acceptable consents.
    Return False otherwise.
    """
    consent_table = {}
    consent_table["patientId"] = patient_id

    for record in patient_records:
        if record.get("eventName") == "Enrollment":
            consent_info = redcap_transform(record, consent_table, "consent_info")

    try:
        temp_cst_info = consent_info[0]
        temp_patient_id = temp_cst_info["patientId"]
    except UnboundLocalError:
        # This indicates that this record does not have consents info
        return False

    if "cst_main_yn" in temp_cst_info:
        if temp_cst_info["cst_main_yn"] == "true":
            if "cst_withd_yn" not in temp_cst_info:
                # True, as no withdrawal info available
                return True
            elif temp_cst_info["cst_withd_yn"] == "No":
                # True, as it explictly indicates that patient did not withdraw
                return True
            else:
                if "cst_withd_type" not in temp_cst_info:
                    # False, as cst_withd_type is not given
                    return False
                elif temp_cst_info["cst_withd_type"] == "1":
                    # TODO: Confirm which type is the valid type that permits future use
                    # True, as withdrawn consent type 1 permits future use
                    return True
                else:
                    # False, as withdraw consent type prohibits use
                    return False
        else:
            # False, as cst_main_yn indicates no consent was given
            return False
    else:
        # False, as cst_main_yn was not given
        return False

def parse_consent(patient_records, patient_id):
    consent_table = {}
    consent_table["patientId"] = patient_id

    for record in patient_records:
        if record.get("eventName") == "Enrollment":
            return redcap_transform(record, consent_table, "consent")
    return {}, {}

def parse_diagnosis(patient_records, patient_id, index):
    diagnosis_table = {}
    diagnosis_table["patientId"] = patient_id

    for record in patient_records:
        # Repeating CRF event
        if record.get("eventName") == "Diagnostic Information({})".format(index):
            return redcap_transform(record, diagnosis_table, "diagnosis")
    return {}, {}

def parse_treatment(patient_records, patient_id, index):
    treatment_table = {}
    treatment_table["patientId"] = patient_id
    treatment_table["treatmentPlanId"] = patient_id+"_tx"+str(index)

    for record in patient_records:
        # Repeating CRF event
        if record.get("eventName") == "Treatment Plan({})".format(index):
            return redcap_transform(record, treatment_table, "treatment")
    return {}, {}

def parse_outcome(patient_records, patient_id):
    outcome_table = {}
    outcome_table["patientId"] = patient_id

    for record in patient_records:
        if record.get("eventName") == "Vital Status and Clinical Follow-Up":
            return redcap_transform(record, outcome_table, "outcome")
    return {}, {}

def parse_complication(patient_records, patient_id):
    complication_table = {}
    complication_table["patientId"] = patient_id

    for record in patient_records:
        if record.get("eventName") == "Vital Status and Clinical Follow-Up":
            return redcap_transform(record, complication_table, "complication")
    return {}, {}

def parse_tumourboard(patient_records, patient_id, index):
    tumourboard_table = {}
    tumourboard_table["patientId"] = patient_id

    for record in patient_records:
        # Repeating CRF    event
        if record.get("eventName") == "Molecular Tumour Board({})".format(index):
            return redcap_transform(record, tumourboard_table, "tumourboard")
    return {}, {}

def redcap_transform(record, table_dict, table_str):
    """
    Parses a record for a single patient id for a single table type
    note: 'treatments' table is subparsed into an additonal list of treatment table types 
    return: record for a specific table and sub table collection (treatments)
    """
    for field in template.get(table_str, []):
        table_dict[template[table_str][field]] = record.get(field)
    record_items = record.get("items")

    sub_tables = dict(
        Chemotherapy = {},
        Radiotherapy = {},
        Surgery = {},
        Immunotherapy = {},
        CellTransplant = {}
    )

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
            item_num = item_name.split("(", 1)[1].split(")")[0]
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
                    if not table_dict.get(mapped_field):
                        table_dict[mapped_field] = mapped_item_value[0]
                    else:
                        if mapped_item_value[0] not in table_dict[mapped_field]:
                            table_dict[mapped_field] = table_dict[mapped_field] + ", " + mapped_item_value[0]

        # generate treatment sub tables
        if table_str == "treatment":
            for tx_table in ["Surgery", "Chemotherapy", "Radiotherapy", "Immunotherapy", "CellTransplant"]:
                tx_str = tx_table.lower()
                if item_name in template[tx_str+"_items"]:
                    mapped_field = template[tx_str+"_items"][item_name]
                    if "responseSet" not in record_item:
                        if item_num not in sub_tables[tx_table]:
                            sub_tables[tx_table][item_num] = {"treatmentPlanId": table_dict["treatmentPlanId"]}    
                        sub_tables[tx_table][item_num][mapped_field] = item_value
                    else:
                        response_set = record_item["responseSet"]
                        mapped_item_value = [d["optionsText"] for d in response_set["responseSetValues"] if d["value"] == item_value]
                        if len(mapped_item_value) > 0:
                            if item_num not in sub_tables[tx_table]:
                                sub_tables[tx_table][item_num] = {}    
                            sub_tables[tx_table][item_num][mapped_field] = mapped_item_value[0]

    return table_dict, sub_tables

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

def get_sites_for_prov(alpha_code):
    """
    Returns list of site ID's that belong to a province's access range
    """
    site_list = []
    code = alpha_code.lower()
    if code in ['bc', 'ab', 'sk', 'mb']:
        site_list = [1482, 1490, 1485, 1481, 1483]
    elif code in ['on']:
        site_list = [1478, 1489, 1477, 1491, 1479, 1484]
    elif code in ['qc', 'pe', 'nl', 'ns', 'nb']:
        site_list = [1480, 1487, 1486, 1488, 1496, 1476, 1497]
    return site_list

def get_sites_all(headers):
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
