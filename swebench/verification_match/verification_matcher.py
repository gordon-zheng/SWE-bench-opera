import json
import argparse
from pickle import TRUE
import sys
import os
import subprocess
import shutil
import base64
import re
from typing import List, Dict
from xml.dom import NotFoundErr
from flask import Flask, request, jsonify
from extract_and_patch_test_file import process_log_file
import importlib.util
from pathlib import Path
from diff_fixer import apply_fuzzy_matching_patch

# Define module name and path
module_name = 'diff_generator'
module_path = Path(__file__).resolve().parent.parent / 'diff_generator' / 'diff_generator.py'

# Load module specification
spec = importlib.util.spec_from_file_location(module_name, module_path)
diff_generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diff_generator)

# Use the create_patch function from the loaded module
create_patch = diff_generator.create_patch

app = Flask(__name__)

model_name = "opera-ai" # TODO this need to getting from the patch file

def parse_arguments():
    """
    Parses command-line arguments.

    Returns:
        argparse.Namespace: The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Find instance_id by python_file and generate a JSON object with provided patch."
    )
    parser.add_argument(
        "issue_64",
        type=str,
        help="The The issue description."
    )
    parser.add_argument(
        "file_name_64",
        type=str,
        help="The name of the Python file to search for (e.g., example.py)."
    )
    parser.add_argument(
        "diff_patch_64",
        type=str,
        help="The diff patch file that the LLM generated."
    )
    parser.add_argument(
        "instance_id",
        type=str,
        help="The instance_id of the issue."
    )
    parser.add_argument(
        "get_unit_test",
        type=str,
        help="(TRUE or FALSE) to get the unit test that is generated for this issue."
    )
    return parser.parse_args()


# Note: this function is currently not used.
def find_instance_id(file_name, issue, input_file_path="./complete_300_lite_input.txt"):
    """
    Searches for the instance_id corresponding to the given python_file.

    Args:
        file_name (str): The Python file name to search for.
        input_file_path (str): Path to the complete_300_lite_input.txt file.

    Returns:
        list: A list of matching instance_ids.
    """
     # Ensure file_name is relative by removing leading '/'
    if file_name.startswith("/"):
        original_file_name = file_name
        file_name = file_name.lstrip("/")
        print(f"Adjusted file_name from '{original_file_name}' to '{file_name}' to ensure it's relative.")

    matches = []
    if not os.path.isfile(input_file_path):
        print(f"Error: Input file '{input_file_path}' does not exist.", file=sys.stderr)
        return matches
    
    # truncate the issue text to be 200 character or less:
    if len(issue) > 200:
        issue = issue[:200]

    with open(input_file_path, 'r', encoding='utf-8') as infile:
        for line_number, line in enumerate(infile, start=1):
            line = line.strip()
            if not line:
                continue  # Skip empty lines
            try:
                data = json.loads(line)
                python_file = data.get('python_file', '')
                instance_id = data.get('instance_id', '')
                issue_in_data = data.get('issues_text', '')
                # due to the issues with extracting issues that might skip leading special characters, we need to remove some special characters from the issue strings
                issue = issue.replace('\n', '').replace('\r', '').replace('\t', '').replace(' ', '')
                issue_in_data = issue_in_data.replace('\n', '').replace('\r', '').replace('\t', '').replace(' ', '')
                if python_file == file_name and issue in issue_in_data:
                    matches.append(instance_id)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON on line {line_number}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Error processing line {line_number}: {e}", file=sys.stderr)

    return matches

def generate_output_jsonl(instance_id, model_name, patch):
    """
    Constructs the desired JSON object that is used in the jsonl file.

    Args:
        instance_id (str): The instance_id to include.
        patch (str): The patch string to include in model_patch.

    Returns:
        str: The JSON object as a string.
    """
    output_data = {
        "instance_id": instance_id,
        "model_name_or_path": model_name,
        "text": "",
        "full_output": "",
        "model_patch": patch
    }
    return output_data

def write_to_file(string_content, output_file):
    """
    Writes the JSON string to the specified output file.

    Args:
        string_content (str): The JSON string to write.
        output_file (str): The path to the output file.
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as outfile:
            outfile.write(string_content + '\n')
        print(f"Written file to '{output_file}' (overwritten existing content).")
    except Exception as e:
        print(f"Error writing to file '{output_file}': {e}", file=sys.stderr)


def clean_log_directory(instance_id):
    log_dir = log_dir = os.path.join('.', 'logs', 'run_evaluation', 'verify_one', model_name, instance_id)
    """
    Deletes all files and folders inside the specified directory.

    Args:
        log_dir (str): The directory path to clean.
    """
    try:
        print(f"Deleting all contents inside '{log_dir}'...")
        if os.path.exists(log_dir):
            # Iterate over all items in the directory
            for filename in os.listdir(log_dir):
                file_path = os.path.join(log_dir, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)  # Remove file or symbolic link
                        print(f"Deleted file: {file_path}")
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)  # Remove directory and all its contents
                        print(f"Deleted directory: {file_path}")
                except Exception as e:
                    print(f"Failed to delete '{file_path}'. Reason: {e}", file=sys.stderr)
        else:
            print(f"Directory '{log_dir}' does not exist. No contents to delete.")
    except Exception as e:
        print(f"An error occurred while deleting contents of '{log_dir}': {e}", file=sys.stderr)
        # Depending on your requirements, you might want to exit or continue
        # sys.exit(1)


def run_verification(verification_file_name):
    """
    Runs the verification script and captures its console output.

    Returns:
        str: The console output from the verification script.
    """
    command = [
        "python",
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        "princeton-nlp/SWE-bench_Lite",
        "--predictions_path",
        f"{verification_file_name}",
        "--max_workers",
        "4",
        "--run_id",
        "verify_one",
        # following command may not be needed
        "--clean",
        "TRUE",
        "--cache_level",
        "none",
        "--force_rebuild",
        "TRUE",
    ]

    try:
        print("Running verification script...")
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=True  # Raises CalledProcessError for non-zero exit codes
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_output = e.output.strip()
        print(f"Error during verification: {error_output}", file=sys.stderr)
        return error_output
    except FileNotFoundError:
        error_msg = "Verification script not found. Ensure that 'swebench' is installed and accessible."
        print(error_msg, file=sys.stderr)
        return error_msg
    except Exception as e:
        error_msg = f"An unexpected error occurred while running verification: {e}"
        print(error_msg, file=sys.stderr)
        return error_msg


def read_log_file(instance_id: str, file_name: str, file_extension: str):
    """
    Constructs the path to the specified log file and attempts to read its contents.

    Parameters:
        instance_id (str): The identifier for the specific instance.
        file_name (str): The name of the file to read (without extension).
        file_extension (str): The file extension (e.g., '.log').

    Returns:
        str: The contents of the log file if successful, 
             or an error message if the file cannot be read.
        boolean: did file load successfully
    """
    # Construct the base path to the log file
    base_path = os.path.join(
        '.', 
        'logs', 
        'run_evaluation', 
        'verify_one', 
        model_name, 
        instance_id
    )
    # Combine the base path with the file name and extension
    log_file_path = os.path.join(base_path, file_name) + file_extension

    # Initialize the variable to hold the log contents
    log_contents = ""
    log_file_loaded = True

    # Attempt to read the log file
    try:
        with open(log_file_path, 'r', encoding='utf-8') as log_file:
            log_contents = log_file.read().strip()
    except FileNotFoundError:
        log_contents = f"Log file '{log_file_path}' not found."
        log_file_loaded = False
    except Exception as e:
        log_contents = f"Error reading file '{log_file_path}': {e}"
        log_file_loaded = False

    return log_contents, log_file_loaded


def generate_verification_json(instance_id, python_file, error_msg_segment, patch_applied=True):
    """
    Constructs the verification JSON object, including the run_instance_log.

    Args:
        instance_id (str): The instance_id.
        python_file (str): The python_file name.
        error_msg_segment (str): The error message segment that is useful for the LLM ai to debug the issue.

    Returns:
        str: The JSON object as a string.
    """
    
    test_report_json, _ = read_log_file(instance_id, "report", ".json")

    # Determine fix_successful
    fix_successful = "FALSE"
    if "\"resolved\": true" in test_report_json:
        fix_successful = "TRUE"
    patched_str = "TRUE"
    if not patch_applied:
        patched_str = "FALSE"

    # Construct the verification data
    verification_data = {
        "instance_id": instance_id,
        "python_file": python_file,
        "error_msg_segment": error_msg_segment,
        "patch_applied": patched_str,
        "fix_successful": fix_successful,
    }
    print(f"==== Result: {instance_id}, fix_successful: {fix_successful}")
    return verification_data


def pretty_print_json(json_string, max_length=50):
    """
    Truncates each value in the JSON object to the specified maximum length.

    Args:
        json_string (str): The original JSON string.
        max_length (int): The maximum number of characters for each value.

    Returns:
        str: The truncated JSON string.
    """
    try:
        data = json.loads(json_string)
        truncated_data = {}
        for key, value in data.items():
            if isinstance(value, str):
                truncated_value = value[:max_length]
            else:
                # If the value is not a string, convert it to string and truncate
                truncated_value = str(value)[:max_length]
            truncated_data[key] = truncated_value
        print("======================")
        print("{")
        for key, value in truncated_data.items():
            print(f"   {key}: {value}")
        print("}")
        return
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON for truncation: {e}", file=sys.stderr)
        return json_string  # Return the original if decoding fails
    except Exception as e:
        print(f"Unexpected error during JSON truncation: {e}", file=sys.stderr)
        return json_string  # Return the original if any other error occurs


def extract_based64_string(base64_str):
    base64_bytes = base64_str.encode('utf-8')
    input_bytes = base64.b64decode(base64_bytes)
    return input_bytes.decode('utf-8')


def get_failed_test_files_with_content(json_str: str) -> Dict[str, List[Dict[str, str]]]:
    """
    Parses a JSON string representing test results, retrieves the file paths of failed tests,
    reads their contents, and returns a JSON structure with file names and contents.

    Parameters:
        json_str (str): A string containing the JSON data.

    Returns:
        Dict[str, List[Dict[str, str]]]: A dictionary with a key "failed_tests" containing
                                         a list of dictionaries with "test_file_name" and "content".
    """
    try:
        # Parse the JSON string into a Python dictionary
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON data: {e}")

    failed_files = set()

    # Iterate over all top-level keys in the JSON data
    for _, value in data.items():
        # Access the 'tests_status' dictionary
        tests_status = value.get("tests_status", {})
        
        # Iterate over each status category (e.g., "FAIL_TO_PASS", "PASS_TO_PASS", etc.)
        for _, status_values in tests_status.items():
            # Get the list of failed tests in the current category
            failures = status_values.get("failure", [])
            
            # Iterate over each failed test identifier
            for test_identifier in failures:
                # Split the test identifier to separate file path and test method
                parts = test_identifier.split("::")
                if len(parts) >= 1:
                    file_path = parts[0]
                    failed_files.add(file_path)
                else:
                    # Handle cases where the test identifier does not follow the expected format
                    continue

    # Prepare the list to hold file information
    failed_tests_info = []

    for file_path in failed_files:
        # Initialize content
        content = ""
        try:
            # Ensure the file path is safe and exists
            if not os.path.isfile(file_path):
                content = f"File '{file_path}' does not exist."
            else:
                # Read the file content
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
        except Exception as e:
            # Handle any other exceptions during file reading
            content = f"Error reading file '{file_path}': {e}"

        # Append the file information to the list
        failed_tests_info.append({
            "test_file_name": file_path,
            "content": content
        })

    # Construct the final JSON structure
    result = {
        "failed_tests": failed_tests_info
    }

    return result


def get_old_code(instance_id_to_find, source_json_file="./complete_300_lite_input.txt"):
    """
        get the old code that need to be fixed from the input prompts
    """
    old_code = None
    with open(source_json_file, 'r', encoding='utf-8') as infile:
        for line_number, line in enumerate(infile, start=1):
            line = line.strip()
            if not line:
                continue  # Skip empty lines
            try:
                data = json.loads(line)
                instance_id = data.get('instance_id', '')
                if instance_id == instance_id_to_find:
                    old_code = data.get('file_content', '')
                    python_file_path = data.get('python_file', '')
                    break
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON on line {line_number}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Error processing line {line_number}: {e}", file=sys.stderr)
    
    if old_code is None:
        error_text = f"Error, old_code not found for {instance_id_to_find}"
        print(error_text)
        raise NotFoundErr(error_text)
    
    return old_code, python_file_path


def remove_line_number(code_text):
    # remove the first line number if it exist, first line number is unique since it doesn't start with \n
    if code_text.startswith('1 '):
        code_text = code_text[2:]
    code_without_line_numbers = re.sub(r'\n\d+ ', '\n', code_text)
    return code_without_line_numbers


def extract_relevant_error(instance_id, verification_stdout):
    """
        extract the relevant error message for why the verification run failed from all the logs and console message
        return:
            None if the fix was successful and no error message is needed.
    """
   
    # check the content of those file to try to isolate the error segment.
    test_output_txt, test_output_exist = read_log_file(instance_id, "test_output", ".txt")
    # the below 3 logs file isn't needed for now.
    # test_report_json, test_report_exist = read_log_file(instance_id, "report", ".json")
    # run_instance_log, run_log_exist = read_log_file(instance_id, "run_instance", ".log")
    # test_eval_sh, test_eval_exist = read_log_file(instance_id, "eval", ".sh")

    error_log = ""
    # if the test_output.txt doesn't exist, mean something have gone wrong in the verification run (docker image build error, or patch error?)
    if not test_output_exist:
        # TODO: extract any error from stdout
        print(f"==== ERROR: no test_output.text exist for {instance_id}, here is the verification_stdout:\n{verification_stdout}")
        error_log = verification_stdout
    else:
        content_parts = re.split(r'Checking patch ', test_output_txt)
        rest_of_string = f"Checking patch {content_parts[-1].strip()}"
        content_parts = re.split(r'\+ git checkout', rest_of_string)
        error_log = content_parts[0]

    return error_log

def verify_patch(instance_id, diff_patch_64, get_unit_test=False):
    try:
        if not instance_id:
            error_msg = f"'instance_id' is required"
            return {"error": error_msg}, 400
        
        print(f"==== processing {instance_id}")
        temp_dir = "temp"
        # Always clean logs before processing the prompt
        clean_log_directory(instance_id)

        diff_patch_content = extract_based64_string(diff_patch_64)
        # remove the line number from the diff_patch_content if line number exists
        diff_patch_content = remove_line_number(diff_patch_content)
        # Write the diff_patch send by the caller to file system for debugging usage later 
        user_input_file_path = os.path.join(temp_dir, f"{instance_id}_input.diff")
        write_to_file(diff_patch_content, user_input_file_path)
    
        old_file_content, file_name = get_old_code(instance_id)
        # generate the new file content by fuzzy patching the old file
        # write out old file content to system, so it can be process by fuzzy matching
        old_file_path = os.path.join(temp_dir, f"{instance_id}_old.py")
        with open(old_file_path, 'wb') as f:
            f.write(old_file_content.encode("utf-8"))
        print(f"Attempting to fuzzy patch")
        new_file_content = apply_fuzzy_matching_patch(old_file_path, user_input_file_path)
        patch = create_patch(file_name, old_file_content.encode('utf-8'), new_file_content.encode('utf-8'), instance_id)

        # Use the first matching instance_id
        output_jsonl = generate_output_jsonl(instance_id, model_name, patch)
        verification_file_name = os.path.join(temp_dir, f"{instance_id}_verify_one_instance.jsonl")
        write_to_file(json.dumps(output_jsonl), verification_file_name)
        
        # Run verification and capture the output
        verification_stdout = run_verification(verification_file_name)
        
        # get the relevant error message from the different log files
        test_error_segment = extract_relevant_error(instance_id, verification_stdout)

        # Generate the verification JSON structure
        verification_json = generate_verification_json(instance_id, file_name, test_error_segment, True)
   
        response = {
            # "run_api_jsonl": output_jsonl, # for now don't include output_json, to make debugging easier
            "verification_json": verification_json
        }
        if get_unit_test:                    
            # creat the unit test of the process instance
            try:
                unit_test_content = process_log_file(instance_id)
            except Exception as e:
                unit_test_content = f"{e}"
            response["unit_test"] = unit_test_content
        
        return response, 200
    except ValueError as ve:
        return {
            "verification_json": generate_verification_json(instance_id, file_name, str(ve), False)
        }, 200
    except Exception as e:
        return {"error": str(e)}, 500


# New verify_patch route
@app.route('/verify_patch', methods=['POST'])
def verify_patch_endpoint():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400
        
        instance_id = data.get('instance_id')
        diff_patch_64 = data.get('diff_patch_64')
        get_unit_test = data.get('get_unit_test')

        if not get_unit_test:
            get_unit_test = False
        elif get_unit_test.upper() == "TRUE":
            get_unit_test = True
        elif get_unit_test.upper() == "FALSE":
            get_unit_test = False        

        if not instance_id or not diff_patch_64:
            return jsonify({"error": "Both 'instance_id' and 'diff_patch_64' fields are required"}), 400
        
        result, status_code = verify_patch(instance_id, diff_patch_64, get_unit_test)
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, threaded=True)
