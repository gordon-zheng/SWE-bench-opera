import json
import re

# Define the input and output file paths
input_file_path = 'all_300_input.jsonl'  # Replace with your actual input file path
output_file_path = 'complete_300_lite_input.txt'

# Define the regular expression pattern to find the python file name
pattern_file_name = re.compile(r'\[start of ([^\]]+\.py)\]')

def extract_python_file(text):
    """
    Extracts the Python file name from the given text using the specified regex pattern.
    
    Args:
        text (str): The text to search within.
        
    Returns:
        str or None: The extracted Python file name if a match is found; otherwise, None.
    """
    match = pattern_file_name.search(text)
    if match:
        return match.group(1)
    return None

def extract_issues(text):
    """
    Extracts the text between <issue> and </issue> tags.
    
    Args:
        text (str): The text to search within.
        
    Returns:
        str or None: The extracted issues text if found; otherwise, None.
    """
    match = re.search(r'<issue>(.*?)</issue>', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def extract_target_code(text, file_name):
    """
        Extract the python code between: '\[start of ([^\]]+\.py)\]' and '[end of ([^\]]+\.py)\]'
    """
    pattern = r'\[start of .*?\.py\](.*?)\[end of .*?\.py\]'
    # Search for the pattern
    match = re.search(pattern, text, re.DOTALL)

    if match:
        code_segment = match.group(1)
        # Use re.sub to remove the line numbers and a single space after them
        code_without_line_numbers = re.sub(r'\n\d+ ', '\n', code_segment)
        # Remove a leading newline if it still exists
        if code_without_line_numbers.startswith('\n'):
            code_without_line_numbers = code_without_line_numbers[1:]
        # we also remove the extra '\n' for the start of the '\n[end of ...]'
        code_without_line_numbers = code_without_line_numbers[:-1]
    else:
        print(f"code segment not found for file: {file_name}.")
    return code_without_line_numbers

def process_file(input_path, output_path):
    """
    Processes the input file line by line, extracts the Python file names and issues text,
    and writes the results to the output file.
    
    Args:
        input_path (str): Path to the input JSONL file.
        output_path (str): Path to the output file.
    """
    with open(input_path, 'r', encoding='utf-8') as infile, \
         open(output_path, 'w', encoding='utf-8') as outfile:
        
        for line_number, line in enumerate(infile, start=1):
            line = line.strip()
            if not line:
                # Skip empty lines
                continue
            try:
                data = json.loads(line)
                instance_id = data.get('instance_id')
                text = data.get('text', '')
                
                python_file = extract_python_file(text)
                issues_text = extract_issues(text)
                code_segment = extract_target_code(text, python_file)
                
                # Prepare the output JSON object
                output_data = {
                    "instance_id": instance_id,
                    "python_file": python_file if python_file else "",
                    "issues_text": issues_text if issues_text else "", # the value suppose to be 1000
                    "file_content": code_segment,
                }
                
                # Write the JSON object to the output file
                outfile.write(json.dumps(output_data) + '\n')
                
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON on line {line_number}: {e}")
            except Exception as e:
                print(f"Error processing line {line_number}: {e}")

if __name__ == "__main__":
    process_file(input_file_path, output_file_path)
    print(f"Processing complete. Extracted data written to '{output_file_path}'.")
