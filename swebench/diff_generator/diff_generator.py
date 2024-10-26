from flask import Flask, request, jsonify
import os
import base64
import subprocess
import re

app = Flask(__name__)

def create_patch(full_file_path, original_file, new_file, instance_id=None):
    # Create 'temp' directory if it doesn't exist
    temp_dir = 'temp'
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    # Paths to the temporary files
    if instance_id is None:
        old_file_path = os.path.join(temp_dir, 'old.py')
        new_file_path = os.path.join(temp_dir, 'new.py')
        org_patch_file = os.path.join(temp_dir, 'org_patch.diff')
        patch_file = os.path.join(temp_dir, 'patch.diff')
    else:
        old_file_path = os.path.join(temp_dir, f"{instance_id}_old.py")
        new_file_path = os.path.join(temp_dir, f"{instance_id}_new.py")
        org_patch_file = os.path.join(temp_dir, f"{instance_id}_org_patch.diff")
        patch_file = os.path.join(temp_dir, f"{instance_id}_patch.diff")

    # Write out the original file
    with open(old_file_path, 'wb') as f:
        f.write(original_file)

    # Write out the new file
    with open(new_file_path, 'wb') as f:
        f.write(new_file)

    # Run diff tool to generate diff file
    diff_command = ['diff', '-u', old_file_path, new_file_path]

    with open(org_patch_file, 'w') as f:
        subprocess.run(diff_command, stdout=f)

    # Read in the diff file and adjust the lines
    with open(org_patch_file, 'r') as f:
        diff_lines = f.readlines()
    
    # Strip leading slashes from full_file_path
    normalized_file_path = re.sub(r'^(\./|/)+', '', full_file_path)
    
    new_diff_lines = []
    for line in diff_lines:
        if line.startswith('--- '):
            new_line = f'--- a/{normalized_file_path}\n'
        elif line.startswith('+++ '):
            new_line = f'+++ b/{normalized_file_path}\n'
        else:
            new_line = line
        new_diff_lines.append(new_line)

    # Write the updated diff content to 'patch.diff'
    with open(patch_file, 'w') as f:
        f.writelines(new_diff_lines)

    # return the diff content in base64 encoding
    diff_content = ''.join(new_diff_lines)
    return diff_content

@app.route('/create_patch', methods=['POST'])
def create_patch_endpoint():
    data = request.get_json()
    full_file_path = data.get('full_file_path')
    original_file_base64 = data.get('original_file_base64')
    new_file_base64 = data.get('new_file_base64')

    if not all([full_file_path, original_file_base64, new_file_base64]):
        return jsonify({'error': 'Missing parameters'}), 400

    
    try:
        original_file = base64.b64decode(original_file_base64)
        new_file = base64.b64decode(new_file_base64)
        diff_content = create_patch(full_file_path, original_file, new_file)
        diff_content_base64 = base64.b64encode(diff_content.encode('utf-8')).decode('utf-8')
        print(f"diff_content_base64 based string:\n{base64.b64decode(diff_content_base64).decode('utf-8')}")
        return jsonify({'diff_base64': diff_content_base64}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)