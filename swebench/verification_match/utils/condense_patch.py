import sys
import subprocess
import shutil
import os

def generate_condense_patch(source_file_content, patch_content, original_file_name):
    # Define temporary filenames
    source_file = 'source.py'
    patch_file = 'input.diff'
    patched_file = 'patched.py'
    diff_file = 'new.diff'
    
    # Write the original file content to source.py
    with open(source_file, 'w') as f:
        f.write(source_file_content)
    
    # Write the original patch content to input.diff
    with open(patch_file, 'w') as f:
        f.write(patch_content)
    
    # Copy source.py to patched.py
    shutil.copyfile(source_file, patched_file)
    
    # Apply the patch to patched.py
    try:
        subprocess.run(['patch', patched_file, '-i', patch_file], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print("Error applying patch:", e.stderr.decode())
        return ''
    
    # Generate a new diff between source.py and patched.py with correct file names in headers
    with open(diff_file, 'w') as f:
        subprocess.run([
            'diff', '-u',
            '-L', original_file_name,  # Label for the original file
            '-L', original_file_name,  # Label for the patched file
            source_file, patched_file
        ], stdout=f)
        
    # Read the content of the new diff file
    with open(diff_file, 'r') as f:
        new_diff_content = f.read()
    
    # Clean up temporary files
    os.remove(source_file)
    os.remove(patch_file)
    os.remove(patched_file)
    # os.remove(diff_file)
    
    return new_diff_content

def main():
    if len(sys.argv) != 3:
        print("Usage: python script.py <python_file> <diff_file>")
        sys.exit(1)
    
    python_file = sys.argv[1]
    diff_file = sys.argv[2]
    
    # Read the content of the Python source file
    with open(python_file, 'r') as f:
        file_content = f.read()
    
    # Read the content of the diff patch file
    with open(diff_file, 'r') as f:
        patch_content = f.read()
    
    # Generate the condensed patch
    result = generate_condense_patch(file_content, patch_content, python_file)
    
    # Print the result
    print(result)

if __name__ == '__main__':
    main()
