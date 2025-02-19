import os
import sys
from datetime import datetime
from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

# Header template
header = f"""This file is a merged representation of the entire codebase, combining all repository files into a single document.
Generated on: {datetime.utcnow().isoformat()}

================================================================
Purpose:
--------
This file is designed for efficient processing by LLMs, providing a packed 
representation of all code files in the repository.

Format:
-------
- This summary section
- Repository structure
- File sections, each consisting of:
  - A separator line (================)
  - The file path (###START_FILE_PATH: path/to/file###)
  - File contents
  - ###END_FILE###

================================================================
Repository Structure
================================================================
"""

# Load gitignore patterns
def load_gitignore(directory):
    gitignore_path = os.path.join(directory, '.gitignore')
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r') as f:
            return PathSpec.from_lines(GitWildMatchPattern, f.readlines())
    return None

# Function to exclude certain paths
def should_exclude(path, base_dir, gitignore_spec):
    base_name = os.path.basename(path)
    # Basic exclusions
    if base_name.startswith('_') or base_name == 'LLM' or base_name == '.git':
        return True
    
    # Check gitignore patterns if available
    if gitignore_spec:
        rel_path = os.path.relpath(path, base_dir)
        return gitignore_spec.match_file(rel_path)
    
    return False

# Function to generate the repository structure as a formatted string
def generate_repository_structure(directory, gitignore_spec):
    structure = []
    for root, dirs, files in os.walk(directory):
        # Filter out excluded directories in place
        dirs[:] = [d for d in dirs if not should_exclude(os.path.join(root, d), directory, gitignore_spec)]
        
        # Add directory path to structure
        indent_level = root.replace(directory, "").count(os.sep)
        structure.append("    " * indent_level + os.path.basename(root) + "/")
        
        for file in files:
            file_path = os.path.join(root, file)
            if not should_exclude(file_path, directory, gitignore_spec) and file.endswith('.py'):
                structure.append("    " * (indent_level + 1) + file)
                
    return "\n".join(structure)

# Function to merge files and split output if necessary
def merge_and_split_files(directory, output_prefix, max_size_mb=10):
    max_size_bytes = max_size_mb * 1024 * 1024
    current_size = 0
    current_file_number = 1
    gitignore_spec = load_gitignore(directory)
    repository_structure = generate_repository_structure(directory, gitignore_spec)
    current_output = [header, repository_structure, ""]

    def write_output():
        nonlocal current_file_number
        output_filename = os.path.join(script_dir, f"{output_prefix}_{current_file_number}.txt")
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write('\n'.join(current_output))
        print(f"Created {output_filename}")
        current_file_number += 1

    for root, dirs, files in os.walk(directory):
        # Exclude certain directories
        dirs[:] = [d for d in dirs if not should_exclude(os.path.join(root, d), directory, gitignore_spec)]

        for file in files:
            if file.endswith('.py') and not should_exclude(os.path.join(root, file), directory, gitignore_spec):
                file_path = os.path.join(root, file)
                
                # Skip files in excluded paths
                if any(should_exclude(os.path.join(directory, part), directory, gitignore_spec) for part in file_path.split(os.sep)):
                    continue

                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                file_size = len(content.encode('utf-8'))

                if current_size + file_size > max_size_bytes:
                    if current_output:
                        write_output()
                    current_output = [header, repository_structure, ""]
                    current_size = 0
                
                relative_path = os.path.relpath(file_path, directory)
                current_output.append("================================================================")
                current_output.append(f"###START_FILE_PATH: {relative_path}###")
                current_output.append(content)
                current_output.append("###END_FILE###")
                current_output.append("")  # Add an empty line between files
                current_size += file_size

    if current_output:
        write_output()

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)

    output_prefix = "merged_output"
    max_size_mb = 10

    if len(sys.argv) > 1:
        output_prefix = sys.argv[1]
    if len(sys.argv) > 2:
        max_size_mb = int(sys.argv[2])

    print(f"Scanning directory: {parent_dir}")
    print(f"Output will be saved in: {script_dir}")
    print(f"Output prefix: {output_prefix}")
    print(f"Maximum file size: {max_size_mb} MB")
    print("Excluding folders: /LLM, and all folders starting with '.' or '_'")

    merge_and_split_files(parent_dir, output_prefix, max_size_mb)