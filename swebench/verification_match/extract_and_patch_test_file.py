from distutils.errors import UnknownFileError
import re
import argparse
import sys
import os
import subprocess
import shutil
import logging
from typing import Optional


# Pre-defined dictionary of repositories
repositories = {
    "astropy": "https://github.com/astropy/astropy.git",
    "django": "https://github.com/django/django.git",
    "matplotlib": "https://github.com/matplotlib/matplotlib.git",
    "seaborn": "https://github.com/mwaskom/seaborn.git",
    "requests": "https://github.com/psf/requests.git",
    "pylint": "https://github.com/pylint-dev/pylint.git",
    "pytest": "https://github.com/pytest-dev/pytest.git",
    "scikit-learn": "https://github.com/scikit-learn/scikit-learn.git",
    "sphinx": "https://github.com/sphinx-doc/sphinx.git", 
    "sympy": "https://github.com/sympy/sympy.git",
    # Add more repositories as needed
}

base_directory = "./git_repository/"

repo_locations = {
    "astropy": f"{base_directory}astropy/",
    "django": f"{base_directory}django/",
    "matplotlib": f"{base_directory}matplotlib/",
    "seaborn": f"{base_directory}seaborn/",
    "requests": f"{base_directory}requests/",
    "pylint": f"{base_directory}pylint/",
    "pytest": f"{base_directory}pytest/",
    "scikit-learn": f"{base_directory}scikit-learn/",
    "sphinx": f"{base_directory}sphinx/",
    "sympy": f"{base_directory}sympy/",
}

patched_file_main_folder = "./patched_tests"

run_verification_log_location = "./logs/run_evaluation/verify_one/opera-ai/"

eval_file_name = "eval.sh"


def extract_commands(log_file_path, output_script_path):
    capturing = False
    captured_lines = []
    test_file = None
    eof_line_start_marker = "EOF_"

    # Regular expressions
    # Matches lines like: git checkout <commit_hash> <file_path>
    git_checkout_pattern = re.compile(r'^\s*git\s+checkout\s+\S+\s+([^\s]+)$')
    # Matches lines starting with 'pytest', allowing leading spaces
    pytest_pattern = re.compile(r'^\s*pytest\b')
    # Extracts the name of the patched file from the bash script.
    diff_pattern = re.compile(r'^diff --git a/(?P<file_path>.+?) b/\1$', re.MULTILINE)

    # Read all lines from the log file
    try:
        with open(log_file_path, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: The file '{log_file_path}' does not exist.")
        raise FileNotFoundError(f"Error: The file '{log_file_path}' does not exist.")
    except Exception as e:
        print(f"Error reading the file '{log_file_path}': {e}")
        raise FileExistsError(f"Error reading the file '{log_file_path}'.")
    
    # Identify the first git checkout command that checks out a specific file
    start_idx = None
    for idx, line in enumerate(lines):
        checkout_match = git_checkout_pattern.search(line)
        if checkout_match:
            # Extract the file path from the git checkout command
            test_file = checkout_match.group(1)
            capturing = True
            start_idx = idx
            captured_lines.append(line)
            print(f"Capturing started at line {idx + 1}: {line.strip()}")
            break
    
    if not capturing:
        print("No 'git checkout' command found that checks out a specific file.")
        raise Exception(f"No 'git checkout' command found that checks out '{log_file_path}'.")
    
    # Capture all subsequent lines from the first git checkout onward
    for line in lines[start_idx + 1:]:
        captured_lines.append(line)
    
    # Now, process the captured lines to:
    # 1. Exclude any lines that are 'pytest' commands
    # 2. Exclude the final 'git checkout' command if present

    # Filter out 'pytest' commands
    filtered_lines = []
    for line in captured_lines:
        if line.startswith(eof_line_start_marker):
            # we encountered the EOF_... which should signify the end of the patch.
            filtered_lines.append(line)
            filtered_lines.append("\n")
            break
        filtered_lines.append(line)
        matches = diff_pattern.findall(line)
        if matches:
            patched_file = matches[0]
    
    # Write the filtered commands to the output script
    try:
        with open(output_script_path, 'w') as f:
            f.write('#!/bin/bash\n')
            f.write('set -euxo pipefail\n')
            for captured_line in filtered_lines:
                f.write(captured_line)
    except Exception as e:
        print(f"Error writing to the output script '{output_script_path}': {e}")
        raise Exception(f"Error writing to the output script '{output_script_path}': {e}")
    
    if test_file:
        print(f"Test file being changed: {test_file}")
    else:
        print("No test file changes detected.")
    
    print(f"Captured commands have been written to '{output_script_path}', for test file: {patched_file}")
    return patched_file
    

def update_or_clone_repos(base_dir="."):
    repo_dict = repositories
    repo_dirs = []
    for repo_name, repo_url in repo_dict.items():
        local_dir = os.path.join(base_dir, repo_name)
        repo_dirs.append(local_dir)
        if os.path.isdir(local_dir):
            if os.path.isdir(os.path.join(local_dir, '.git')):
                print(f"Repository '{repo_name}' exists. Pulling latest code.")
                subprocess.run(['git', '-C', local_dir, 'pull'], check=True)
            else:
                print(f"Directory '{local_dir}' exists but is not a Git repository.")
                raise Exception(f"Directory '{local_dir}' exists but is not a Git repository.")
        else:
            print(f"Cloning repository '{repo_name}' into '{local_dir}'.")
            subprocess.run(['git', 'clone', repo_url, local_dir], check=True)
    return repo_dirs


def extract_project_name(instance_id):
    """
    Extracts the project name from the instance_id based on specific rules.
    Args:
        instance_id (str): The instance_id string (e.g., "django__django-11099").
    Returns:
        str: The extracted project name (e.g., "django").
    """
    # Split the instance_id on double underscores
    parts = instance_id.split('__')
    if not parts:
        raise UnknownFileError("The instance_id does not match expected format")

    project_identifier = parts[0]

    # Exception: If the project is "scikit-learn", retain it as is
    if project_identifier == "scikit-learn":
        return project_identifier

    # If the project_identifier contains a hyphen, remove the suffix
    if '-' in project_identifier:
        base_project = project_identifier.split('-')[0]
        return base_project
    else: # If no hyphen, retain as is
        return project_identifier


def process_log_file(
    instance_id: str
) -> str:
    """
    Processes the log file to extract git commands, execute them in the specified project,
    and copy the patched file to a designated directory.

    Parameters:
        instance_id (str): instance_id of the input.
    Return:
        the file content of the unit test.
    """
    output = os.path.join(patched_file_main_folder, f"{instance_id}_extracted.sh")
    log_file = f"{run_verification_log_location}{instance_id}/{eval_file_name}"

    # Validate log_file
    if not os.path.isfile(log_file):
        logging.error(f"Log file '{log_file}' does not exist.")
        return f"{eval_file_name} does not exist for {instance_id}"
    
    # Extract commands from the log file
    patched_test_file = extract_commands(log_file, output)
    logging.info(f"Patched file extracted: {patched_test_file}")

    # Execute git commands if execute_project is provided
    execute_project = extract_project_name(instance_id)
    if execute_project:
        project_path = repo_locations.get(execute_project)
        if not project_path:
            logging.error(f"Project '{execute_project}' not found in repo_locations.")
            return f"could not find {execute_project} repo location for {instance_id}"
        
        if not os.path.isdir(project_path):
            logging.error(f"Project path '{project_path}' does not exist.")
            return f"could not find repo path {project_path} for {instance_id}"
        
        script_path = os.path.abspath(output)
        logging.info(f"Changing directory to: {project_path}")

        try:
            subprocess.run(['bash', script_path], check=True, cwd=project_path)
            logging.info(f"Executed script: {script_path} in {project_path}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error executing script: {e}")
            return f"issue running the {script_path} script for {instance_id}"

        # Copy the patched file if requested
      
        dest_folder = f"{instance_id}"
        source_file = os.path.join(project_path, patched_test_file)
        dest_dir = os.path.join(patched_file_main_folder, dest_folder)

        # Ensure the destination directory exists
        try:
            os.makedirs(dest_dir, exist_ok=True)
            logging.info(f"Destination directory '{dest_dir}' is ready.")
        except Exception as e:
            logging.error(f"Error creating destination directory '{dest_dir}': {e}")
            return f"problem creating the directory: {dest_dir} for {instance_id}"

        # Get the base name of the patched file to copy it without the full path
        dest_file = os.path.join(dest_dir, os.path.basename(patched_test_file))

        # Verify the source file exists
        if not os.path.isfile(source_file):
            logging.error(f"Source file '{source_file}' does not exist.")
            return f"Unit test: {dest_dir} for {instance_id} does not exist"

        try:
            # Copy the patched file to the destination directory
            shutil.copy2(source_file, dest_file)
            print(f"Copied '{source_file}' to '{dest_file}'")
        except FileNotFoundError as e:
            logging.error(f"Error: {e}")
            return f"file not found when copying Unit test file: {dest_dir} for {instance_id}"
        except Exception as e:
            logging.error(f"An unexpected error occurred while copying the file: {e}")
            return f"could not copy Unit test file: {dest_dir} for {instance_id}"

        # Reset the git repository to the latest commit
        try:
            subprocess.run(['git', 'reset', '--hard'], check=True, cwd=project_path)
            logging.info(f"Executed 'git reset --hard' in {project_path}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error executing 'git reset --hard': {e}")
            return f"error resetting project git repo for {instance_id}"
        
        # read the dest_file content, and return it to the caller
        with open(dest_file, 'r', encoding='utf-8') as file:
            content = file.read()
        return content

def main():
    parser = argparse.ArgumentParser(description='Extract git checkout and patching commands from a log file.')
    parser.add_argument('instance_id', help='Path to the log file to parse')
    
    args = parser.parse_args()
    process_log_file(instance_id=args.instance_id)

if __name__ == "__main__":
    main()
