import os
import sys
import re
from datetime import datetime

# Header template for the merged output file
header = f"""This file is a merged representation of selected files from the codebase.
Generated on: {datetime.utcnow().isoformat()}

================================================================
Purpose:
--------
This file is designed for efficient processing by LLMs, providing a packed 
representation of selected code files in the repository.

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

def is_binary_file(file_path):
    """
    Check if a file is binary by reading its first few bytes.
    """
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
            return b'\0' in chunk  # Simple check for null bytes
    except Exception as e:
        print(f"ERROR checking if file is binary: {file_path} - {str(e)}")
        return True  # Assume binary on error

def should_exclude_path(path, base_dir, exclude_patterns):
    """
    Determine if a path should be excluded based on the exclude patterns.
    """
    # Normalize path for consistent matching (convert backslashes to forward slashes)
    rel_path = os.path.relpath(path, base_dir).replace('\\', '/')
    
    # Check each exclude pattern
    for pattern in exclude_patterns:
        # Special handling for _*/ pattern
        if pattern == '_*/':
            path_parts = rel_path.split('/')
            if any(part.startswith('_') for part in path_parts):
                return True
        
        # If pattern ends with /, it's a directory pattern - exclude anything inside it
        if pattern.endswith('/') and rel_path.startswith(pattern):
            return True
            
        # Handle wildcard patterns with regex
        if '*' in pattern:
            # Convert glob pattern to regex pattern
            regex_pattern = pattern.replace('.', '\\.').replace('*', '.*')
            if re.match(f"^{regex_pattern}$", rel_path):
                return True
    
    return False

def find_focus_files(base_dir, focus_files, exclude_patterns):
    """
    Find and validate the specified focus files.
    Returns a list of (full_path, relative_path) tuples for valid focus files.
    """
    valid_files = []
    
    for focus_path in focus_files:
        # Get full path
        full_path = os.path.join(base_dir, focus_path)
        rel_path = focus_path.replace('\\', '/')
        
        # Check if file exists
        if not os.path.exists(full_path):
            print(f"WARNING: Focus file not found: {focus_path}")
            print(f"  Full path tried: {full_path}")
            print(f"  Current directory: {os.getcwd()}")
            continue
        
        # Check if file should be excluded
        if should_exclude_path(full_path, base_dir, exclude_patterns):
            print(f"WARNING: Focus file matches exclude pattern: {focus_path}")
            continue
        
        # Check if file is a directory
        if os.path.isdir(full_path):
            print(f"WARNING: Focus path is a directory, not a file: {focus_path}")
            continue
        
        # Check if file is binary
        if is_binary_file(full_path):
            print(f"WARNING: Focus file appears to be binary: {focus_path}")
            continue
        
        # All checks passed, add file
        valid_files.append((full_path, rel_path))
        print(f"Including focus file: {rel_path}")
    
    return valid_files

def collect_directory_structure(files):
    """
    Generate a directory structure based on the included files.
    """
    # Extract all unique directories from file paths
    directories = set()
    for _, rel_path in files:
        # Add all parent directories
        parts = rel_path.split('/')
        for i in range(len(parts)):
            if i > 0:  # Skip the file itself
                dir_path = '/'.join(parts[:i])
                if dir_path:
                    directories.add(dir_path)
    
    # Sort directories for consistent output
    sorted_dirs = sorted(directories)
    
    # Create a list to represent the directory structure
    structure_lines = ["./"]
    
    # Add directories with proper indentation
    for dir_path in sorted_dirs:
        depth = dir_path.count('/') + 1
        dir_name = os.path.basename(dir_path)
        structure_lines.append("    " * depth + dir_name + "/")
    
    # Add files with proper indentation
    for _, rel_path in sorted(files, key=lambda x: x[1]):
        dir_name = os.path.dirname(rel_path)
        depth = dir_name.count('/') + 1 if dir_name else 1
        file_name = os.path.basename(rel_path)
        structure_lines.append("    " * depth + file_name)
    
    return "\n".join(structure_lines)

def merge_files(base_dir, output_dir, output_prefix):
    """
    Main function to merge files using hardcoded config
    """
    # Use hardcoded config values
    focus_files = [
        "app/routes/portfolio_routes.py",
        "templates/pages/analyse.html",
        "templates/components/analyse_components.html"
    ]
    
    exclude_patterns = [
        "_*/",
        ".git/",
        ".LLM/",
        "venv/"
    ]
    
    print("Using hardcoded configuration:")
    print(f"Focus files: {focus_files}")
    print(f"Exclude patterns: {exclude_patterns}")
    
    # Process focus files
    print(f"\nFOCUS MODE: Will only include {len(focus_files)} specified files")
    files_to_include = find_focus_files(base_dir, focus_files, exclude_patterns)
    
    # If no files to include, exit
    if not files_to_include:
        print("ERROR: No valid files to include. Check focus files and exclude patterns.")
        return
    
    # Generate repository structure
    print(f"\nGenerating repository structure for {len(files_to_include)} files")
    repo_structure = collect_directory_structure(files_to_include)
    
    # Prepare output content
    output_lines = [
        header,
        repo_structure,
        ""
    ]
    
    # Process files
    print("\nProcessing files:")
    for full_path, rel_path in files_to_include:
        try:
            # Read and add file content
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            output_lines.append("================================================================")
            output_lines.append(f"###START_FILE_PATH: {rel_path}###")
            output_lines.append(content)
            output_lines.append("###END_FILE###\n")
            print(f"  Added: {rel_path}")
        
        except Exception as e:
            print(f"  ERROR reading {rel_path}: {str(e)}")
    
    # Write output file
    output_file = f"{output_prefix}.txt"
    output_path = os.path.join(output_dir, output_file)
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output_lines))
        print(f"\nCreated {output_path} with {len(files_to_include)} files")
    except Exception as e:
        print(f"ERROR creating output file {output_path}: {str(e)}")
        # Try with a different approach
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for line in output_lines:
                    f.write(line + '\n')
            print(f"\nCreated {output_path} (alternative method) with {len(files_to_include)} files")
        except Exception as e2:
            print(f"ERROR on second attempt: {str(e2)}")

if __name__ == "__main__":
    # Get script directory and parent directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    
    # Print current working directory
    print(f"Current working directory: {os.getcwd()}")
    print(f"Script directory: {script_dir}")
    print(f"Parent directory: {parent_dir}")
    
    # Get output prefix from command line args
    output_prefix = "merged_output"
    if len(sys.argv) > 1 and not sys.argv[1].startswith('--'):
        output_prefix = sys.argv[1]
    
    print(f"Repository merger script starting:")
    print(f"  Base directory: {parent_dir}")
    print(f"  Output directory: {script_dir}")
    print(f"  Output file: {output_prefix}.txt\n")
    
    # Check existing config.yml
    config_path = os.path.join(script_dir, 'config.yml')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Existing config.yml contains {len(content)} bytes:")
            print("-" * 40)
            print(content)
            print("-" * 40)
        except Exception as e:
            print(f"Error reading config.yml: {str(e)}")
    
    # Merge files using hardcoded config
    merge_files(parent_dir, script_dir, output_prefix)